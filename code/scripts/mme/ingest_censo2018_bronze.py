"""
Ingesta bronze: DANE Censo 2018 — Necesidades Básicas Insatisfechas (NBI) por municipio.

Fuente oficial: DANE, Censo Nacional de Población y Vivienda (CNPV) 2018.
URL directa:    https://www.dane.gov.co/files/censo2018/informacion-tecnica/CNPV-2018-NBI.xlsx
Publisher:      Departamento Administrativo Nacional de Estadística (DANE)

El xlsx publicado por DANE trae 3 hojas (Departamento_OLD / Departamento / Municipios).
Parseamos `Municipios`: 5 componentes NBI (vivienda, servicios, hacinamiento,
inasistencia escolar, dependencia económica) × 4 escalas geográficas (total,
cabecera, centros poblados y rural disperso, resto).

Output:
  data/mme/bronze/censo2018/nbi_municipios.parquet
  data/mme/bronze/censo2018/_raw/CNPV-2018-NBI.xlsx
  data/mme/bronze/censo2018/_manifest.json

Uso:
  uv run python scripts/mme/ingest_censo2018_bronze.py [--force-download]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd
import requests

from _paths import REPO_ROOT, MME_DATA
BRONZE_DIR = MME_DATA / "bronze" / "censo2018"
RAW_DIR = BRONZE_DIR / "_raw"
NBI_XLSX_URL = "https://www.dane.gov.co/files/censo2018/informacion-tecnica/CNPV-2018-NBI.xlsx"
NBI_XLSX_PATH = RAW_DIR / "CNPV-2018-NBI.xlsx"
NBI_PARQUET = BRONZE_DIR / "nbi_municipios.parquet"
MANIFEST_PATH = BRONZE_DIR / "_manifest.json"
HTTP_TIMEOUT = 90


def download_nbi(force: bool = False) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if NBI_XLSX_PATH.exists() and not force:
        print(f"[censo2018] reuse cache: {NBI_XLSX_PATH}")
        return NBI_XLSX_PATH
    print(f"[censo2018] GET {NBI_XLSX_URL}")
    r = requests.get(NBI_XLSX_URL, timeout=HTTP_TIMEOUT, allow_redirects=True)
    r.raise_for_status()
    NBI_XLSX_PATH.write_bytes(r.content)
    print(f"[censo2018] saved {len(r.content):,} bytes → {NBI_XLSX_PATH}")
    return NBI_XLSX_PATH


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_municipios_sheet(xlsx_path: Path) -> pd.DataFrame:
    """Parsea la hoja 'Municipios' con su header de 2 niveles.

    Layout real verificado 2026-04-23 sobre CNPV-2018-NBI.xlsx (FIX: había 7 cols por
    grupo, no 6 — el archivo incluye 'Prop de Personas en miseria' entre el índice
    total y los 5 componentes; un parseo inicial ignoró esa col y corrió todo el
    mapeo un lugar, desviando cabecera/rural):

      Filas 7-9: encabezados multi-nivel.
      Fila 10+:  data.
      Cols:
        0: Código Departamento
        1: Nombre Departamento
        2: Código Municipio  (local, 3 dígitos)
        3: Nombre Municipio
        [Grupo 1 — Total]
        4: NBI Prop de Personas (%)              → nbi_total_pct
        5: Prop de Personas en miseria           → nbi_miseria_pct
        6: Componente vivienda                   → nbi_vivienda_pct
        7: Componente servicios                  → nbi_servicios_pct
        8: Componente hacinamiento               → nbi_hacinamiento_pct
        9: Componente inasistencia               → nbi_inasistencia_pct
       10: Componente dependencia económica      → nbi_dependencia_pct
        [Grupo 2 — Cabeceras]
       11: NBI Prop de Personas (%)              → nbi_cabecera_pct
       12: miseria (cabecera)
       13-17: componentes (cabecera)
        [Grupo 3 — Centros poblados y rural disperso]
       18: NBI Prop de Personas (%)              → nbi_centros_rural_disperso_pct
       19: miseria (rural)
       20-24: componentes (rural)
    """
    df = pd.read_excel(xlsx_path, sheet_name="Municipios", header=None, dtype=object)
    data = df.iloc[10:].reset_index(drop=True).copy()
    data = data.dropna(subset=[0, 2], how="any")

    out = pd.DataFrame({
        "cod_dpto": pd.to_numeric(data[0], errors="coerce").astype("Int64"),
        "nom_dpto": data[1].astype("string").str.strip(),
        "_cod_mpio_local": pd.to_numeric(data[2], errors="coerce").astype("Int64"),
        "nom_mpio": data[3].astype("string").str.strip(),
        "nbi_total_pct":          pd.to_numeric(data[4],  errors="coerce"),
        "nbi_miseria_pct":        pd.to_numeric(data[5],  errors="coerce"),
        "nbi_vivienda_pct":       pd.to_numeric(data[6],  errors="coerce"),
        "nbi_servicios_pct":      pd.to_numeric(data[7],  errors="coerce"),
        "nbi_hacinamiento_pct":   pd.to_numeric(data[8],  errors="coerce"),
        "nbi_inasistencia_pct":   pd.to_numeric(data[9],  errors="coerce"),
        "nbi_dependencia_pct":    pd.to_numeric(data[10], errors="coerce"),
        "nbi_cabecera_pct":       pd.to_numeric(data[11], errors="coerce"),
        "nbi_centros_rural_disperso_pct": pd.to_numeric(data[18], errors="coerce"),
    })
    out = out.dropna(subset=["cod_dpto", "_cod_mpio_local", "nbi_total_pct"])
    out["cod_mpio"] = (out["cod_dpto"].astype("int64") * 1000 + out["_cod_mpio_local"].astype("int64")).astype("int64")
    out = out.drop(columns=["_cod_mpio_local"])
    cols = [
        "cod_mpio", "cod_dpto", "nom_dpto", "nom_mpio",
        "nbi_total_pct", "nbi_miseria_pct",
        "nbi_vivienda_pct", "nbi_servicios_pct", "nbi_hacinamiento_pct",
        "nbi_inasistencia_pct", "nbi_dependencia_pct",
        "nbi_cabecera_pct", "nbi_centros_rural_disperso_pct",
    ]
    out = out[cols]
    out["cod_dpto"] = out["cod_dpto"].astype("int64")
    return out.reset_index(drop=True)


def write_bronze(df: pd.DataFrame) -> None:
    BRONZE_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(":memory:")
    con.register("nbi", df)
    con.execute(
        f"COPY (SELECT * FROM nbi ORDER BY cod_mpio) TO '{NBI_PARQUET}' "
        f"(FORMAT PARQUET, COMPRESSION ZSTD)"
    )
    con.close()
    print(f"[censo2018] wrote {NBI_PARQUET} ({len(df):,} municipios)")


def write_manifest(df: pd.DataFrame, xlsx_sha: str, xlsx_size: int) -> None:
    manifest = {
        "source": {
            "provider": "Departamento Administrativo Nacional de Estadística (DANE)",
            "dataset_name": "CNPV 2018 — Necesidades Básicas Insatisfechas por municipio",
            "url": NBI_XLSX_URL,
            "raw_file": str(NBI_XLSX_PATH),
            "raw_sha256": xlsx_sha,
            "raw_size_bytes": xlsx_size,
        },
        "ingested_at_utc": datetime.now(timezone.utc).isoformat(),
        "n_municipios": int(len(df)),
        "n_departamentos": int(df["cod_dpto"].nunique()),
        "schema": list(df.columns),
        "summary_stats": {
            "nbi_total_pct_mean": round(float(df["nbi_total_pct"].mean()), 3),
            "nbi_total_pct_median": round(float(df["nbi_total_pct"].median()), 3),
            "nbi_total_pct_min": round(float(df["nbi_total_pct"].min()), 3),
            "nbi_total_pct_max": round(float(df["nbi_total_pct"].max()), 3),
            "top5_nbi_muni": df.nlargest(5, "nbi_total_pct")[["cod_mpio", "nom_mpio", "nom_dpto", "nbi_total_pct"]]
                              .to_dict(orient="records"),
        },
        "notes": [
            "NBI Censo 2018 = % de personas con al menos 1 de 5 componentes insatisfechos",
            "Escalas: Total nacional + Cabecera urbana + Centros poblados y rural disperso",
            "cod_mpio = código DIVIPOLA 5 dígitos (cod_dpto × 1000 + cod_mpio_local)",
            "Feature temporalmente invariante: mismo valor repetido en panel 2016-2022",
        ],
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str))
    print(f"[censo2018] manifest → {MANIFEST_PATH}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingesta bronze DANE Censo 2018 NBI por municipio.")
    ap.add_argument("--force-download", action="store_true",
                    help="Fuerza redescarga aunque el xlsx ya esté en cache.")
    args = ap.parse_args()

    xlsx_path = download_nbi(force=args.force_download)
    xlsx_sha = sha256_of_file(xlsx_path)
    xlsx_size = xlsx_path.stat().st_size

    print("[censo2018] parseando hoja 'Municipios'...")
    df = parse_municipios_sheet(xlsx_path)
    print(f"[censo2018] {len(df):,} municipios · {df['cod_dpto'].nunique()} departamentos")
    print(f"[censo2018] NBI total — mean={df['nbi_total_pct'].mean():.2f}% "
          f"median={df['nbi_total_pct'].median():.2f}% "
          f"max={df['nbi_total_pct'].max():.2f}%")

    write_bronze(df)
    write_manifest(df, xlsx_sha, xlsx_size)
    print("[censo2018] ✓ done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
