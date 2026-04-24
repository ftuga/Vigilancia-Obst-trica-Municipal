"""Endpoints de salud."""
from __future__ import annotations

from fastapi import APIRouter, Request

from app.schemas import HealthResponse
from app.services.model_store import ChampionNotFoundError

router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    """Liveness: simple echo."""
    return HealthResponse(status="ok", service="api_predict_mme", details={})


@router.get("/readyz", response_model=HealthResponse)
async def readyz(request: Request) -> HealthResponse:
    """Readiness: modelo cargado + panel disponible."""
    details: dict[str, str | bool | int | float] = {}
    try:
        bundle = request.app.state.model_store.bundle
        details["model_version"] = bundle.version
        details["residuals_available"] = bundle.residuals is not None
        details["baseline_available"] = bundle.baseline_df is not None
        details["test_spearman_dpto"] = bundle.test_spearman_dpto
    except ChampionNotFoundError as exc:
        return HealthResponse(
            status="error",
            service="api_predict_mme",
            details={"error": str(exc)},
        )

    try:
        panel_snap = request.app.state.panel_cache.get()
        details["panel_rows"] = panel_snap.n_rows
        details["panel_fs_version"] = panel_snap.feature_spec_version
    except Exception as exc:  # noqa: BLE001
        return HealthResponse(
            status="degraded",
            service="api_predict_mme",
            details={**details, "panel_error": str(exc)},
        )

    return HealthResponse(status="ok", service="api_predict_mme", details=details)
