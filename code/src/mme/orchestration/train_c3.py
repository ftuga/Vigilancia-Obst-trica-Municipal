"""Orquestador de entrenamiento C3.

Hila data loading + feature selection + training de cada familia + reporting.
Cada paso delega a su módulo. Este archivo NO contiene lógica de negocio —
solo wiring.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from mme.config import Config
from mme.data.feature_set import apply_pca, load_feature_set, select_features
from mme.data.panel import PanelSplit, load_panel, split_temporal
from mme.models import glm_negbin, lgbm_poisson
from mme.models.base import ModelResult, TrainingData
from mme.paths import MME_REPORTS
from mme.tracking.mlflow_ops import log_training_run

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class TrainC3Report:
    """Reporte agregado de una ejecución de train_c3."""

    dataset_cycle: str
    n_features: int
    n_train: int
    n_val: int
    n_test: int
    clayton_kaldor_alpha: float
    clayton_kaldor_beta: float
    results: list[ModelResult]
    mlflow_run_ids: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        """Serializa a dict JSON-friendly."""
        return {
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "dataset_cycle": self.dataset_cycle,
            "n_features": self.n_features,
            "n_train": self.n_train,
            "n_val": self.n_val,
            "n_test": self.n_test,
            "clayton_kaldor": {
                "alpha": self.clayton_kaldor_alpha,
                "beta": self.clayton_kaldor_beta,
            },
            "mlflow_run_ids": self.mlflow_run_ids,
            "results": [
                {
                    "family": r.family,
                    "test": r.test_metrics.as_dict(),
                    "val": r.val_metrics.as_dict(),
                    "params": r.params,
                    "metadata": r.metadata,
                }
                for r in self.results
            ],
        }


def _prepare_training_data(split: PanelSplit, features: list[str]) -> TrainingData:
    """Construye TrainingData desde PanelSplit + lista de features."""
    x_train = select_features(split.train, features)
    x_val = select_features(split.val, features)
    x_test = select_features(split.test, features)
    return TrainingData(
        X_train=x_train,
        y_train=split.train["casos_mme"].to_numpy(dtype=float),
        offset_train=split.train["log_offset"].to_numpy(dtype=float),
        X_val=x_val,
        y_val=split.val["casos_mme"].to_numpy(dtype=float),
        offset_val=split.val["log_offset"].to_numpy(dtype=float),
        X_test=x_test,
        y_test=split.test["casos_mme"].to_numpy(dtype=float),
        offset_test=split.test["log_offset"].to_numpy(dtype=float),
        pop_sem_val=split.val["pop_sem"].to_numpy(dtype=float),
        pop_sem_test=split.test["pop_sem"].to_numpy(dtype=float),
        cod_dpto_val=split.val["cod_dpto"].to_numpy(),
        cod_dpto_test=split.test["cod_dpto"].to_numpy(),
    )


def run(
    *,
    config: Config | None = None,
    dataset_cycle: str | None = None,
    mlflow_enabled: bool = True,
) -> TrainC3Report:
    """Ejecuta el training pipeline completo.

    Args:
        config: Config override (default: env vars via ``Config()``).
        dataset_cycle: ISO date string identificador. Default: hoy UTC.
        mlflow_enabled: Si ``True``, loguea cada modelo a MLflow y retorna
            los run_ids en ``TrainC3Report.mlflow_run_ids``. Útil apagarlo
            para tests que no deben tocar el tracking server.

    Returns:
        TrainC3Report con resultados de todos los modelos.
    """
    cfg = config or Config()
    cycle = dataset_cycle or datetime.now(UTC).strftime("%Y-%m-%d")

    panel = load_panel()
    fs = load_feature_set()
    panel = apply_pca(panel, fs)
    split = split_temporal(panel)

    data = _prepare_training_data(split, fs.features_final)

    results: list[ModelResult] = [
        glm_negbin.train(data),
        lgbm_poisson.train(data, cfg.training),
    ]

    run_ids: dict[str, str] = {}
    if mlflow_enabled:
        common_tags = {
            "feature_spec_version": cfg.feature_spec_version,
            "split_strategy": "temporal_2022_test",
            "n_train": str(split.n_train),
            "n_val": str(split.n_val),
            "n_test": str(split.n_test),
        }
        # Baseline = panel train+val post-PCA filtrado a features finales.
        # Representa la distribución que el modelo conoce (sin leak del test).
        baseline_df = pd.concat(
            [data.X_train, data.X_val], axis=0, ignore_index=True,
        )
        y_train_val = np.concatenate([data.y_train, data.y_val])
        for result in results:
            # Residuos (observado - predicho) sobre train+val — base del bootstrap CI.
            residuals = (y_train_val - result.y_pred_train_val).astype(np.float64)
            run_ids[result.family] = log_training_run(
                result,
                experiment_name=cfg.mlflow.experiment_name,
                dataset_cycle=cycle,
                tracking_uri=cfg.mlflow.tracking_uri,
                extra_tags=common_tags,
                baseline_df=baseline_df,
                residuals=residuals,
            )

    return TrainC3Report(
        dataset_cycle=cycle,
        n_features=len(fs.features_final),
        n_train=split.n_train,
        n_val=split.n_val,
        n_test=split.n_test,
        clayton_kaldor_alpha=split.clayton_kaldor.alpha,
        clayton_kaldor_beta=split.clayton_kaldor.beta,
        results=results,
        mlflow_run_ids=run_ids,
    )


def persist_report(report: TrainC3Report, out_dir: Path | None = None) -> Path:
    """Guarda el reporte JSON en reports/mme/models/."""
    target_dir = out_dir or (MME_REPORTS / "models")
    target_dir.mkdir(parents=True, exist_ok=True)
    out_path = target_dir / f"train_c3_{report.dataset_cycle}.json"
    out_path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    return out_path
