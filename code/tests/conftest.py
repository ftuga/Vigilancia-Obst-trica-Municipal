"""Conftest raíz del monorepo. Permite correr pytest desde el root y encontrar
los tests de contrato de features + los tests de api_datos por separado.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in [ROOT / "scripts", ROOT / "api_datos"]:
    sp = str(p)
    if p.exists() and sp not in sys.path:
        sys.path.insert(0, sp)
