"""
Ingesta bronze: SIVIGILA evento 550 — MORTALIDAD MATERNA.

Fuente oficial: `4hyg-wa9d` — "Datos de Vigilancia en Salud Pública de Colombia 2007-2024"
Publisher: Instituto Nacional de Salud (INS)

Filtro: cod_eve = 550 (Mortalidad Materna — agrupa directa e indirecta en este dataset)
AND ano >= 2016. Ventana 2016-2024 alineada con protocolo (estabilidad de criterios).

Nota: `4hyg-wa9d` publica el evento 550 unificado (~3.530 filas 2016-2024).
La desagregación directa (550) vs indirecta (551) a nivel individual requiere microdata INS
con trámite. Para C3 la razón MM/100.000 NV y el índice de letalidad MM/MME usan el total.

Output:
  data/mme/bronze/sivigila_mm/year=YYYY/part-0000.parquet
  data/mme/bronze/sivigila_mm/_manifest.json

Uso:
  uv run python scripts/mme/ingest_sivigila_mm_bronze.py
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

DATASET_ID = "4hyg-wa9d"
BASE_URL = f"https://www.datos.gov.co/resource/{DATASET_ID}.json"
EVENT_CODE = "550"
YEAR_MIN = 2016
PAGE_SIZE = 50_000
TIMEOUT = 60

from _paths import REPO_ROOT, MME_DATA
BRONZE_DIR = MME_DATA / "bronze" / "sivigila_mm"
MANIFEST_PATH = BRONZE_DIR / "_manifest.json"


def fetch_page(offset: int) -> list[dict]:
    params = {
        "$where": f"cod_eve='{EVENT_CODE}' AND ano>={YEAR_MIN}",
        "$limit": PAGE_SIZE,
        "$offset": offset,
        "$order": "ano,semana,cod_dpto_o,cod_mun_o",
    }
    r = requests.get(BASE_URL, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def fetch_all() -> pd.DataFrame:
    offset = 0
    pages: list[list[dict]] = []
    while True:
        t0 = time.perf_counter()
        batch = fetch_page(offset)
        dt = time.perf_counter() - t0
        n = len(batch)
        print(f"  [page offset={offset:>7}] rows={n:>5} in {dt:.2f}s", flush=True)
        if n == 0:
            break
        pages.append(batch)
        if n < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    flat = [row for page in pages for row in page]
    return pd.DataFrame(flat)


def normalize_types(df: pd.DataFrame) -> pd.DataFrame:
    int_cols = ["cod_eve", "semana", "ano", "cod_dpto_o", "cod_mun_o", "conteo"]
    for c in int_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    str_cols = ["nombre_evento", "departamento_ocurrencia", "municipio_ocurrencia"]
    for c in str_cols:
        if c in df.columns:
            df[c] = df[c].astype("string")
    return df


def write_partitioned(df: pd.DataFrame) -> dict[int, int]:
    BRONZE_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(":memory:")
    con.register("raw", df)
    rows_per_year: dict[int, int] = {}
    for year in sorted(df["ano"].dropna().unique()):
        year = int(year)
        out_dir = BRONZE_DIR / f"year={year}"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "part-0000.parquet"
        con.execute(
            f"COPY (SELECT * FROM raw WHERE ano = {year}) "
            f"TO '{out_path}' (FORMAT PARQUET, COMPRESSION ZSTD)"
        )
        rows_per_year[year] = int((df["ano"] == year).sum())
        print(f"  wrote {out_path} ({rows_per_year[year]} rows)")
    con.close()
    return rows_per_year


def sha256_of_dataframe(df: pd.DataFrame) -> str:
    h = hashlib.sha256()
    for row in df.itertuples(index=False, name=None):
        h.update(repr(row).encode("utf-8"))
    return h.hexdigest()


def write_manifest(df: pd.DataFrame, rows_per_year: dict[int, int]) -> None:
    manifest = {
        "source": {
            "portal": "datos.gov.co",
            "provider": "Instituto Nacional de Salud (INS)",
            "dataset_id": DATASET_ID,
            "dataset_name": "Datos de Vigilancia en Salud Pública de Colombia",
            "api": BASE_URL,
        },
        "filter": {
            "cod_eve": EVENT_CODE,
            "event_name_expected": "MORTALIDAD MATERNA",
            "year_min": YEAR_MIN,
        },
        "ingested_at_utc": datetime.now(timezone.utc).isoformat(),
        "schema": sorted(df.columns.tolist()),
        "row_count_total": int(len(df)),
        "row_count_per_year": {str(k): v for k, v in sorted(rows_per_year.items())},
        "casos_mm_por_ano": {
            str(y): int(df.loc[df["ano"] == y, "conteo"].sum())
            for y in sorted(df["ano"].dropna().unique())
        },
        "content_sha256": sha256_of_dataframe(df),
        "notes": [
            "Bronze = raw INS + cast de tipos, sin limpieza semántica",
            "Evento 550 consolidado (directa + indirecta juntas en 4hyg-wa9d)",
            "Partición Hive: year=YYYY",
            "Compresión ZSTD vía DuckDB",
            "Referencia INS: RMM Colombia ~50/100.000 NV (PAREMM v5 target ~40)",
        ],
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"  manifest → {MANIFEST_PATH}")


def main() -> int:
    print(f"[bronze-mm] SIVIGILA {DATASET_ID} — evento {EVENT_CODE} (Mortalidad Materna) desde {YEAR_MIN}")
    print(f"[bronze-mm] endpoint: {BASE_URL}")

    print("[bronze-mm] fetching...")
    df = fetch_all()
    if df.empty:
        print("[bronze-mm] ⚠ dataset vacío — abortar", file=sys.stderr)
        return 2

    print(f"[bronze-mm] total rows fetched: {len(df):,}")
    df = normalize_types(df)

    unique_event_names = df["nombre_evento"].dropna().unique().tolist() if "nombre_evento" in df else []
    print(f"[bronze-mm] event names in result: {unique_event_names}")
    total_casos = int(df["conteo"].sum()) if "conteo" in df.columns else 0
    print(f"[bronze-mm] suma de casos reportados: {total_casos:,}")

    print("[bronze-mm] writing partitioned parquet...")
    rows_per_year = write_partitioned(df)

    print("[bronze-mm] writing manifest...")
    write_manifest(df, rows_per_year)

    print("[bronze-mm] ✓ done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
