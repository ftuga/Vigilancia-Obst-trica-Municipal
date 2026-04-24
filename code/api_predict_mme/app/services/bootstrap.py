"""Bootstrap de residuos para intervalos de confianza por predicción.

Técnica: dada una predicción puntual ``y_point`` y un array de ``residuals``
del training (``y_train_val - y_pred_train_val``), samplea con reemplazo y
retorna los percentiles del intervalo.

No requiere reentrenar N modelos — es ``residual bootstrap`` clásico en
regresión. Valido para modelos donde los errores sean aproximadamente
intercambiables; la distribución Poisson fuerte skew justifica esta técnica
sobre el CI Wald.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray


@dataclass(frozen=True)
class BootstrapCI:
    """Resultado de un bootstrap CI."""

    point: float
    low: float
    high: float
    alpha: float
    n_bootstrap: int


def compute_ci(
    y_point: float,
    residuals: NDArray[np.float64],
    *,
    alpha: float = 0.10,
    n_bootstrap: int = 200,
    seed: int | None = 42,
) -> BootstrapCI:
    """Calcula intervalo bootstrap simétrico via residual resampling.

    Args:
        y_point: Predicción puntual (casos esperados).
        residuals: Residuos del training (shape (n_train_val,)).
        alpha: Nivel de significancia. ``alpha=0.10`` → 90% CI.
        n_bootstrap: Cantidad de replicates.
        seed: Seed para reproducibilidad. ``None`` usa entropía del sistema.

    Returns:
        ``BootstrapCI`` con ``low``, ``high`` (clipeados a ≥ 0 porque MME
        son counts no-negativos) y el ``point`` pasado.
    """
    if residuals.size == 0:
        # Sin residuos disponibles → intervalo degenerado = punto.
        return BootstrapCI(
            point=y_point, low=y_point, high=y_point,
            alpha=alpha, n_bootstrap=0,
        )

    rng = np.random.default_rng(seed)
    idx = rng.integers(0, residuals.size, size=n_bootstrap)
    samples = y_point + residuals[idx]
    samples = np.clip(samples, 0.0, None)

    lo_pct = 100.0 * (alpha / 2.0)
    hi_pct = 100.0 * (1.0 - alpha / 2.0)
    low, high = np.percentile(samples, [lo_pct, hi_pct])

    return BootstrapCI(
        point=float(y_point),
        low=float(low),
        high=float(high),
        alpha=alpha,
        n_bootstrap=n_bootstrap,
    )


def classify_risk(razon_por_1000: float) -> str:
    """Clasifica tier de riesgo según razón MME por 1.000 habitantes.

    Umbrales basados en distribución histórica colombiana (boletines INS
    2018-2022): mediana ~5, P75 ~10, cola larga.
    """
    if razon_por_1000 >= 10.0:
        return "alto"
    if razon_por_1000 >= 5.0:
        return "medio"
    return "bajo"
