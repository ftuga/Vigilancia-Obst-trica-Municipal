"""Augmentación de features para modelos tree-based.

Para LightGBM/XGBoost con objective Poisson, el offset poblacional se agrega
como FEATURE (``log_pop_sem``) en lugar de ``init_score``/``base_margin``.
Razón: LightGBM issue #2708 — init_score con offset de exposure puede producir
modelos que invierten el ranking (confirmado empíricamente con Spearman test
bajando a −0.45 antes del fix).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

LOG_POP_COL = "log_pop_sem"


def augment_with_offset(X: pd.DataFrame, offset: np.ndarray) -> pd.DataFrame:
    """Añade ``log_pop_sem`` como columna feature.

    Args:
        X: Features del modelo sin offset.
        offset: Vector ``log(pop_sem)`` de la misma longitud que ``X``.

    Returns:
        Copia de ``X`` con la columna ``log_pop_sem`` añadida al final.

    Raises:
        ValueError: si longitudes no coinciden.
    """
    if len(X) != len(offset):
        raise ValueError(f"X ({len(X)}) y offset ({len(offset)}) no coinciden")
    out = X.copy()
    out[LOG_POP_COL] = np.asarray(offset, dtype=np.float64)
    return out
