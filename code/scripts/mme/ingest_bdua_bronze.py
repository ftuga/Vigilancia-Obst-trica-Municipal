"""
Ingesta bronze: BDUA — Afiliados por municipio y régimen (snapshot MinSalud).

Fuente oficial: `hn4i-593p` — "Número de afiliados por departamento, municipio y régimen".
Publisher: Ministerio de Salud y Protección Social (MinSalud).
URL: https://www.datos.gov.co/d/hn4i-593p

Cobertura: snapshot 2022 (el dataset dice "por trimestre desde 2017" pero actualmente
sólo expone 2022 abril con ~3.369 filas). Régimenes: C (contributivo), S (subsidiado),
E (excepción, p.ej. magisterio/fuerzas), I (indígena — subsistema especial).

La cobertura cambia con lentitud (meses de orden, no semanas), por lo que la
variable se usa como **feature estructural invariante** en el panel 2016-2022,
con el snapshot 2022 como representante del período. Documentar limitación.

Output:
  data/mme/bronze/bdua/afiliados_muni_regimen.parquet
  data/mme/bronze/bdua/_manifest.json

Uso:
  uv run python scripts/mme/ingest_bdua_bronze.py
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd
import requests

DATASET_ID = "hn4i-593p"
BASE_URL = f"https://www.datos.gov.co/resource/{DATASET_ID}.json"
PAGE_SIZE = 50_000
TIMEOUT = 60

from _paths import REPO_ROOT, MME_DATA
BRONZE_DIR = MME_DATA / "bronze" / "bdua"
PARQUET_PATH = BRONZE_DIR / "afiliados_muni_regimen.parquet"
MANIFEST_PATH = BRONZE_DIR / "_manifest.json"


def fetch_all() -> pd.DataFrame:
    offset = 0
    pages: list[list[dict]] = []
    while True:
        t0 = time.perf_counter()
        r = requests.get(BASE_URL, params={"$limit": PAGE_SIZE, "$offset": offset,
                                           "$order": "ano,coddepto,codmunicipio,idregimen"},
                         timeout=TIMEOUT)
        r.raise_for_status()
        batch = r.json()
        dt = time.perf_counter() - t0
        print(f"  [page offset={offset:>6}] rows={len(batch):>5} in {dt:.2f}s", flush=True)
        if not batch:
            break
        pages.append(batch)
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    flat = [row for page in pages for row in page]
    return pd.DataFrame(flat)


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    int_cols = ["coddepto", "codmunicipio", "ano", "mes", "numpersonas"]
    for c in int_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    str_cols = ["departamento", "municipio", "idregimen"]
    for c in str_cols:
        if c in df.columns:
            df[c] = df[c].astype("string").str.strip()
    df = df.rename(columns={
        "coddepto": "cod_dpto",
        "codmunicipio": "cod_mpio",
        "numpersonas": "n_afiliados",
        "idregimen": "regimen_code",
    })
    df["regimen_nombre"] = df["regimen_code"].map({
        "C": "Contributivo",
        "S": "Subsidiado",
        "E": "Excepción",
        "I": "Indígena (subsistema)",
    }).astype("string")
    return df


def pivot_to_muni(df: pd.DataFrame) -> pd.DataFrame:
    """Pivota a 1 fila por municipio: columnas por régimen + derivados."""
    # Usar el snapshot más reciente por (muni, régimen) por si hay múltiples meses
    latest = (df.sort_values(["cod_mpio", "regimen_code", "ano", "mes"])
                .groupby(["cod_mpio", "regimen_code"], as_index=False).tail(1))

    wide = (latest.pivot_table(index=["cod_mpio", "cod_dpto", "departamento", "municipio"],
                               columns="regimen_code", values="n_afiliados",
                               aggfunc="sum", fill_value=0)
                  .reset_index())
    wide.columns.name = None

    for col in ["C", "S", "E", "I"]:
        if col not in wide.columns:
            wide[col] = 0

    wide = wide.rename(columns={
        "C": "afiliados_contributivo",
        "S": "afiliados_subsidiado",
        "E": "afiliados_excepcion",
        "I": "afiliados_indigena",
    })
    wide["afiliados_total"] = (wide["afiliados_contributivo"] + wide["afiliados_subsidiado"]
                               + wide["afiliados_excepcion"] + wide["afiliados_indigena"])
    wide["pct_subsidiado_muni"] = (wide["afiliados_subsidiado"] * 100.0
                                   / wide["afiliados_total"].replace(0, pd.NA)).round(3)
    wide["pct_contributivo_muni"] = (wide["afiliados_contributivo"] * 100.0
                                     / wide["afiliados_total"].replace(0, pd.NA)).round(3)
    wide["pct_excepcion_muni"] = (wide["afiliados_excepcion"] * 100.0
                                  / wide["afiliados_total"].replace(0, pd.NA)).round(3)

    # Asegurar cod_mpio int64
    wide["cod_mpio"] = pd.to_numeric(wide["cod_mpio"], errors="coerce").astype("Int64")
    wide["cod_dpto"] = pd.to_numeric(wide["cod_dpto"], errors="coerce").astype("Int64")
    wide = wide.dropna(subset=["cod_mpio"])
    wide["cod_mpio"] = wide["cod_mpio"].astype("int64")
    wide["cod_dpto"] = wide["cod_dpto"].astype("int64")

    cols = [
        "cod_mpio", "cod_dpto", "departamento", "municipio",
        "afiliados_contributivo", "afiliados_subsidiado",
        "afiliados_excepcion", "afiliados_indigena", "afiliados_total",
        "pct_subsidiado_muni", "pct_contributivo_muni", "pct_excepcion_muni",
    ]
    return wide[cols]


def write_bronze(df: pd.DataFrame) -> None:
    BRONZE_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(":memory:")
    con.register("afil", df)
    con.execute(
        f"COPY (SELECT * FROM afil ORDER BY cod_mpio) TO '{PARQUET_PATH}' "
        f"(FORMAT PARQUET, COMPRESSION ZSTD)"
    )
    con.close()
    print(f"[bdua] wrote {PARQUET_PATH} ({len(df):,} municipios)")


def sha256_of_dataframe(df: pd.DataFrame) -> str:
    h = hashlib.sha256()
    for row in df.itertuples(index=False, name=None):
        h.update(repr(row).encode("utf-8"))
    return h.hexdigest()


def write_manifest(df_raw: pd.DataFrame, df_wide: pd.DataFrame, periods: list[str]) -> None:
    manifest = {
        "source": {
            "portal": "datos.gov.co",
            "provider": "Ministerio de Salud y Protección Social (MinSalud)",
            "dataset_id": DATASET_ID,
            "dataset_name": "Número de afiliados por departamento, municipio y régimen",
            "api": BASE_URL,
        },
        "ingested_at_utc": datetime.now(timezone.utc).isoformat(),
        "raw_row_count": int(len(df_raw)),
        "periods_observed": periods,
        "regimen_codes": {
            "C": "Contributivo", "S": "Subsidiado",
            "E": "Excepción", "I": "Indígena (subsistema)",
        },
        "n_municipios_pivot": int(len(df_wide)),
        "schema": list(df_wide.columns),
        "summary_stats": {
            "total_afiliados": int(df_wide["afiliados_total"].sum()),
            "pct_subsidiado_mean": round(float(df_wide["pct_subsidiado_muni"].mean()), 2),
            "pct_subsidiado_median": round(float(df_wide["pct_subsidiado_muni"].median()), 2),
            "top5_subsidiado": df_wide.nlargest(5, "pct_subsidiado_muni")[
                ["cod_mpio", "municipio", "departamento",
                 "pct_subsidiado_muni", "afiliados_total"]].to_dict(orient="records"),
            "top5_contributivo": df_wide.nlargest(5, "pct_contributivo_muni")[
                ["cod_mpio", "municipio", "departamento",
                 "pct_contributivo_muni", "afiliados_total"]].to_dict(orient="records"),
        },
        "content_sha256": sha256_of_dataframe(df_wide),
        "notes": [
            "Snapshot BDUA — el dataset dice 'trimestral desde 2017' pero actualmente expone sólo 2022.",
            "Uso en panel MME 2016-2022: feature temporalmente invariante (cobertura cambia con lentitud).",
            "pct_subsidiado_muni = proxy Demora II según recomendación del mme-domain-expert.",
            "ADRES: afiliados por municipio de RESIDENCIA (puede diferir del muni de atención).",
            "Referencia: cobertura aseguramiento Colombia 2022 ≈ 96-97% nacional.",
        ],
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str))
    print(f"[bdua] manifest → {MANIFEST_PATH}")


def main() -> int:
    print(f"[bdua] descargando {DATASET_ID} desde datos.gov.co")
    raw = fetch_all()
    if raw.empty:
        print("[bdua] ⚠ dataset vacío", file=sys.stderr)
        return 2
    print(f"[bdua] {len(raw):,} filas descargadas")

    df = normalize(raw)
    # Documentar períodos (ano-mes)
    periods = sorted(f"{int(a)}-{int(m):02d}"
                     for a, m in df[["ano", "mes"]].dropna().drop_duplicates().itertuples(index=False))
    print(f"[bdua] períodos: {periods}")

    wide = pivot_to_muni(df)
    print(f"[bdua] pivoted: {len(wide):,} municipios | afiliados totales {int(wide['afiliados_total'].sum()):,}")
    print(f"[bdua] pct_subsidiado mean {wide['pct_subsidiado_muni'].mean():.2f}% "
          f"median {wide['pct_subsidiado_muni'].median():.2f}%")

    write_bronze(wide)
    write_manifest(raw, wide, periods)
    print("[bdua] ✓ done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
