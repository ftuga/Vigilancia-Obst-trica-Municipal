"""Empirical Bayes Poisson-Gamma smoothing (Clayton-Kaldor 1987).

Estabiliza razones en municipios con bajo denominador usando la posterior
E[λ_i | y_i] = (α + y_i) / (β + n_i) con α, β estimados por método de momentos.

Reemplaza el shrinkage ad-hoc `k / (k + N_pop)` del prototipo inicial.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ClaytonKaldorParams:
    """Parámetros EB Poisson-Gamma estimados del dataset.

    Attributes:
        alpha: Hiperparámetro prior Gamma (shape).
        beta: Hiperparámetro prior Gamma (rate).
        m1: Media de la tasa cruda (y/n).
        excess_var: Varianza en exceso sobre Poisson, usada para estimar α, β.
    """

    alpha: float
    beta: float
    m1: float
    excess_var: float


def empirical_bayes_smooth(
    y: np.ndarray,
    n: np.ndarray,
    *,
    min_n: float = 1.0,
) -> tuple[np.ndarray, ClaytonKaldorParams]:
    """Calcula razones suavizadas vía EB Poisson-Gamma.

    Modelo:
        y_i ~ Poisson(n_i · λ_i)
        λ_i ~ Gamma(α, β)
        E[λ_i | y_i] = (α + y_i) / (β + n_i)

    Estimación por momentos (Clayton-Kaldor 1987):
        mean(rate) = α/β                        → estimador m1
        var(rate)  = α/β² + mean(y)/mean(n²)    → estimador excess_var

    Args:
        y: Conteos observados por unidad (≥0, shape N).
        n: Denominador (exposure) por unidad (>0, shape N).
        min_n: Piso para n (evita división por cero). Default 1.0.

    Returns:
        Tupla ``(razon_suavizada, params)``:
            - razon_suavizada: E[λ_i|y_i] × 1000 (escala por 1000 NV/hab).
            - params: ClaytonKaldorParams con α, β, m1, excess_var.

    Raises:
        ValueError: si ``y`` o ``n`` tienen longitudes diferentes o contienen NaN.
    """
    if len(y) != len(n):
        raise ValueError(f"y ({len(y)}) y n ({len(n)}) deben tener la misma longitud")
    y_arr = np.asarray(y, dtype=np.float64)
    n_arr = np.asarray(n, dtype=np.float64).clip(min=min_n)
    if np.isnan(y_arr).any() or np.isnan(n_arr).any():
        raise ValueError("y y n no pueden contener NaN")

    rate = y_arr / n_arr
    m1 = float(np.mean(rate))
    m2 = float(np.var(rate, ddof=1))
    # Varianza "en exceso" sobre lo que predice Poisson puro:
    # Var(rate_sample) = Var(λ_true) + E[λ] / E[n]
    excess_var = max(m2 - m1 / float(np.mean(n_arr)), 1e-12)

    beta = m1 / excess_var
    alpha = (m1**2) / excess_var
    lambda_eb = (alpha + y_arr) / (beta + n_arr)

    return lambda_eb * 1000.0, ClaytonKaldorParams(
        alpha=float(alpha),
        beta=float(beta),
        m1=m1,
        excess_var=excess_var,
    )
