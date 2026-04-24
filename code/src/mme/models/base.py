"""Contratos comunes de modelos C3."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from mme.eval.metrics import MetricsResult


@dataclass
class ModelResult:
    """Resultado unificado de un modelo entrenado.

    Cada familia (GLM NegBin, LightGBM, XGBoost) retorna este objeto.
    El logging a MLflow es responsabilidad de ``mme.tracking``, no del trainer.

    Attributes:
        family: Identificador (``glm_negbin``, ``lgbm_poisson``, ``xgb_poisson``).
        model: Objeto modelo serializable (statsmodels result / lgb.Booster / xgb.Booster).
        test_metrics: Métricas sobre test 2022.
        val_metrics: Métricas sobre val 2021.
        y_pred_test: Predicciones sobre test (escala counts, mismo len que test).
        y_pred_train_val: Predicciones sobre ``concat(train, val)`` — base para
            residuos del bootstrap CI. Misma longitud que ``n_train + n_val``.
        params: Hiperparámetros finales (best params de Optuna si aplica).
        metadata: Info adicional (device, n_trials, etc.).
    """

    family: str
    model: Any
    test_metrics: MetricsResult
    val_metrics: MetricsResult
    y_pred_test: np.ndarray  # type: ignore[type-arg]
    y_pred_train_val: np.ndarray = field(  # type: ignore[type-arg]
        default_factory=lambda: np.empty(0),
    )
    params: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TrainingData:
    """Bundle de datos preparados para training.

    Args:
        X_train: Features train (sin offset como col — ver ``augment``).
        y_train: Counts train.
        offset_train: log(pop_sem) train.
        X_val, y_val, offset_val: Idem val 2021.
        X_test, y_test, offset_test: Idem test 2022.
        pop_sem_val, pop_sem_test: Denominador para métricas.
        cod_dpto_val, cod_dpto_test: Para Spearman dpto.
    """

    X_train: pd.DataFrame
    y_train: np.ndarray
    offset_train: np.ndarray
    X_val: pd.DataFrame
    y_val: np.ndarray
    offset_val: np.ndarray
    X_test: pd.DataFrame
    y_test: np.ndarray
    offset_test: np.ndarray
    pop_sem_val: np.ndarray
    pop_sem_test: np.ndarray
    cod_dpto_val: np.ndarray
    cod_dpto_test: np.ndarray
