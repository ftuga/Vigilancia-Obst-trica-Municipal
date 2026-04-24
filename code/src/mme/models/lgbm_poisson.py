"""LightGBM objective=poisson con hyperparameter tuning via Optuna.

Challenger no-lineal del NegBin GLM. El offset poblacional va como FEATURE
(``log_pop_sem``), no como init_score — ver ``mme.features.augment`` para el
razonamiento (LightGBM issue #2708).
"""
from __future__ import annotations

from typing import Any

import lightgbm as lgb
import numpy as np
import optuna
from optuna.pruners import MedianPruner
from optuna.samplers import TPESampler

from mme.config import TrainingConfig
from mme.eval.metrics import compute_metrics
from mme.features.augment import augment_with_offset
from mme.models.base import ModelResult, TrainingData

FAMILY = "lgbm_poisson"


def _build_datasets(
    data: TrainingData, num_threads: int,
) -> tuple[lgb.Dataset, lgb.Dataset]:
    """Construye Dataset train+val con log_pop_sem como feature."""
    x_train_aug = augment_with_offset(data.X_train, data.offset_train)
    x_val_aug = augment_with_offset(data.X_val, data.offset_val)
    ds_params = {"feature_pre_filter": False, "num_threads": num_threads}
    y_train = np.ascontiguousarray(data.y_train, dtype=np.float64)
    y_val = np.ascontiguousarray(data.y_val, dtype=np.float64)
    train_set = lgb.Dataset(
        x_train_aug.to_numpy(),
        label=y_train,
        feature_name=list(x_train_aug.columns),
        params=ds_params,
        free_raw_data=False,
    )
    val_set = lgb.Dataset(
        x_val_aug.to_numpy(),
        label=y_val,
        reference=train_set,
        params=ds_params,
        free_raw_data=False,
    )
    return train_set, val_set


def _build_objective(
    data: TrainingData,
    train_set: lgb.Dataset,
    val_set: lgb.Dataset,
    cfg: TrainingConfig,
) -> Any:
    """Retorna la función objective de Optuna (closure sobre data+datasets+cfg)."""
    x_val_aug = augment_with_offset(data.X_val, data.offset_val)

    def objective(trial: optuna.Trial) -> float:
        params: dict[str, Any] = {
            "objective": "poisson",
            "metric": "poisson",
            "verbosity": -1,
            "feature_pre_filter": False,
            "num_threads": cfg.lgbm_num_threads,
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
            "num_leaves": trial.suggest_int("num_leaves", 15, 127),
            "min_data_in_leaf": trial.suggest_int("min_data_in_leaf", 10, 100),
            "feature_fraction": trial.suggest_float("feature_fraction", 0.6, 1.0),
            "bagging_fraction": trial.suggest_float("bagging_fraction", 0.6, 1.0),
            "bagging_freq": trial.suggest_int("bagging_freq", 0, 10),
            "lambda_l1": trial.suggest_float("lambda_l1", 1e-8, 10.0, log=True),
            "lambda_l2": trial.suggest_float("lambda_l2", 1e-8, 10.0, log=True),
            "max_depth": trial.suggest_int("max_depth", 3, 12),
            "min_gain_to_split": trial.suggest_float("min_gain_to_split", 0.0, 1.0),
        }
        booster = lgb.train(
            params,
            train_set,
            num_boost_round=cfg.lgbm_num_boost_round,
            valid_sets=[val_set],
            callbacks=[
                lgb.early_stopping(cfg.lgbm_early_stopping, verbose=False),
                lgb.log_evaluation(0),
            ],
        )
        y_pred = booster.predict(x_val_aug.to_numpy())
        m = compute_metrics(
            data.y_val, np.asarray(y_pred), data.pop_sem_val, data.cod_dpto_val,
        )
        return m.spearman_dpto

    return objective


def train(data: TrainingData, cfg: TrainingConfig) -> ModelResult:
    """Entrena LightGBM Poisson con Optuna TPE.

    Args:
        data: TrainingData preparado.
        cfg: TrainingConfig (n_trials, num_threads, etc.).

    Returns:
        ModelResult con Booster + best params de Optuna.
    """
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    train_set, val_set = _build_datasets(data, cfg.lgbm_num_threads)
    objective = _build_objective(data, train_set, val_set, cfg)

    study = optuna.create_study(
        direction="maximize",
        sampler=TPESampler(seed=cfg.optuna_seed),
        pruner=MedianPruner(n_warmup_steps=10),
    )
    study.optimize(objective, n_trials=cfg.optuna_n_trials, show_progress_bar=False)

    best_params: dict[str, Any] = {
        **study.best_params,
        "objective": "poisson",
        "metric": "poisson",
        "verbosity": -1,
        "feature_pre_filter": False,
        "num_threads": cfg.lgbm_num_threads,
    }
    final_booster = lgb.train(
        best_params,
        train_set,
        num_boost_round=cfg.lgbm_num_boost_round + 100,
        valid_sets=[val_set],
        callbacks=[
            lgb.early_stopping(cfg.lgbm_early_stopping + 5, verbose=False),
            lgb.log_evaluation(0),
        ],
    )

    x_train_aug = augment_with_offset(data.X_train, data.offset_train)
    x_val_aug = augment_with_offset(data.X_val, data.offset_val)
    x_test_aug = augment_with_offset(data.X_test, data.offset_test)
    y_pred_train = np.asarray(final_booster.predict(x_train_aug.to_numpy()))
    y_pred_val = np.asarray(final_booster.predict(x_val_aug.to_numpy()))
    y_pred_test = np.asarray(final_booster.predict(x_test_aug.to_numpy()))

    test_m = compute_metrics(
        data.y_test, y_pred_test, data.pop_sem_test, data.cod_dpto_test,
    )
    val_m = compute_metrics(
        data.y_val, y_pred_val, data.pop_sem_val, data.cod_dpto_val,
    )

    return ModelResult(
        family=FAMILY,
        model=final_booster,
        test_metrics=test_m,
        val_metrics=val_m,
        y_pred_test=y_pred_test,
        y_pred_train_val=np.concatenate([y_pred_train, y_pred_val]),
        params=study.best_params,
        metadata={
            "optuna_n_trials": cfg.optuna_n_trials,
            "optuna_best_val_spearman": study.best_value,
            "optuna_sampler": "TPE",
            "optuna_pruner": "MedianPruner",
        },
    )
