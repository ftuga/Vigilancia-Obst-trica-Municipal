"""Tests de Clayton-Kaldor Empirical Bayes — `src/mme/data/clayton_kaldor.py`."""
from __future__ import annotations

import numpy as np
import pytest

from mme.data.clayton_kaldor import empirical_bayes_smooth


def test_ck_shapes_and_scale() -> None:
    """Output mismo tamaño que input; escala de razón en /1.000."""
    rng = np.random.default_rng(42)
    n = np.full(100, 1000.0)
    y = rng.poisson(lam=5.0, size=100).astype(float)  # tasa 5/1000
    razon, params = empirical_bayes_smooth(y, n)
    assert razon.shape == y.shape
    # Media de razón suavizada cercana a tasa real × 1000
    assert 4.0 < razon.mean() < 6.0
    assert params.alpha > 0
    assert params.beta > 0


def test_ck_shrinks_small_counties() -> None:
    """Municipios con n bajo deben shrinkear más hacia la media global."""
    # Mezcla: 50 muni grandes (n=10.000), 50 muni chicos (n=100)
    n = np.concatenate([np.full(50, 10000.0), np.full(50, 100.0)])
    # Todos con rate verdadera 3/1000, pero muni chicos tienen más varianza muestral
    rng = np.random.default_rng(7)
    y = rng.poisson(lam=n * 3.0 / 1000.0)
    razon, _ = empirical_bayes_smooth(y, n)
    razon_grandes = razon[:50]
    razon_chicos = razon[50:]
    # Varianza de razón suavizada debe ser MENOR en muni chicos (más shrinkage)
    assert np.var(razon_chicos) < np.var(y[50:] * 1000.0 / n[50:])


def test_ck_rejects_mismatched_lengths() -> None:
    """Shapes mal alineadas deben levantar ValueError claro."""
    with pytest.raises(ValueError, match="misma longitud"):
        empirical_bayes_smooth(np.array([1.0, 2.0]), np.array([10.0, 20.0, 30.0]))


def test_ck_rejects_nan() -> None:
    """NaN en y o n debe ser error explícito."""
    with pytest.raises(ValueError, match="NaN"):
        empirical_bayes_smooth(np.array([1.0, np.nan]), np.array([10.0, 20.0]))


def test_ck_zero_counts_no_crash() -> None:
    """y_i = 0 en municipios silentes no debe crashear."""
    n = np.full(10, 1000.0)
    y = np.zeros(10)
    razon, params = empirical_bayes_smooth(y, n)
    # Con todo cero, razón suavizada → 0 pero finita
    assert np.all(np.isfinite(razon))
    assert np.all(razon >= 0)


def test_ck_params_immutable() -> None:
    """ClaytonKaldorParams es frozen (no se puede mutar)."""
    _, params = empirical_bayes_smooth(
        np.array([1.0, 2.0, 3.0]), np.array([100.0, 200.0, 300.0]),
    )
    with pytest.raises(AttributeError):
        params.alpha = 999.0  # type: ignore[misc]
