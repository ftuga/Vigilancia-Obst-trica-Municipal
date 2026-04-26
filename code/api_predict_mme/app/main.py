"""FastAPI app entry point."""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from app.config import Settings
from app.routes import health, model, predict
from app.services.model_store import ChampionNotFoundError, ModelStore
from app.services.panel_loader import PanelCache

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Inicializa ModelStore + PanelCache al arrancar; cleanup no-op al parar."""
    settings = Settings()
    logging.basicConfig(level=settings.log_level)
    logger.info(
        "Starting %s · mlflow=%s · alias=%s · ci_alpha=%s",
        settings.service_name, settings.mlflow_tracking_uri,
        settings.champion_alias, settings.ci_alpha,
    )

    store = ModelStore(
        registered_model_name=settings.registered_model_name,
        champion_alias=settings.champion_alias,
        tracking_uri=settings.mlflow_tracking_uri,
    )
    try:
        store.reload()
    except ChampionNotFoundError as exc:
        # Degraded start: levantamos igual, /readyz reporta el problema
        logger.warning("Champion no cargado al arrancar: %s", exc)

    # Challenger opcional (A/B testing). Mismo modelo registrado, alias distinto.
    # Si el alias no existe en MLflow Registry, store_challenger queda con _bundle=None
    # y el endpoint /predict/compare devuelve solo champion + null.
    store_challenger = ModelStore(
        registered_model_name=settings.registered_model_name,
        champion_alias="challenger",
        tracking_uri=settings.mlflow_tracking_uri,
    )
    try:
        store_challenger.reload()
        logger.info("Challenger cargado: version=%s", store_challenger.bundle.version)
    except ChampionNotFoundError:
        logger.info("Sin alias 'challenger' en Registry — A/B compare devolverá solo champion")

    panel_cache = PanelCache(ttl_seconds=settings.panel_cache_ttl_seconds)
    # No cargamos el panel acá — lazy en el primer /predict

    app.state.settings = settings
    app.state.model_store = store
    app.state.model_store_challenger = store_challenger
    app.state.panel_cache = panel_cache
    yield


app = FastAPI(
    title="api_predict_mme",
    description=(
        "Serving del modelo C3 de vulnerabilidad obstétrica municipal. "
        "Predicción puntual + 90% CI bootstrap por municipio."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

Instrumentator().instrument(app).expose(app, endpoint="/metrics")

app.include_router(health.router)
app.include_router(model.router)
app.include_router(predict.router)
