"""Resolución canónica de paths del proyecto.

Dos env vars permiten redirigir escritura (crítico para Airflow worker con repo RO):
    MME_DATA_ROOT     → default: REPO_ROOT/data/mme
    MME_REPORTS_ROOT  → default: REPO_ROOT/reports/mme

Uso típico::

    from mme.paths import MME_DATA, MME_REPORTS
    bronze_dir = MME_DATA / "bronze"
"""
from __future__ import annotations

import os
from pathlib import Path

# El paquete vive en src/mme/, así que parents[2] = repo root
REPO_ROOT: Path = Path(__file__).resolve().parents[2]

_data_override = os.environ.get("MME_DATA_ROOT")
MME_DATA: Path = Path(_data_override) if _data_override else REPO_ROOT / "data" / "mme"

_reports_override = os.environ.get("MME_REPORTS_ROOT")
MME_REPORTS: Path = (
    Path(_reports_override) if _reports_override else REPO_ROOT / "reports" / "mme"
)


def ensure_roots() -> None:
    """Crea los directorios base si no existen."""
    MME_DATA.mkdir(parents=True, exist_ok=True)
    MME_REPORTS.mkdir(parents=True, exist_ok=True)
