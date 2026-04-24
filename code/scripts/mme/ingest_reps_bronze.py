"""
Ingesta bronze: REPS MinSalud — IPS por nivel + capacidad instalada por municipio.

Dos datasets nacionales públicos (no regionales, no requieren trámite):

1. `ugc5-acjp` (11.466 filas) — "Listado de IPS en Colombia según su nivel de complejidad"
   Variables clave: `nivel` (1/2/3), `ese`, `naju_nombre` (Pública/Privada), `habilitado`,
   `muni_nombre`, `depa_nombre`, `codigo_habilitacion`.

2. `s2ru-bqt6` (41.427 filas) — "IPS capacidad instalada"
   Variables clave: `nom_grupo_capacidad` (SALAS / CAMAS / AMBULANCIAS),
   `nom_descripcion_capacidad` (UCI, Obstetricia, Partos, Banco de Sangre…),
   `num_cantidad_capacidad_instalada`, `num_nivel_atencion`.

Outputs (agregados por cod_mpio):
  data/mme/bronze/reps/ips_por_muni.parquet         — n_ips_total, n_ips_nivel_{1,2,3}, n_ips_ese, …
  data/mme/bronze/reps/capacidad_por_muni.parquet   — n_camas_uci, n_camas_obstetricia, n_salas_parto, …
  data/mme/bronze/reps/_manifest.json

Uso:
  uv run python scripts/mme/ingest_reps_bronze.py
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd
import requests

from _paths import REPO_ROOT, MME_DATA
BRONZE_DIR = MME_DATA / "bronze" / "reps"
IPS_PARQUET = BRONZE_DIR / "ips_por_muni.parquet"
CAP_PARQUET = BRONZE_DIR / "capacidad_por_muni.parquet"
MANIFEST_PATH = BRONZE_DIR / "_manifest.json"

IPS_DATASET = "ugc5-acjp"
CAP_DATASET = "s2ru-bqt6"
PAGE_SIZE = 50_000
TIMEOUT = 120


# Cache DIVIPOLA para resolver muni_nombre → cod_mpio.
# DIVIPOLA ya está en bronze (DANE dic/2024).
DIVIPOLA_PARQUET = MME_DATA / "bronze" / "divipola" / "municipios.parquet"


def _strip_accents(s: str) -> str:
    """Normaliza a uppercase, sin tildes, sin puntuación, sin espacios múltiples."""
    if not isinstance(s, str):
        return ""
    s = ''.join(c for c in unicodedata.normalize("NFD", s)
                if unicodedata.category(c) != "Mn")
    s = re.sub(r"[,.\-_]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.upper().strip()


# Distritos especiales que REPS etiqueta como DEPARTAMENTO mientras DIVIPOLA
# los coloca como MUNICIPIO del departamento real. Mapeo directo cod_mpio.
DISTRITOS_ESPECIALES_REPS = {
    "BOGOTA D C": 11001,      # Bogotá D.C.
    "BOGOTA": 11001,
    "BARRANQUILLA": 8001,     # Atlántico
    "CARTAGENA": 13001,       # Bolívar
    "SANTA MARTA": 47001,     # Magdalena
    "BUENAVENTURA": 76109,    # Valle del Cauca
    # Casos especiales archipiélago
    "SAN ANDRES Y PROVIDENCIA": 88001,
}


def load_divipola_index() -> pd.DataFrame:
    """Devuelve df con columnas: cod_mpio, cod_dpto, nom_mpio_norm, nom_dpto_norm."""
    con = duckdb.connect(":memory:")
    df = con.execute(f"SELECT * FROM parquet_scan('{DIVIPOLA_PARQUET}')").df()
    con.close()
    # DIVIPOLA nuestra tiene cod_dpto y cod_mpio (local 3 dígitos)? Verificar.
    # En ingestas previas tratamos cod_mpio como DIVIPOLA 5 dígitos.
    df["cod_mpio"] = pd.to_numeric(df["cod_mpio"], errors="coerce").astype("Int64")
    df["cod_dpto"] = pd.to_numeric(df["cod_dpto"], errors="coerce").astype("Int64")
    df["nom_mpio_norm"] = df["nom_mpio"].astype(str).map(_strip_accents)
    df["nom_dpto_norm"] = df["dpto"].astype(str).map(_strip_accents)
    # Mantener solo DIVIPOLA 5 dígitos (descartar totales departamentales cuando mpio_local=0)
    df = df.dropna(subset=["cod_mpio"])
    df = df[df["cod_mpio"].astype("int64") % 1000 != 0]
    df["cod_mpio"] = df["cod_mpio"].astype("int64")
    df["cod_dpto"] = df["cod_dpto"].astype("int64")
    return df[["cod_mpio", "cod_dpto", "nom_mpio_norm", "nom_dpto_norm"]].drop_duplicates()


def fetch_socrata(dataset_id: str) -> pd.DataFrame:
    base = f"https://www.datos.gov.co/resource/{dataset_id}.json"
    pages: list[list[dict]] = []
    offset = 0
    while True:
        t0 = time.perf_counter()
        r = requests.get(base, params={"$limit": PAGE_SIZE, "$offset": offset},
                         timeout=TIMEOUT)
        r.raise_for_status()
        batch = r.json()
        dt = time.perf_counter() - t0
        print(f"  [{dataset_id} offset={offset:>6}] rows={len(batch):>5} in {dt:.2f}s", flush=True)
        if not batch:
            break
        pages.append(batch)
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    flat = [row for page in pages for row in page]
    return pd.DataFrame(flat)


def resolve_cod_mpio(df: pd.DataFrame, muni_col: str, dpto_col: str, divipola: pd.DataFrame) -> pd.Series:
    """Resuelve cod_mpio DIVIPOLA desde nombres (muni_col, dpto_col) vía JOIN normalizado.

    Maneja el caso especial de Distritos Especiales (REPS los codifica como departamento).
    """
    nm = df[muni_col].astype(str).map(_strip_accents)
    nd = df[dpto_col].astype(str).map(_strip_accents)

    # 1) Match directo (muni, dpto).
    tmp = pd.DataFrame({"nom_mpio_norm": nm.values, "nom_dpto_norm": nd.values,
                        "_row_id": range(len(df))})
    merged = tmp.merge(divipola, on=["nom_mpio_norm", "nom_dpto_norm"], how="left")
    merged = merged.drop_duplicates(subset=["_row_id"]).sort_values("_row_id")
    out = pd.Series(merged["cod_mpio"].values, index=df.index, dtype="Int64")

    # 2) Fallback: si el departamento REPS es un Distrito Especial → asignar directo.
    for distrito_norm, cod in DISTRITOS_ESPECIALES_REPS.items():
        mask = out.isna() & (nd.values == distrito_norm)
        if mask.any():
            out.loc[mask] = cod

    # 3) Fallback adicional: si muni_nombre está vacío o coincide con el departamento,
    #    y el departamento es un distrito, también asignar.
    for distrito_norm, cod in DISTRITOS_ESPECIALES_REPS.items():
        mask = out.isna() & (nm.values == distrito_norm)
        if mask.any():
            out.loc[mask] = cod

    # 4) Aliases conocidos de municipios con nombre largo/corto divergente entre
    #    REPS y DIVIPOLA. (muni_norm, dpto_norm) → cod_mpio.
    MUNI_ALIASES: dict[tuple[str, str], int] = {
        ("CALI", "VALLE DEL CAUCA"): 76001,        # DIVIPOLA: SANTIAGO DE CALI
        ("BOGOTA", "CUNDINAMARCA"): 11001,         # Some older REPS entries
        ("TUNJA", "BOYACA"): 15001,
        ("MANIZALES", "CALDAS"): 17001,
        ("POPAYAN", "CAUCA"): 19001,
        ("MONTERIA", "CORDOBA"): 23001,
        ("NEIVA", "HUILA"): 41001,
        ("RIOHACHA", "LA GUAJIRA"): 44001,
        ("VILLAVICENCIO", "META"): 50001,
        ("PASTO", "NARINO"): 52001,
        ("CUCUTA", "NORTE DE SANTANDER"): 54001,
        ("ARMENIA", "QUINDIO"): 63001,
        ("PEREIRA", "RISARALDA"): 66001,
        ("BUCARAMANGA", "SANTANDER"): 68001,
        ("SINCELEJO", "SUCRE"): 70001,
        ("IBAGUE", "TOLIMA"): 73001,
    }
    for (m_norm, d_norm), cod in MUNI_ALIASES.items():
        mask = out.isna() & (nm.values == m_norm) & (nd.values == d_norm)
        if mask.any():
            out.loc[mask] = cod
    return out


def aggregate_ips(raw: pd.DataFrame, divipola: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Agrega ugc5-acjp a 1 fila por municipio con conteos por nivel / naju / ese."""
    df = raw.copy()
    # Filtrar IPS (clpr_codigo=1) habilitadas. El dataset también trae profesionales
    # independientes (clpr_codigo=2) — los excluimos aquí para conteo IPS.
    mask = (df.get("clpr_codigo", "").astype(str) == "1") & (df.get("habilitado", "").astype(str) == "SI")
    df = df[mask].copy()
    df["nivel_int"] = pd.to_numeric(df.get("nivel"), errors="coerce").fillna(-1).astype("int64")
    df["cod_mpio"] = resolve_cod_mpio(df, "muni_nombre", "depa_nombre", divipola)
    before = len(df)
    df = df.dropna(subset=["cod_mpio"])
    unmatched = before - len(df)
    df["cod_mpio"] = df["cod_mpio"].astype("int64")

    flags = pd.DataFrame({
        "cod_mpio": df["cod_mpio"].values,
        "_one": 1,
        "nivel_1": (df["nivel_int"].values == 1).astype("int64"),
        "nivel_2": (df["nivel_int"].values == 2).astype("int64"),
        "nivel_3": (df["nivel_int"].values == 3).astype("int64"),
        "ese":     (df.get("ese", pd.Series("", index=df.index)).astype(str).values == "SI").astype("int64"),
        "publica": (df.get("naju_nombre", pd.Series("", index=df.index)).astype(str).values == "Pública").astype("int64"),
        "privada": (df.get("naju_nombre", pd.Series("", index=df.index)).astype(str).values == "Privada").astype("int64"),
    })
    agg = flags.groupby("cod_mpio", as_index=False).sum().rename(columns={
        "_one": "n_ips_total",
        "nivel_1": "n_ips_nivel_1",
        "nivel_2": "n_ips_nivel_2",
        "nivel_3": "n_ips_nivel_3",
        "ese":     "n_ips_ese",
        "publica": "n_ips_publica",
        "privada": "n_ips_privada",
    })
    agg["tiene_ips_nivel_3"] = (agg["n_ips_nivel_3"] > 0).astype("int64")
    agg["tiene_ips_nivel_2_o_3"] = ((agg["n_ips_nivel_2"] + agg["n_ips_nivel_3"]) > 0).astype("int64")
    meta = {"rows_raw": int(len(raw)), "rows_kept": int(len(df)),
            "muni_unmatched_divipola": int(unmatched)}
    return agg.sort_values("cod_mpio").reset_index(drop=True), meta


def aggregate_capacidad(raw: pd.DataFrame, divipola: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Agrega s2ru-bqt6 a 1 fila por municipio, con conteos por tipo de capacidad."""
    df = raw.copy()
    df["num_cantidad_capacidad_instalada"] = pd.to_numeric(
        df.get("num_cantidad_capacidad_instalada"), errors="coerce"
    ).fillna(0).astype("int64")
    df["cod_mpio"] = resolve_cod_mpio(df, "municipio", "departamento", divipola)
    df = df.dropna(subset=["cod_mpio"])
    df["cod_mpio"] = df["cod_mpio"].astype("int64")

    desc = df.get("nom_descripcion_capacidad", "").astype(str).map(_strip_accents)
    grupo = df.get("nom_grupo_capacidad", "").astype(str).map(_strip_accents)
    cant = df["num_cantidad_capacidad_instalada"]

    # Flags según vocabulario REPS verificado (2026-04-23 contra s2ru-bqt6).
    # NOTA: REPS NO codifica "UCI Obstétrica" como tipo de cama separado — se maneja
    # dentro de UCI Adulto en IPS con UCI-O habilitada. Limitación documentada.
    # Proxies operacionalizan Demora III según guía mme-domain-expert.
    is_camas_parto      = (grupo == "CAMAS") & (desc == "ATENCION DEL PARTO")
    is_uci_adulto       = (grupo == "CAMAS") & desc.str.startswith("CUIDADO INTENSIVO ADULTO")
    is_uci_neonatal     = (grupo == "CAMAS") & desc.str.startswith("CUIDADO INTENSIVO NEONATAL")
    is_uci_pediatrico   = (grupo == "CAMAS") & desc.str.startswith("CUIDADO INTENSIVO PEDIATRICO")
    is_intermedio_neo   = (grupo == "CAMAS") & desc.str.contains("INTERMEDIO NEONATAL")
    is_salas_parto      = (grupo == "SALAS") & (desc == "PARTOS")
    is_salas_cirugia    = (grupo == "SALAS") & desc.isin(["QUIROFANO", "SALA DE CIRUGIA"])
    is_salas_procedim   = (grupo == "SALAS") & (desc == "PROCEDIMIENTOS")
    is_ambul_medical    = (grupo == "AMBULANCIAS") & (desc == "MEDICALIZADA")

    flags = pd.DataFrame({
        "cod_mpio": df["cod_mpio"].values,
        "cap_camas_parto":        cant.where(is_camas_parto, 0).values,
        "cap_uci_adulto":         cant.where(is_uci_adulto, 0).values,
        "cap_uci_neonatal":       cant.where(is_uci_neonatal, 0).values,
        "cap_uci_pediatrico":     cant.where(is_uci_pediatrico, 0).values,
        "cap_intermedio_neonatal": cant.where(is_intermedio_neo, 0).values,
        "cap_salas_parto":        cant.where(is_salas_parto, 0).values,
        "cap_salas_cirugia":      cant.where(is_salas_cirugia, 0).values,
        "cap_salas_procedimiento": cant.where(is_salas_procedim, 0).values,
        "cap_ambulancias_medicalizadas": cant.where(is_ambul_medical, 0).values,
    })
    agg = flags.groupby("cod_mpio", as_index=False).sum()
    agg["tiene_camas_parto"]      = (agg["cap_camas_parto"] > 0).astype("int64")
    agg["tiene_uci_adulto"]       = (agg["cap_uci_adulto"] > 0).astype("int64")
    agg["tiene_uci_neonatal"]     = (agg["cap_uci_neonatal"] > 0).astype("int64")
    agg["tiene_salas_parto"]      = (agg["cap_salas_parto"] > 0).astype("int64")
    agg["tiene_salas_cirugia"]    = (agg["cap_salas_cirugia"] > 0).astype("int64")
    # Proxy compuesto "capacidad obstétrica alta": camas parto + UCI adulto + sala cirugía
    agg["score_capacidad_obstetrica"] = (
        (agg["cap_camas_parto"] > 0).astype(int)
        + (agg["cap_uci_adulto"] > 0).astype(int)
        + (agg["cap_salas_cirugia"] > 0).astype(int)
    )
    meta = {"rows_raw": int(len(raw)), "rows_kept": int(len(df))}
    return agg.sort_values("cod_mpio").reset_index(drop=True), meta


def write_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(":memory:")
    con.register("agg", df)
    con.execute(f"COPY (SELECT * FROM agg) TO '{path}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    con.close()
    print(f"[reps] wrote {path} ({len(df):,} municipios)")


def main() -> int:
    BRONZE_DIR.mkdir(parents=True, exist_ok=True)
    print("[reps] cargando DIVIPOLA...")
    divipola = load_divipola_index()
    print(f"[reps] DIVIPOLA: {len(divipola):,} municipios cacheados")

    print(f"[reps] descargando {IPS_DATASET} (IPS por nivel)...")
    raw_ips = fetch_socrata(IPS_DATASET)
    print(f"[reps] {len(raw_ips):,} filas IPS")

    print("[reps] agregando IPS por muni...")
    ips_agg, ips_meta = aggregate_ips(raw_ips, divipola)
    print(f"[reps] IPS pivot: {len(ips_agg):,} municipios")
    print(f"[reps]   tiene_ips_nivel_3 = SI en {int(ips_agg['tiene_ips_nivel_3'].sum())} municipios")
    write_parquet(ips_agg, IPS_PARQUET)

    print(f"[reps] descargando {CAP_DATASET} (capacidad instalada)...")
    raw_cap = fetch_socrata(CAP_DATASET)
    print(f"[reps] {len(raw_cap):,} filas capacidad")

    print("[reps] agregando capacidad por muni...")
    cap_agg, cap_meta = aggregate_capacidad(raw_cap, divipola)
    print(f"[reps] capacidad pivot: {len(cap_agg):,} municipios")
    print(f"[reps]   tiene_camas_parto = SI en {int(cap_agg['tiene_camas_parto'].sum())} muni")
    print(f"[reps]   tiene_uci_adulto  = SI en {int(cap_agg['tiene_uci_adulto'].sum())} muni")
    print(f"[reps]   tiene_salas_parto = SI en {int(cap_agg['tiene_salas_parto'].sum())} muni")
    print(f"[reps]   total camas parto nacional: {int(cap_agg['cap_camas_parto'].sum())}")
    print(f"[reps]   total camas UCI adulto nacional: {int(cap_agg['cap_uci_adulto'].sum())}")
    write_parquet(cap_agg, CAP_PARQUET)

    manifest = {
        "sources": {
            "ips_por_nivel": {
                "dataset_id": IPS_DATASET,
                "url": f"https://www.datos.gov.co/d/{IPS_DATASET}",
                "description": "Listado de IPS en Colombia según su nivel de complejidad",
                **ips_meta,
            },
            "capacidad_instalada": {
                "dataset_id": CAP_DATASET,
                "url": f"https://www.datos.gov.co/d/{CAP_DATASET}",
                "description": "Relación de IPS según nivel de atención y capacidad instalada",
                **cap_meta,
            },
        },
        "ingested_at_utc": datetime.now(timezone.utc).isoformat(),
        "n_municipios_ips": int(len(ips_agg)),
        "n_municipios_capacidad": int(len(cap_agg)),
        "summary": {
            "n_muni_con_ips_nivel_3": int(ips_agg["tiene_ips_nivel_3"].sum()),
            "n_muni_con_camas_parto": int(cap_agg["tiene_camas_parto"].sum()),
            "n_muni_con_uci_adulto":  int(cap_agg["tiene_uci_adulto"].sum()),
            "n_muni_con_salas_parto": int(cap_agg["tiene_salas_parto"].sum()),
            "camas_parto_nacional":    int(cap_agg["cap_camas_parto"].sum()),
            "camas_uci_adulto_nacional": int(cap_agg["cap_uci_adulto"].sum()),
        },
        "notes": [
            "Fuente REPS MinSalud vía datos.gov.co (Socrata) — no requiere trámite institucional.",
            "Fecha corte REPS: varía por dataset (Mar/Nov 2022-2026). Feature se considera estructural.",
            "Resolución muni vía nombre normalizado (sin tildes) contra DIVIPOLA DANE.",
            "LIMITACIÓN: REPS NO codifica 'UCI Obstétrica' como tipo de cama separado. Se maneja dentro de UCI Adulto en IPS con UCI-O habilitada. Usamos proxies: cap_camas_parto, cap_uci_adulto, cap_salas_cirugia → score_capacidad_obstetrica (0-3) como indicador compuesto de Demora III.",
            "Banco de sangre NO está en este dataset (es SERVICIO HABILITADO, tabla separada) — pendiente ingestar si MinSalud publica dataset nacional.",
            "Capacidad = CAMAS/SALAS habilitadas (no ocupadas). Ocupación real requiere SISPRO (no público).",
        ],
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str))
    print(f"[reps] manifest → {MANIFEST_PATH}")
    print("[reps] ✓ done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
