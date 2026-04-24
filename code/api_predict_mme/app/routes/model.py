"""Endpoints de metadata y refresh del modelo champion."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from app.schemas import ModelInfo, ReloadResponse
from app.services.model_store import ChampionNotFoundError

router = APIRouter(prefix="/model", tags=["model"])


@router.get("/info", response_model=ModelInfo)
async def model_info(request: Request) -> ModelInfo:
    """Metadata del champion activo."""
    try:
        bundle = request.app.state.model_store.bundle
    except ChampionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc),
        ) from exc

    return ModelInfo(
        registered_model_name=request.app.state.settings.registered_model_name,
        version=bundle.version,
        run_id=bundle.run_id,
        family=bundle.family,
        test_spearman_dpto=bundle.test_spearman_dpto,
        test_precision_at_50=bundle.test_precision_at_50,
        dataset_cycle=bundle.dataset_cycle,
        feature_spec_version=bundle.feature_spec_version,
        n_features=len(bundle.feature_names),
        residuals_available=bundle.residuals is not None,
        baseline_available=bundle.baseline_df is not None,
    )


@router.post("/reload", response_model=ReloadResponse)
async def model_reload(request: Request) -> ReloadResponse:
    """Re-descubre el champion y recarga modelo + residuals + baseline."""
    store = request.app.state.model_store
    try:
        prev, new = store.reload()
    except ChampionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc),
        ) from exc

    # Invalidar panel cache para forzar reload (por si feature_set cambió)
    request.app.state.panel_cache.invalidate()

    return ReloadResponse(
        reloaded=prev != new,
        previous_version=prev,
        new_version=new,
        message=(
            f"Promoted {prev} → {new}" if prev != new
            else f"Ya estaba en version {new} — panel cache invalidado"
        ),
    )
