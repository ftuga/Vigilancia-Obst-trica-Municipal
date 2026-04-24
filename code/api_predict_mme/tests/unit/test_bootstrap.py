"""Tests del bootstrap CI — ``app/services/bootstrap.py``."""
from __future__ import annotations

import numpy as np
import pytest

from app.services.bootstrap import BootstrapCI, classify_risk, compute_ci


def test_empty_residuals_returns_degenerate_ci() -> None:
    """Sin residuos → CI = punto (low == high == point)."""
    ci = compute_ci(5.0, np.empty(0, dtype=float))
    assert ci.low == 5.0
    assert ci.high == 5.0
    assert ci.n_bootstrap == 0


def test_ci_brackets_point_prediction() -> None:
    """Con residuos centrados en 0, el punto debería caer dentro del CI."""
    rng = np.random.default_rng(42)
    residuals = rng.normal(0.0, 1.0, size=500)
    ci = compute_ci(10.0, residuals, alpha=0.10, n_bootstrap=200, seed=7)
    assert ci.low <= 10.0 <= ci.high
    assert ci.alpha == 0.10
    assert ci.n_bootstrap == 200


def test_ci_is_clipped_at_zero() -> None:
    """Predicción baja + residuos negativos → low se clipea a 0 (counts ≥ 0)."""
    residuals = np.array([-5.0, -3.0, -1.0, 0.0, 1.0, 3.0, 5.0])
    ci = compute_ci(2.0, residuals, alpha=0.10, n_bootstrap=500, seed=1)
    assert ci.low >= 0.0


def test_higher_alpha_narrows_interval() -> None:
    """alpha más alto (80% CI) → intervalo más angosto que 90% CI."""
    rng = np.random.default_rng(0)
    residuals = rng.normal(0, 2.0, size=1000)
    ci_90 = compute_ci(5.0, residuals, alpha=0.10, n_bootstrap=500, seed=3)
    ci_80 = compute_ci(5.0, residuals, alpha=0.20, n_bootstrap=500, seed=3)
    assert (ci_80.high - ci_80.low) <= (ci_90.high - ci_90.low)


def test_deterministic_with_seed() -> None:
    """Misma seed → mismo CI (reproducibilidad)."""
    rng = np.random.default_rng(42)
    residuals = rng.normal(0, 1, size=300)
    a = compute_ci(5.0, residuals, seed=99)
    b = compute_ci(5.0, residuals, seed=99)
    assert a == b


def test_bootstrap_ci_frozen_dataclass() -> None:
    """BootstrapCI es frozen: no se puede mutar."""
    ci = BootstrapCI(point=1.0, low=0.5, high=1.5, alpha=0.1, n_bootstrap=100)
    with pytest.raises((AttributeError, TypeError)):
        ci.point = 2.0  # type: ignore[misc]


def test_classify_risk_tiers() -> None:
    """Thresholds: ≥10 alto, ≥5 medio, resto bajo."""
    assert classify_risk(12.5) == "alto"
    assert classify_risk(10.0) == "alto"
    assert classify_risk(7.0) == "medio"
    assert classify_risk(5.0) == "medio"
    assert classify_risk(4.9) == "bajo"
    assert classify_risk(0.0) == "bajo"
