"""Configuración tipada via pydantic BaseSettings.

Reemplaza el patrón anti-patrón ``os.environ.get("X", "5")`` con cast manual.
Todas las tunables del training, ingesta y paths llegan vía env ``MME_*``.

Ejemplo::

    from mme.config import Config
    cfg = Config()
    print(cfg.optuna_n_trials)  # 100 o valor de MME_OPTUNA_N_TRIALS
"""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TrainingConfig(BaseSettings):
    """Hiperparametros de entrenamiento C3."""

    model_config = SettingsConfigDict(env_prefix="MME_", extra="ignore")

    optuna_n_trials: int = Field(default=100, ge=1, le=1000)
    optuna_seed: int = 42
    lgbm_num_threads: int = Field(default=4, ge=1, le=32)
    lgbm_num_boost_round: int = 200
    lgbm_early_stopping: int = 20
    xgb_num_boost_round: int = 200
    xgb_early_stopping: int = 20
    pca_nbi_variance_threshold: float = Field(default=0.85, ge=0.5, le=0.99)
    clayton_kaldor_min_pop_sem: float = 1.0


class MLflowConfig(BaseSettings):
    """Configuración del tracking MLflow."""

    model_config = SettingsConfigDict(env_prefix="MLFLOW_", extra="ignore")

    tracking_uri: str = "http://localhost:5000"
    s3_endpoint_url: str = "http://localhost:9000"
    experiment_name: str = "mme_vulnerability_v1"


class PathsConfig(BaseSettings):
    """Paths del medallón. Override via env MME_DATA_ROOT / MME_REPORTS_ROOT."""

    model_config = SettingsConfigDict(env_prefix="MME_", extra="ignore")

    data_root: Path | None = None
    reports_root: Path | None = None


class Config(BaseSettings):
    """Config raíz del paquete. Aglomera sub-configs por dominio."""

    model_config = SettingsConfigDict(env_prefix="MME_", extra="ignore")

    training: TrainingConfig = Field(default_factory=TrainingConfig)
    mlflow: MLflowConfig = Field(default_factory=MLflowConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    feature_spec_version: str = "v1"
