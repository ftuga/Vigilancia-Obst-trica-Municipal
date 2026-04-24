"""GLM Negative Binomial con offset log(pop_sem).

Baseline interpretable. Seleccionado sobre Poisson por dispersion ratio = 710
(ver reports/mme/models/eda_target_c3.md §1).
"""
from __future__ import annotations

from typing import Any

import numpy as np
import statsmodels.api as sm
from sklearn.preprocessing import StandardScaler

from mme.eval.metrics import compute_metrics
from mme.models.base import ModelResult, TrainingData

FAMILY = "glm_negbin"


def train(data: TrainingData) -> ModelResult:
    """Entrena NegBin GLM con offset clásico.

    Args:
        data: TrainingData preparado (X sin log_pop_sem — statsmodels lo usa como offset).

    Returns:
        ModelResult con modelo statsmodels + scaler empaquetados.
    """
    scaler = StandardScaler().fit(data.X_train.to_numpy())
    xs_train = scaler.transform(data.X_train.to_numpy())
    xc_train = sm.add_constant(xs_train, has_constant="add")

    model = sm.GLM(
        data.y_train,
        xc_train,
        family=sm.families.NegativeBinomial(alpha=1.0),
        offset=data.offset_train,
    ).fit()

    y_pred_train = np.asarray(model.predict(xc_train, offset=data.offset_train))

    xs_test = scaler.transform(data.X_test.to_numpy())
    xc_test = sm.add_constant(xs_test, has_constant="add")
    y_pred_test = np.asarray(model.predict(xc_test, offset=data.offset_test))

    xs_val = scaler.transform(data.X_val.to_numpy())
    xc_val = sm.add_constant(xs_val, has_constant="add")
    y_pred_val = np.asarray(model.predict(xc_val, offset=data.offset_val))

    test_m = compute_metrics(
        data.y_test, y_pred_test, data.pop_sem_test, data.cod_dpto_test,
    )
    val_m = compute_metrics(
        data.y_val, y_pred_val, data.pop_sem_val, data.cod_dpto_val,
    )

    packed: dict[str, Any] = {
        "model": model,
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
        "features": list(data.X_train.columns),
    }
    return ModelResult(
        family=FAMILY,
        model=packed,
        test_metrics=test_m,
        val_metrics=val_m,
        y_pred_test=y_pred_test,
        y_pred_train_val=np.concatenate([y_pred_train, y_pred_val]),
        params={"alpha": 1.0, "link": "log"},
        metadata={"n_train": len(data.y_train)},
    )
