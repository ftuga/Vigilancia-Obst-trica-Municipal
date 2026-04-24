"""
Ingesta bronze: dataset SIVIGILA histórico Colombia (datos.gov.co Socrata).

Fuente oficial: `4hyg-wa9d` — "Datos de Vigilancia en Salud Pública de Colombia 2007-2024"
Publisher: Instituto Nacional de Salud (INS)

Filtro: cod_eve = 549 (Morbilidad Materna Extrema) AND ano >= 2016.
Ventana 2016-2024 justificada en docs/research-mme.md (estabilidad de protocolo 549).

Output:
  data/mme/bronze/year=YYYY/part-0000.parquet         (particionado Hive)
  data/mme/bronze/_manifest.json                      (metadata de ingesta)

Uso:
  uv run python scripts/mme/ingest_sivigila_bronze.py
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
EVENT_CODE = "549"
YEAR_MIN = 2016
PAGE_SIZE = 50_000  # Max Socrata
TIMEOUT = 60

from _paths import REPO_ROOT, MME_DATA
BRONZE_DIR = MME_DATA / "bronze"
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
    """Cast mínimo en bronze: solo tipos, sin limpieza semántica. Esa va en silver."""
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
    """Escribe parquet particionado por year=YYYY usando DuckDB."""
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
    """Hash estable del contenido (filas ordenadas + columnas). Idempotencia y trazabilidad."""
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
            "event_name_expected": "MORBILIDAD MATERNA EXTREMA",
            "year_min": YEAR_MIN,
        },
        "ingested_at_utc": datetime.now(timezone.utc).isoformat(),
        "schema": sorted(df.columns.tolist()),
        "row_count_total": int(len(df)),
        "row_count_per_year": {str(k): v for k, v in sorted(rows_per_year.items())},
        "content_sha256": sha256_of_dataframe(df),
        "notes": [
            "Bronze = raw INS + cast de tipos, sin limpieza semántica",
            "Partición Hive: year=YYYY",
            "Compresión ZSTD vía DuckDB",
            "Ventana 2016-2024: ver docs/research-mme.md §3.4",
        ],
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"  manifest → {MANIFEST_PATH}")


def main() -> int:
    print(f"[bronze ingest] SIVIGILA {DATASET_ID} — evento {EVENT_CODE} (MME) desde {YEAR_MIN}")
    print(f"[bronze ingest] endpoint: {BASE_URL}")

    print("[bronze ingest] fetching...")
    df = fetch_all()
    if df.empty:
        print("[bronze ingest] ⚠ dataset vacío — abortar", file=sys.stderr)
        return 2

    print(f"[bronze ingest] total rows fetched: {len(df):,}")
    print(f"[bronze ingest] schema: {df.columns.tolist()}")

    df = normalize_types(df)

    unique_event_names = df["nombre_evento"].dropna().unique().tolist() if "nombre_evento" in df else []
    print(f"[bronze ingest] event names in result: {unique_event_names}")
    if unique_event_names and not all("MORBILIDAD MATERNA" in s.upper() for s in unique_event_names):
        print("[bronze ingest] ⚠ ADVERTENCIA: hay eventos que no son MME en el resultado", file=sys.stderr)

    print("[bronze ingest] writing partitioned parquet...")
    rows_per_year = write_partitioned(df)

    print("[bronze ingest] writing manifest...")
    write_manifest(df, rows_per_year)

    print("[bronze ingest] ✓ done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
