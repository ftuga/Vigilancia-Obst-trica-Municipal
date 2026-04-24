"""Helper centralizado para resolver paths del medallón MME + reports.

Permite override vía env vars:
  MME_DATA_ROOT     → dónde escribir bronze/silver/gold (default: REPO_ROOT/data/mme)
  MME_REPORTS_ROOT  → dónde escribir reports (default: REPO_ROOT/reports/mme)

Los DAGs Airflow setean ambas para redirigir escrituras fuera del repo RO:
  MME_DATA_ROOT=/opt/airflow/data/mme
  MME_REPORTS_ROOT=/opt/airflow/data/mme/reports

Uso estándar en cada script:

    from _paths import REPO_ROOT, MME_DATA, MME_REPORTS
    BRONZE_DIR = MME_DATA / "bronze"
    REPORTS_DIR = MME_REPORTS

Como este módulo está al lado de los scripts (scripts/mme/), Python resuelve
el import automáticamente (el dir del script entra a sys.path).
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_data_override = os.environ.get("MME_DATA_ROOT")
MME_DATA = Path(_data_override) if _data_override else REPO_ROOT / "data" / "mme"

_reports_override = os.environ.get("MME_REPORTS_ROOT")
MME_REPORTS = Path(_reports_override) if _reports_override else REPO_ROOT / "reports" / "mme"


def ensure_roots() -> None:
    MME_DATA.mkdir(parents=True, exist_ok=True)
    MME_REPORTS.mkdir(parents=True, exist_ok=True)
