"""Tests de métricas de evaluación — `src/mme/eval/metrics.py`."""
from __future__ import annotations

import numpy as np
import pytest

from mme.eval.metrics import compute_metrics


def test_metrics_perfect_prediction() -> None:
    """Predicción perfecta → Spearman=1, MAE razón=0, p@50=1."""
    n = 100
    rng = np.random.default_rng(42)
    y_true = rng.poisson(lam=10.0, size=n).astype(float)
    pop = np.full(n, 5000.0)
    dpto = rng.integers(1, 34, size=n)
    m = compute_metrics(y_true, y_true, pop, dpto)
    assert m.mae_razon == 0.0
    assert m.spearman_dpto > 0.99
    assert m.precision_at_50 == 1.0
    assert m.r2_log_counts > 0.99


def test_metrics_negative_pred_clipped() -> None:
    """Predicciones negativas deben clipearse a 0 (no crashear)."""
    y_true = np.array([5.0, 10.0, 15.0])
    y_pred = np.array([-1.0, 10.0, 20.0])  # uno negativo
    pop = np.array([1000.0, 1000.0, 1000.0])
    dpto = np.array([1, 2, 3])
    m = compute_metrics(y_true, y_pred, pop, dpto, top_k=3)
    assert np.isfinite(m.mae_razon)


def test_metrics_rejects_mismatched_lengths() -> None:
    """Tamaños diferentes → ValueError."""
    with pytest.raises(ValueError, match="misma longitud"):
        compute_metrics(
            np.array([1.0, 2.0]),
            np.array([1.0, 2.0, 3.0]),
            np.array([100.0, 200.0, 300.0]),
            np.array([1, 2, 3]),
        )


def test_metrics_precision_at_k_edge_small() -> None:
    """top_k > n → usa n (no crashea)."""
    y_true = np.array([1.0, 2.0, 3.0])
    y_pred = np.array([1.0, 2.0, 3.0])
    pop = np.array([1000.0, 1000.0, 1000.0])
    dpto = np.array([1, 2, 3])
    m = compute_metrics(y_true, y_pred, pop, dpto, top_k=50)
    assert m.precision_at_50 == 1.0  # n=3, efectivo top_k=3


def test_metrics_as_dict() -> None:
    """as_dict() retorna solo las 4 métricas primarias."""
    m = compute_metrics(
        np.array([1.0, 2.0, 3.0]),
        np.array([1.0, 2.0, 3.0]),
        np.array([1000.0, 1000.0, 1000.0]),
        np.array([1, 2, 3]),
        top_k=3,
    )
    d = m.as_dict()
    assert set(d.keys()) == {"mae_razon", "spearman_dpto", "precision_at_50", "r2_log_counts"}
