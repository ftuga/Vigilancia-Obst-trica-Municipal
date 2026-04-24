"""Fixtures compartidas de tests MME."""
from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLD_SEMESTRE = REPO_ROOT / "data" / "mme" / "gold" / "panel_muni_semestre.parquet"
GOLD_SEMANA = REPO_ROOT / "data" / "mme" / "gold" / "panel_muni_semana.parquet"
SILVER = REPO_ROOT / "data" / "mme" / "silver" / "mme_clean.parquet"


@pytest.fixture(scope="session")
def con() -> duckdb.DuckDBPyConnection:
    """Conexión DuckDB de sesión, sola lectura."""
    c = duckdb.connect(":memory:")
    yield c
    c.close()


@pytest.fixture(scope="session")
def gold_semestre_path() -> Path:
    if not GOLD_SEMESTRE.exists():
        pytest.skip(f"Gold semestre no existe en {GOLD_SEMESTRE} — ejecutar ETL primero")
    return GOLD_SEMESTRE


@pytest.fixture(scope="session")
def gold_semana_path() -> Path:
    if not GOLD_SEMANA.exists():
        pytest.skip(f"Gold semana no existe en {GOLD_SEMANA} — ejecutar ETL primero")
    return GOLD_SEMANA


@pytest.fixture(scope="session")
def silver_path() -> Path:
    if not SILVER.exists():
        pytest.skip(f"Silver no existe en {SILVER} — ejecutar ETL primero")
    return SILVER
