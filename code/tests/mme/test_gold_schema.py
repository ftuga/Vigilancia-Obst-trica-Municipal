"""Tests del contrato gold panel — `docs/mme/features-spec-v1.md` v1.

Valida invariantes duras que el DAG 1-mme_etl_medallion.validate_gold_invariants
también chequea, pero desde el lado del test runner (fail-fast para CI).
"""
from __future__ import annotations

import duckdb


# Columnas requeridas por contrato v1 (subset mínimo — spec completo tiene 69)
REQUIRED_COLUMNS_SEMESTRE = {
    # Identificación
    "cod_mpio", "cod_dpto", "nom_mpio", "nom_dpto",
    # Temporal
    "ano", "semestre",
    # Régimen
    "covid_window", "post_c055",
    # Outcome MME
    "casos_mme", "is_silent_period",
    # Outcome MM
    "casos_mm_semestre", "casos_mm_anual",
    # NBI
    "nbi_total_pct", "nbi_cabecera_pct", "nbi_centros_rural_disperso_pct",
    # Población
    "poblacion_total_2018", "pct_rural_pobl", "pct_cabecera_pobl",
    # BDUA
    "pct_subsidiado_muni_bdua", "pct_contributivo_muni_bdua",
    # REPS
    "n_ips_total", "n_ips_nivel_3", "tiene_ips_nivel_3",
    "reps_camas_parto", "reps_uci_adulto",
    "score_capacidad_obstetrica",
}

REQUIRED_COLUMNS_SEMANA = {
    "cod_mpio", "cod_dpto", "nom_mpio", "nom_dpto",
    "ano", "semana",
    "casos_mme", "is_silent_period",
    "covid_window", "post_c055",
}


def _cols(con: duckdb.DuckDBPyConnection, path) -> set[str]:
    rows = con.execute(f"DESCRIBE SELECT * FROM '{path}'").fetchall()
    return {r[0] for r in rows}


def test_panel_semestre_shape(con, gold_semestre_path):
    n = con.execute(f"SELECT COUNT(*) FROM '{gold_semestre_path}'").fetchone()[0]
    assert n == 15708, f"Esperado 15.708 filas (1.122 muni × 7 años × 2 sem), obtenido {n}"


def test_panel_semestre_required_columns(con, gold_semestre_path):
    cols = _cols(con, gold_semestre_path)
    missing = REQUIRED_COLUMNS_SEMESTRE - cols
    assert not missing, f"Columnas faltantes en panel_muni_semestre: {sorted(missing)}"


def test_panel_semana_shape(con, gold_semana_path):
    n = con.execute(f"SELECT COUNT(*) FROM '{gold_semana_path}'").fetchone()[0]
    assert n == 408408, f"Esperado 408.408 filas (1.122 × 7 × 52), obtenido {n}"


def test_panel_semana_required_columns(con, gold_semana_path):
    cols = _cols(con, gold_semana_path)
    missing = REQUIRED_COLUMNS_SEMANA - cols
    assert not missing, f"Columnas faltantes en panel_muni_semana: {sorted(missing)}"


def test_casos_mme_no_negatives(con, gold_semestre_path):
    n = con.execute(f"SELECT COUNT(*) FROM '{gold_semestre_path}' WHERE casos_mme < 0").fetchone()[0]
    assert n == 0, f"Hay {n} filas con casos_mme negativo — invariante roto"


def test_silent_flag_consistent(con, gold_semestre_path):
    """is_silent_period=1 ⟺ casos_mme=0."""
    inconsistent = con.execute(f"""
        SELECT COUNT(*) FROM '{gold_semestre_path}'
        WHERE (is_silent_period = 1 AND casos_mme > 0)
           OR (is_silent_period = 0 AND casos_mme = 0)
    """).fetchone()[0]
    assert inconsistent == 0, f"{inconsistent} filas con is_silent_period inconsistente"


def test_cobertura_nbi(con, gold_semestre_path):
    pct = con.execute(f"""
        SELECT 100.0 * SUM(CASE WHEN nbi_total_pct IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*)
        FROM '{gold_semestre_path}'
    """).fetchone()[0]
    assert pct >= 99.0, f"Cobertura NBI {pct:.1f}% < 99%"


def test_cobertura_reps(con, gold_semestre_path):
    pct = con.execute(f"""
        SELECT 100.0 * SUM(CASE WHEN n_ips_total > 0 THEN 1 ELSE 0 END) / COUNT(*)
        FROM '{gold_semestre_path}'
    """).fetchone()[0]
    assert pct >= 75.0, f"Cobertura REPS {pct:.1f}% < 75%"


def test_divipola_valid(con, gold_semestre_path):
    """cod_mpio debe ser 5 dígitos (1000-99999)."""
    invalid = con.execute(f"""
        SELECT COUNT(*) FROM '{gold_semestre_path}'
        WHERE cod_mpio < 1000 OR cod_mpio > 99999
    """).fetchone()[0]
    assert invalid == 0, f"{invalid} filas con cod_mpio inválido"


def test_covid_window_consistent(con, gold_semestre_path):
    """covid_window=1 ⟺ ano ∈ {2020, 2021, 2022}."""
    bad = con.execute(f"""
        SELECT COUNT(*) FROM '{gold_semestre_path}'
        WHERE (covid_window = 1 AND ano NOT BETWEEN 2020 AND 2022)
           OR (covid_window = 0 AND ano BETWEEN 2020 AND 2022)
    """).fetchone()[0]
    assert bad == 0, f"{bad} filas con covid_window inconsistente"
