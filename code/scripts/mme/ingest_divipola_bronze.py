"""
Ingesta bronze: DIVIPOLA (División Político-Administrativa de Colombia).

Fuente oficial: DANE — corte 30 diciembre 2024.
  - `gdxc-w37w`  DIVIPOLA Municipios
  - `vcjz-niiq`  DIVIPOLA Departamentos

Uso en el pipeline:
  - Catálogo canónico para join con SIVIGILA (códigos municipio 5 dígitos).
  - Identificación de municipios silentes (en DIVIPOLA pero ausentes en bronze MME).
  - Normalización de nombres y códigos en silver.

Output:
  data/mme/bronze/divipola/municipios.parquet
  data/mme/bronze/divipola/departamentos.parquet
  data/mme/bronze/divipola/_manifest.json

Uso:
  uv run python scripts/mme/ingest_divipola_bronze.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd
import requests

DATASETS = {
    "municipios": {
        "id": "gdxc-w37w",
        "description": "DIVIPOLA municipios corte 30-dic-2024",
    },
    "departamentos": {
        "id": "vcjz-niiq",
        "description": "DIVIPOLA departamentos corte 30-dic-2024",
    },
}

from _paths import REPO_ROOT, MME_DATA
OUT_DIR = MME_DATA / "bronze" / "divipola"
PAGE_SIZE = 50_000
TIMEOUT = 60


def fetch_all(dataset_id: str) -> list[dict]:
    url = f"https://www.datos.gov.co/resource/{dataset_id}.json"
    offset = 0
    rows: list[dict] = []
    while True:
        r = requests.get(url, params={"$limit": PAGE_SIZE, "$offset": offset}, timeout=TIMEOUT)
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return rows


def write_parquet(df: pd.DataFrame, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Socrata JSON → object dtype puede romper duckdb.register en pandas 3.x
    # Forzamos string_ explícito por columna (todas las columnas DIVIPOLA son categóricas/códigos).
    for c in df.columns:
        df[c] = df[c].astype("string")
    con = duckdb.connect(":memory:")
    con.register("t", df)
    con.execute(f"COPY t TO '{out_path}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    con.close()


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "ingested_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_portal": "datos.gov.co",
        "provider": "DANE",
        "cut_off": "2024-12-30",
        "datasets": {},
    }

    for name, meta in DATASETS.items():
        print(f"[divipola] fetching {name} ({meta['id']})...")
        rows = fetch_all(meta["id"])
        if not rows:
            print(f"[divipola] ⚠ {name} vacío", file=sys.stderr)
            return 2
        df = pd.DataFrame(rows)
        out_path = OUT_DIR / f"{name}.parquet"
        write_parquet(df, out_path)
        print(f"  rows={len(df):,}, cols={len(df.columns)}, schema={df.columns.tolist()}")
        print(f"  → {out_path}")

        manifest["datasets"][name] = {
            "dataset_id": meta["id"],
            "description": meta["description"],
            "row_count": int(len(df)),
            "schema": df.columns.tolist(),
        }

    (OUT_DIR / "_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"[divipola] ✓ manifest → {(OUT_DIR / '_manifest.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
