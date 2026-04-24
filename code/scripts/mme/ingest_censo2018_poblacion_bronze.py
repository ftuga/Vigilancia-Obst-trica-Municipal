"""
Ingesta bronze: DANE Censo 2018 — Población ajustada por cobertura (muni × zona).

Fuente oficial: DANE, Censo Nacional de Población y Vivienda (CNPV) 2018.
URL directa:    https://www.dane.gov.co/files/censo2018/informacion-tecnica/CNPV-2018-Poblacion-Ajustada-por-Cobertura.xls

Del archivo extraemos la hoja 'Ajuste por Cobertura CNPV Mpios' con población municipal
ajustada 2018: total, cabecera urbana, centros poblados y rural disperso, más la
omisión censal estimada (proxy de cobertura censal). Derivamos `pct_rural_pobl` como
feature directa de Demora II (barreras geográficas de acceso).

Output:
  data/mme/bronze/censo2018/poblacion_municipios.parquet
  data/mme/bronze/censo2018/_raw/CNPV-2018-Poblacion-Ajustada-por-Cobertura.xls
  data/mme/bronze/censo2018/_manifest_poblacion.json

Uso:
  uv run python scripts/mme/ingest_censo2018_poblacion_bronze.py [--force-download]
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
XLS_URL = (
    "https://www.dane.gov.co/files/censo2018/informacion-tecnica/"
    "CNPV-2018-Poblacion-Ajustada-por-Cobertura.xls"
)
XLS_PATH = RAW_DIR / "CNPV-2018-Poblacion-Ajustada-por-Cobertura.xls"
POBL_PARQUET = BRONZE_DIR / "poblacion_municipios.parquet"
MANIFEST_PATH = BRONZE_DIR / "_manifest_poblacion.json"
HTTP_TIMEOUT = 90


def download(force: bool = False) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if XLS_PATH.exists() and not force:
        print(f"[censo-pobl] reuse cache: {XLS_PATH}")
        return XLS_PATH
    print(f"[censo-pobl] GET {XLS_URL}")
    r = requests.get(XLS_URL, timeout=HTTP_TIMEOUT, allow_redirects=True)
    r.raise_for_status()
    XLS_PATH.write_bytes(r.content)
    print(f"[censo-pobl] saved {len(r.content):,} bytes")
    return XLS_PATH


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_municipios(xls_path: Path) -> pd.DataFrame:
    """Parsea 'Ajuste por Cobertura CNPV Mpios'.

    Layout real (fila 8 = headers, fila 9+ = data):
       col 0: Código DIVIPOLA (5 dígitos como '05001')
       col 1: NOMBRE DEPARTAMENTO
       col 2: NOMBRE MUNICIPIO
       col 3: POBLACIÓN TOTAL ajustada
       col 4: POBLACIÓN CABECERA ajustada
       col 5: POBLACIÓN CENTROS POBLADOS Y RURAL DISPERSO
       col 6: OMISIÓN CENSAL TOTAL (fracción 0..1)
       col 7: OMISIÓN CENSAL CABECERA
       col 8: OMISIÓN CENSAL CENTROS POBLADOS Y RURAL DISPERSO
    """
    df = pd.read_excel(xls_path, sheet_name="Ajuste por Cobertura CNPV Mpios",
                       header=None, dtype=object)
    data = df.iloc[9:].reset_index(drop=True).copy()
    data = data.dropna(subset=[0, 3], how="any")

    cod_raw = data[0].astype(str).str.strip()
    cod_mpio = pd.to_numeric(cod_raw, errors="coerce").astype("Int64")

    out = pd.DataFrame({
        "cod_mpio":             cod_mpio,
        "nom_dpto":             data[1].astype("string").str.strip(),
        "nom_mpio":             data[2].astype("string").str.strip(),
        "poblacion_total_2018": pd.to_numeric(data[3], errors="coerce").astype("Int64"),
        "poblacion_cabecera_2018":    pd.to_numeric(data[4], errors="coerce").astype("Int64"),
        "poblacion_centros_rural_2018": pd.to_numeric(data[5], errors="coerce").astype("Int64"),
        "omision_censal_total":        pd.to_numeric(data[6], errors="coerce"),
        "omision_censal_cabecera":     pd.to_numeric(data[7], errors="coerce"),
        "omision_censal_centros_rural": pd.to_numeric(data[8], errors="coerce"),
    })
    out = out.dropna(subset=["cod_mpio", "poblacion_total_2018"])

    # Features derivadas
    out["pct_rural_pobl"] = (
        out["poblacion_centros_rural_2018"] / out["poblacion_total_2018"] * 100.0
    ).round(3)
    out["pct_cabecera_pobl"] = (
        out["poblacion_cabecera_2018"] / out["poblacion_total_2018"] * 100.0
    ).round(3)

    # cod_dpto derivado (primeros 2 dígitos de DIVIPOLA)
    out["cod_dpto"] = (out["cod_mpio"] // 1000).astype("int64")
    out["cod_mpio"] = out["cod_mpio"].astype("int64")

    cols = [
        "cod_mpio", "cod_dpto", "nom_dpto", "nom_mpio",
        "poblacion_total_2018", "poblacion_cabecera_2018", "poblacion_centros_rural_2018",
        "pct_rural_pobl", "pct_cabecera_pobl",
        "omision_censal_total", "omision_censal_cabecera", "omision_censal_centros_rural",
    ]
    return out[cols].reset_index(drop=True)


def write_bronze(df: pd.DataFrame) -> None:
    BRONZE_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(":memory:")
    con.register("pobl", df)
    con.execute(
        f"COPY (SELECT * FROM pobl ORDER BY cod_mpio) TO '{POBL_PARQUET}' "
        f"(FORMAT PARQUET, COMPRESSION ZSTD)"
    )
    con.close()
    print(f"[censo-pobl] wrote {POBL_PARQUET} ({len(df):,} municipios)")


def write_manifest(df: pd.DataFrame, xls_sha: str, xls_size: int) -> None:
    manifest = {
        "source": {
            "provider": "Departamento Administrativo Nacional de Estadística (DANE)",
            "dataset_name": "CNPV 2018 — Población ajustada por cobertura por municipio",
            "url": XLS_URL,
            "raw_file": str(XLS_PATH),
            "raw_sha256": xls_sha,
            "raw_size_bytes": xls_size,
        },
        "ingested_at_utc": datetime.now(timezone.utc).isoformat(),
        "n_municipios": int(len(df)),
        "n_departamentos": int(df["cod_dpto"].nunique()),
        "schema": list(df.columns),
        "summary_stats": {
            "poblacion_nacional_2018": int(df["poblacion_total_2018"].sum()),
            "pct_rural_pobl_mean":     round(float(df["pct_rural_pobl"].mean()),    2),
            "pct_rural_pobl_median":   round(float(df["pct_rural_pobl"].median()),  2),
            "top5_rural_muni":         df.nlargest(5, "pct_rural_pobl")[
                ["cod_mpio", "nom_mpio", "nom_dpto", "pct_rural_pobl", "poblacion_total_2018"]
            ].to_dict(orient="records"),
            "top5_urbano_muni":        df.nsmallest(5, "pct_rural_pobl")[
                ["cod_mpio", "nom_mpio", "nom_dpto", "pct_rural_pobl", "poblacion_total_2018"]
            ].to_dict(orient="records"),
        },
        "notes": [
            "Población ajustada CNPV 2018 con omisión censal estimada por DANE",
            "pct_rural_pobl = centros poblados y rural disperso / total × 100",
            "cod_mpio = DIVIPOLA 5 dígitos",
            "Feature temporalmente invariante en el panel 2016-2022 (proyecciones separadas en M-004)",
            "omision_censal_* útil como feature anti-sesgo de cobertura (censo 2018 tuvo 8.5% omisión nacional)",
        ],
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str))
    print(f"[censo-pobl] manifest → {MANIFEST_PATH}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingesta bronze DANE Censo 2018 población ajustada por muni.")
    ap.add_argument("--force-download", action="store_true")
    args = ap.parse_args()

    xls_path = download(force=args.force_download)
    xls_sha = sha256_of_file(xls_path)
    xls_size = xls_path.stat().st_size

    print("[censo-pobl] parseando hoja 'Ajuste por Cobertura CNPV Mpios'...")
    df = parse_municipios(xls_path)
    print(f"[censo-pobl] {len(df):,} municipios · {df['cod_dpto'].nunique()} departamentos")
    print(f"[censo-pobl] población nacional 2018: {int(df['poblacion_total_2018'].sum()):,}")
    print(f"[censo-pobl] pct_rural_pobl — mean={df['pct_rural_pobl'].mean():.2f}% "
          f"median={df['pct_rural_pobl'].median():.2f}% "
          f"max={df['pct_rural_pobl'].max():.2f}%")

    write_bronze(df)
    write_manifest(df, xls_sha, xls_size)
    print("[censo-pobl] ✓ done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
