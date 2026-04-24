"""Métricas de evaluación alineadas con el gate Go/No-Go del ml-problem-definition §6.

Las 4 métricas primarias (todas sobre test 2022):
    mae_razon        — error absoluto en razón por 1.000 hab
    spearman_dpto    — ranking departamental (robustez MAUP)
    precision_at_50  — ¿top-50 predicho coincide con top-50 real?
    r2_log_counts    — R² sobre log(casos+1)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr


@dataclass(frozen=True)
class MetricsResult:
    """Resultado de evaluación de un modelo sobre un split."""

    mae_razon: float
    spearman_dpto: float
    precision_at_50: float
    r2_log_counts: float
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, float]:
        """Convierte a dict plano (para MLflow log_metrics)."""
        return {
            "mae_razon": self.mae_razon,
            "spearman_dpto": self.spearman_dpto,
            "precision_at_50": self.precision_at_50,
            "r2_log_counts": self.r2_log_counts,
        }


def compute_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    pop_sem: np.ndarray,
    cod_dpto: np.ndarray,
    *,
    top_k: int = 50,
) -> MetricsResult:
    """Calcula las 4 métricas primarias.

    Args:
        y_true: Counts observados (≥0).
        y_pred: Counts predichos (≥0 — clipeados aquí).
        pop_sem: Denominador poblacional (semestre) para convertir a razón.
        cod_dpto: Código DIVIPOLA departamento por fila (para agregación dpto).
        top_k: Tamaño del top para ``precision@top-k``. Default 50.

    Returns:
        MetricsResult con las 4 métricas calculadas.

    Raises:
        ValueError: si alguna longitud no coincide.
    """
    if not (len(y_true) == len(y_pred) == len(pop_sem) == len(cod_dpto)):
        raise ValueError("y_true, y_pred, pop_sem, cod_dpto deben tener misma longitud")

    pop = np.clip(np.asarray(pop_sem, dtype=np.float64), 1.0, None)
    y_true_arr = np.asarray(y_true, dtype=np.float64)
    y_pred_arr = np.clip(np.asarray(y_pred, dtype=np.float64), 0.0, None)

    razon_true = y_true_arr * 1000.0 / pop
    razon_pred = y_pred_arr * 1000.0 / pop

    mae_razon = float(np.mean(np.abs(razon_pred - razon_true)))

    # Spearman agregado a nivel departamento (robustez MAUP)
    dpto_df = pd.DataFrame({"d": cod_dpto, "t": razon_true, "p": razon_pred})
    agg = dpto_df.groupby("d").agg(t=("t", "mean"), p=("p", "mean"))
    try:
        rho = float(spearmanr(agg["t"], agg["p"]).statistic)
    except (ValueError, RuntimeWarning):
        rho = float("nan")

    n_k = min(top_k, len(razon_true))
    top_t = set(np.argsort(razon_true)[-n_k:])
    top_p = set(np.argsort(razon_pred)[-n_k:])
    p_at_k = len(top_t & top_p) / n_k

    y_log_t = np.log1p(y_true_arr)
    y_log_p = np.log1p(y_pred_arr)
    ss_res = float(np.sum((y_log_t - y_log_p) ** 2))
    ss_tot = float(np.sum((y_log_t - y_log_t.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    return MetricsResult(
        mae_razon=round(mae_razon, 4),
        spearman_dpto=round(rho, 4),
        precision_at_50=round(p_at_k, 4),
        r2_log_counts=round(r2, 4),
        extra={"top_k": top_k},
    )
