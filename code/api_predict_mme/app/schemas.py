"""Pydantic DTOs públicos de la API."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PredictRequest(BaseModel):
    """Solicitud de predicción para un municipio."""

    cod_mpio: str = Field(
        ...,
        description="Código DIVIPOLA del municipio (5 dígitos, ej. '05001').",
        pattern=r"^\d{5}$",
        examples=["05001", "11001", "91001"],
    )
    anio: int | None = Field(
        default=None,
        ge=2016,
        le=2030,
        description="Año objetivo (default: último año disponible en el panel).",
    )


class BatchPredictRequest(BaseModel):
    """Solicitud batch para varios municipios."""

    cod_mpios: list[str] = Field(..., min_length=1, max_length=1122)
    anio: int | None = Field(default=None, ge=2016, le=2030)


class PredictResponse(BaseModel):
    """Respuesta de predicción con intervalo bootstrap."""

    cod_mpio: str
    departamento_cod: str
    anio: int
    casos_mme_predichos: float = Field(
        ..., description="Casos MME esperados (escala count) semestre.",
    )
    ci_low: float = Field(..., description="Límite inferior del intervalo bootstrap.")
    ci_high: float = Field(..., description="Límite superior del intervalo bootstrap.")
    ci_level: float = Field(..., description="Nivel de confianza (0-1).")
    razon_mme_por_1000: float = Field(
        ...,
        description="Razón MME por 1.000 habitantes en el semestre.",
    )
    risk_tier: Literal["alto", "medio", "bajo"] = Field(
        ...,
        description="Clasificación cualitativa del riesgo predicho.",
    )
    n_bootstrap: int = Field(..., description="Bootstrap replicates usados.")
    feature_spec_version: str = Field(..., description="Versión del feature set usado.")


class RankingItem(BaseModel):
    """Item del ranking top-N de municipios."""

    cod_mpio: str
    departamento_cod: str
    casos_mme_predichos: float
    razon_mme_por_1000: float
    ci_low: float
    ci_high: float
    risk_tier: Literal["alto", "medio", "bajo"]


class RankingResponse(BaseModel):
    """Top-N municipios por razón MME predicha."""

    departamento_cod: str | None
    anio: int
    top_n: int
    items: list[RankingItem]


class ModelInfo(BaseModel):
    """Metadata del champion activo."""

    registered_model_name: str
    version: str
    run_id: str
    family: str
    test_spearman_dpto: float
    test_precision_at_50: float
    dataset_cycle: str
    feature_spec_version: str
    n_features: int
    residuals_available: bool
    baseline_available: bool


class ReloadResponse(BaseModel):
    """Resultado de ``POST /model/reload``."""

    reloaded: bool
    previous_version: str | None
    new_version: str | None
    message: str


class HealthResponse(BaseModel):
    """Liveness / readiness probe."""

    status: Literal["ok", "degraded", "error"]
    service: str
    details: dict[str, str | bool | int | float]
