"""
Ingesta bronze: DANE EEVV Nacimientos (asistente para descarga manual).

Fuente oficial: DANE Estadísticas Vitales — Nacimientos.
Portal: https://microdatos.dane.gov.co/index.php/catalog/MICRODATOS
       (no tiene API pública estable de microdata; descarga es manual)

Procedimiento de descarga: ver `docs/mme/dane-eevv-procedure.md`.

Este script lee CSV/Excel descargados y dejados en `data/mme/staging/dane_eevv/`
(uno por año, p.ej. `nacimientos_2016.csv`), los normaliza, agrega por
`cod_mpio × año` y escribe particionado en
`data/mme/bronze/dane/eevv/year=YYYY/part-0000.parquet`.

Uso:
  uv run python scripts/mme/ingest_dane_eevv_bronze.py [--input-dir PATH] [--dry-run]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

from _paths import REPO_ROOT, MME_DATA
DEFAULT_STAGING = MME_DATA / "staging" / "dane_eevv"
BRONZE_DIR = MME_DATA / "bronze" / "dane" / "eevv"
MANIFEST_PATH = BRONZE_DIR / "_manifest.json"
YEAR_MIN, YEAR_MAX = 2016, 2022

# Mapeo flexible: cualquier alias case-insensitive cae al nombre canónico.
# DANE EEVV cambia un par de nombres entre 2016 y 2022; cubrimos los habituales.
COLUMN_ALIASES: dict[str, list[str]] = {
    "ano": ["ano", "año", "anio", "ano_nac", "anonac", "year"],
    "cod_dpto": [
        "coddpto", "cod_dpto", "cod_dane_dpto", "dpnac", "dp_nac",
        "departamento", "cod_dpto_residencia", "dpres", "codpdto", "cod_pdto",
    ],
    "cod_mpio": [
        "codmun", "cod_mun", "codmpio", "cod_mpio", "cod_dane_mpio",
        "cod_dane_mun", "mpnac", "mp_nac", "municipio", "cod_mun_residencia",
        "mpio_res", "mpres", "cod_mpio_residencia",
    ],
    # Aliases para construir el código DIVIPOLA si el archivo solo trae cod_dpto + cod_mpio_local
    "cod_mpio_completo": [
        "codigo_municipio", "cod_municipio", "div_codigo", "divipola", "cod_divipola",
    ],
    "edad_madre": ["edad_madre", "edadmadre", "edad_mad", "edad_de_la_madre", "edadm"],
    "n_consultas_prenatales": [
        "n_consul", "nconsul", "num_consultas", "n_consultas", "ncpn", "n_consultas_prenatales",
        "n_mero_consultas_prenatales",
    ],
    "tipo_parto": ["tipo_parto", "tipoparto", "t_parto", "tipo_de_parto"],
    "peso": ["peso", "peso_gramos", "peso_nacer", "peso_nacimiento"],
    "talla": ["talla", "talla_centimetros", "talla_cent_metros"],
    "tiempo_gestacion": [
        "t_ges", "tges", "tiempo_gestacion", "tiempo_de_gestacion", "tiempo_de_gestaci_n",
        "semanas_gestacion", "semgest",
    ],
    "area_nacimiento": [
        "areanac", "area_nac", "area", "area_nacimiento", "area_residencia",
    ],
    "regimen_seguridad": [
        "seg_social", "segsocial", "regimen", "regimen_seguridad",
        "r_gimen_seguridad_social", "r_gimen_seguridad",
    ],
    "etnia_madre": [
        "idpertet", "etnia", "etnia_madre", "pertenencia_etnica", "pertenencia_tnica",
    ],
    "multiplicidad_embarazo": [
        "multiplicidad_embarazo", "multiplicidad", "idclasem", "clase_embarazo",
    ],
    "sexo": ["sexo", "id_sexo"],
}

# Normalización de valores categóricos. Solo cuando el dato viene como código DANE estándar.
TIPO_PARTO_CESAREA = {2, "2", "CESAREA", "CESÁREA", "C"}
AREA_RURAL_DISPERSO = {3, "3", "RURAL DISPERSO", "RURAL_DISPERSO", "RURAL DISPERSA"}
REGIMEN_SUBSIDIADO = {2, "2", "SUBSIDIADO", "SUB"}
ETNIA_INDIGENA = {1, "1", "INDIGENA", "INDÍGENA"}
ETNIA_AFRO = {2, 3, 4, 5, "2", "3", "4", "5", "NEGRO", "AFRO", "PALENQUERO", "RAIZAL", "MULATO"}


def discover_files(input_dir: Path) -> list[Path]:
    """Descubre archivos CSV/Excel en el staging, ignorando .gitkeep y temporales."""
    if not input_dir.exists():
        return []
    extensions = {".csv", ".CSV", ".xlsx", ".xls", ".txt"}
    files = [
        p for p in sorted(input_dir.iterdir())
        if p.is_file() and p.suffix in extensions and not p.name.startswith(".")
    ]
    return files


def detect_year_from_filename(path: Path) -> int | None:
    """Busca un YYYY en el nombre del archivo (2016..2022)."""
    m = re.search(r"(20[12][0-9])", path.stem)
    if not m:
        return None
    y = int(m.group(1))
    return y if YEAR_MIN <= y <= YEAR_MAX else None


def load_dataframe(path: Path) -> pd.DataFrame:
    """Carga CSV (auto-detecta separador) o Excel."""
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path, dtype=str)
    # CSV: intentar separadores comunes (DANE suele usar ; o |)
    for sep in [",", ";", "|", "\t"]:
        try:
            df = pd.read_csv(path, sep=sep, dtype=str, low_memory=False, encoding="utf-8")
            if df.shape[1] > 1:
                return df
        except UnicodeDecodeError:
            try:
                df = pd.read_csv(path, sep=sep, dtype=str, low_memory=False, encoding="latin-1")
                if df.shape[1] > 1:
                    return df
            except Exception:
                continue
        except Exception:
            continue
    raise ValueError(f"No se pudo leer {path} con separadores comunes ,;|\\t")


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Renombra columnas a alias canónicos (case-insensitive, sin acentos)."""
    def slug(s: str) -> str:
        s = s.strip().lower()
        s = (
            s.replace("á", "a").replace("é", "e").replace("í", "i")
             .replace("ó", "o").replace("ú", "u").replace("ñ", "n")
        )
        s = re.sub(r"[^a-z0-9_]", "_", s)
        return re.sub(r"_+", "_", s).strip("_")

    rename: dict[str, str] = {}
    seen_canon: set[str] = set()
    slug_to_orig = {slug(c): c for c in df.columns}
    for canon, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            a = slug(alias)
            if a in slug_to_orig and canon not in seen_canon:
                rename[slug_to_orig[a]] = canon
                seen_canon.add(canon)
                break
    out = df.rename(columns=rename)
    out.columns = [slug(c) if c not in rename.values() else c for c in out.columns]
    return out


def to_int(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").astype("Int64")


def build_cod_mpio(df: pd.DataFrame) -> pd.Series:
    """Resuelve el código DIVIPOLA a 5 dígitos (cod_dpto*1000 + cod_mpio_local)."""
    if "cod_mpio_completo" in df.columns:
        s = pd.to_numeric(df["cod_mpio_completo"], errors="coerce").astype("Int64")
        if s.notna().any():
            return s
    if "cod_dpto" in df.columns and "cod_mpio" in df.columns:
        d = pd.to_numeric(df["cod_dpto"], errors="coerce").fillna(0).astype("Int64")
        m = pd.to_numeric(df["cod_mpio"], errors="coerce").fillna(0).astype("Int64")
        # Si cod_mpio ya viene como 5 dígitos completos (≥1000), respetar.
        full = m.where(m >= 1000, d * 1000 + m)
        return full.astype("Int64")
    if "cod_mpio" in df.columns:
        return pd.to_numeric(df["cod_mpio"], errors="coerce").astype("Int64")
    raise ValueError("No hay columnas para construir cod_mpio (busqué cod_mpio_completo / cod_dpto+cod_mpio / cod_mpio)")


def aggregate_by_muni_year(df: pd.DataFrame, year: int) -> pd.DataFrame:
    """Agrega por municipio: NV total + indicadores. Robusto a columnas faltantes."""
    df = df.copy()
    df["cod_mpio"] = build_cod_mpio(df)
    df = df.dropna(subset=["cod_mpio"])
    df["cod_mpio"] = df["cod_mpio"].astype("int64")

    # Indicadores derivados (solo si la columna existe; si no, NaN → no se cuenta).
    def safe_in(col: str, vals: set) -> pd.Series:
        if col not in df.columns:
            return pd.Series(False, index=df.index)
        return df[col].astype(str).str.upper().str.strip().isin({str(v).upper() for v in vals})

    edad = to_int(df["edad_madre"]) if "edad_madre" in df.columns else pd.Series(pd.NA, index=df.index, dtype="Int64")
    cpn = to_int(df["n_consultas_prenatales"]) if "n_consultas_prenatales" in df.columns else pd.Series(pd.NA, index=df.index, dtype="Int64")
    peso = to_int(df["peso"]) if "peso" in df.columns else pd.Series(pd.NA, index=df.index, dtype="Int64")
    tges = to_int(df["tiempo_gestacion"]) if "tiempo_gestacion" in df.columns else pd.Series(pd.NA, index=df.index, dtype="Int64")

    flags = pd.DataFrame({
        "cod_mpio": df["cod_mpio"],
        "_one": 1,
        "edad_madre_lt15": (edad.fillna(99) < 15).astype("int64"),
        "edad_madre_15_19": ((edad.fillna(0) >= 15) & (edad.fillna(0) <= 19)).astype("int64"),
        "edad_madre_gte35": (edad.fillna(0) >= 35).astype("int64"),
        "edad_madre_known": edad.notna().astype("int64"),
        "edad_madre_sum": edad.fillna(0).astype("int64"),
        "cpn_gte4": (cpn.fillna(0) >= 4).astype("int64"),
        "cpn_known": cpn.notna().astype("int64"),
        "cpn_sum": cpn.fillna(0).astype("int64"),
        "cesarea": safe_in("tipo_parto", TIPO_PARTO_CESAREA).astype("int64"),
        "rural_disperso": safe_in("area_nacimiento", AREA_RURAL_DISPERSO).astype("int64"),
        "subsidiado": safe_in("regimen_seguridad", REGIMEN_SUBSIDIADO).astype("int64"),
        "indigena_madre": safe_in("etnia_madre", ETNIA_INDIGENA).astype("int64"),
        "afro_madre": safe_in("etnia_madre", ETNIA_AFRO).astype("int64"),
        "bajo_peso": ((peso.fillna(99999) < 2500) & (peso.fillna(99999) > 0)).astype("int64"),
        "pretermino": ((tges.fillna(99) < 37) & (tges.fillna(99) > 0)).astype("int64"),
    })

    g = flags.groupby("cod_mpio", as_index=False).agg({
        "_one": "sum",
        "edad_madre_lt15": "sum",
        "edad_madre_15_19": "sum",
        "edad_madre_gte35": "sum",
        "edad_madre_known": "sum",
        "edad_madre_sum": "sum",
        "cpn_gte4": "sum",
        "cpn_known": "sum",
        "cpn_sum": "sum",
        "cesarea": "sum",
        "rural_disperso": "sum",
        "subsidiado": "sum",
        "indigena_madre": "sum",
        "afro_madre": "sum",
        "bajo_peso": "sum",
        "pretermino": "sum",
    })
    g = g.rename(columns={"_one": "nv_total"})

    # Promedios condicionales (evitan división por cero)
    g["edad_madre_avg"] = (g["edad_madre_sum"] / g["edad_madre_known"].replace(0, pd.NA)).round(2)
    g["cpn_avg"] = (g["cpn_sum"] / g["cpn_known"].replace(0, pd.NA)).round(2)
    g = g.drop(columns=["edad_madre_sum", "edad_madre_known", "cpn_sum", "cpn_known"])

    g.insert(0, "ano", int(year))
    g["nv_total"] = g["nv_total"].astype("int64")
    return g


def write_partitioned(df: pd.DataFrame, year: int) -> Path:
    out_dir = BRONZE_DIR / f"year={year}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "part-0000.parquet"
    con = duckdb.connect(":memory:")
    con.register("agg", df)
    con.execute(f"COPY (SELECT * FROM agg) TO '{out_path}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    con.close()
    return out_path


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingesta bronze DANE EEVV nacimientos.")
    ap.add_argument("--input-dir", type=Path, default=DEFAULT_STAGING,
                    help=f"Carpeta con CSV/Excel descargados (default: {DEFAULT_STAGING})")
    ap.add_argument("--dry-run", action="store_true",
                    help="Procesa y reporta pero no escribe parquet ni manifest.")
    args = ap.parse_args()

    input_dir: Path = args.input_dir
    files = discover_files(input_dir)
    if not files:
        print(f"[eevv] ⚠ no hay archivos en {input_dir if input_dir.is_relative_to(REPO_ROOT) else input_dir}")
        print("[eevv] ver docs/mme/dane-eevv-procedure.md para el procedimiento de descarga.")
        return 0

    print(f"[eevv] {len(files)} archivo(s) en staging:")
    for p in files:
        print(f"   - {p.name}")

    BRONZE_DIR.mkdir(parents=True, exist_ok=True)
    rows_per_year: dict[int, int] = {}
    files_meta: list[dict] = []

    for path in files:
        year = detect_year_from_filename(path)
        df_raw = load_dataframe(path)
        df = normalize_columns(df_raw)
        if year is None and "ano" in df.columns:
            ys = pd.to_numeric(df["ano"], errors="coerce").dropna().astype(int).unique().tolist()
            ys = [y for y in ys if YEAR_MIN <= y <= YEAR_MAX]
            year = ys[0] if len(ys) == 1 else None
        if year is None:
            print(f"[eevv] ⚠ {path.name}: no pude detectar año (ni en nombre ni en columna 'ano'). Saltando.", file=sys.stderr)
            continue

        agg = aggregate_by_muni_year(df, year)
        n_muni = len(agg)
        n_nv = int(agg["nv_total"].sum())
        rows_per_year[year] = n_nv
        files_meta.append({
            "filename": path.name,
            "year": year,
            "input_rows": int(len(df_raw)),
            "input_cols": int(df_raw.shape[1]),
            "muni_aggregated": n_muni,
            "nv_total": n_nv,
            "input_sha256": sha256_of_file(path),
            "detected_columns": sorted(df.columns.tolist()),
        })
        print(f"[eevv] {path.name}: año={year} input={len(df_raw):,} → muni={n_muni:,} NV={n_nv:,}")

        if not args.dry_run:
            out = write_partitioned(agg, year)
            print(f"[eevv]   wrote {out}")

    if args.dry_run:
        print("[eevv] dry-run: no se escribió nada.")
        return 0

    if not files_meta:
        print("[eevv] ⚠ no se procesó ningún archivo válido.", file=sys.stderr)
        return 1

    manifest = {
        "source": {
            "portal": "microdatos.dane.gov.co",
            "provider": "DANE — Estadísticas Vitales (EEVV)",
            "dataset_name": "Nacimientos",
            "url": "https://microdatos.dane.gov.co/index.php/catalog/MICRODATOS",
            "ingestion_mode": "manual_download_then_ingest",
            "procedure_doc": "docs/mme/dane-eevv-procedure.md",
        },
        "ingested_at_utc": datetime.now(timezone.utc).isoformat(),
        "year_range": [YEAR_MIN, YEAR_MAX],
        "row_count_per_year": {str(k): v for k, v in sorted(rows_per_year.items())},
        "files": files_meta,
        "notes": [
            "Bronze EEVV = agregado por (cod_mpio, ano), un parquet por año.",
            "nv_total = COUNT(*) de registros individuales por municipio.",
            "Indicadores: cesarea, cpn_gte4, rural_disperso, subsidiado, indigena/afro_madre, bajo_peso, pretermino, edad_madre_*.",
            "Si el archivo no trae alguna columna fuente, el indicador queda en 0 (no NULL) — verificar en _manifest.detected_columns.",
            "cod_mpio = código DIVIPOLA 5 dígitos (cod_dpto*1000 + cod_mpio_local) si vienen separados.",
        ],
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"[eevv] ✓ manifest → {MANIFEST_PATH}")
    print(f"[eevv] total NV ingeridos: {sum(rows_per_year.values()):,} en {len(rows_per_year)} año(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
