"""Configuración tipada de la API via pydantic-settings."""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings del servicio.

    Los valores por defecto asumen ejecución dentro del compose; para
    desarrollo local sobreescribir vía ``.env`` o env vars.
    """

    model_config = SettingsConfigDict(
        env_prefix="API_MME_",
        env_file=".env",
        extra="ignore",
    )

    # MLflow / Registry
    mlflow_tracking_uri: str = "http://mlflow:5000"
    registered_model_name: str = "mme_vulnerability_baseline"
    champion_alias: str = "champion"

    # Bootstrap CI
    ci_alpha: float = Field(default=0.10, ge=0.01, le=0.50)
    n_bootstrap: int = Field(default=200, ge=50, le=2000)
    bootstrap_seed: int = 42

    # Panel cache
    panel_cache_ttl_seconds: int = Field(default=3600, ge=60)

    # API
    service_name: str = "api_predict_mme"
    log_level: str = "INFO"
