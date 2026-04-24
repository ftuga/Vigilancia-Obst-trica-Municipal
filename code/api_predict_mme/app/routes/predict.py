"""Endpoints de predicción individual y batch."""
from __future__ import annotations

import numpy as np
from fastapi import APIRouter, HTTPException, Request, status

from app.schemas import (
    BatchPredictRequest,
    PredictRequest,
    PredictResponse,
    RankingItem,
)
from app.services.bootstrap import classify_risk, compute_ci
from app.services.model_store import ChampionNotFoundError
from app.services.panel_loader import filter_municipio

router = APIRouter(prefix="/predict", tags=["predict"])


def _predict_one(
    request: Request, cod_mpio: str, anio: int | None,
) -> PredictResponse:
    """Lógica central: filtra panel, predice, bootstrap CI, retorna DTO."""
    settings = request.app.state.settings
    store = request.app.state.model_store
    cache = request.app.state.panel_cache

    try:
        bundle = store.bundle
    except ChampionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc),
        ) from exc

    snap = cache.get()
    try:
        features_df = filter_municipio(
            snap.panel, cod_mpio, bundle.feature_names, anio,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc),
        ) from exc

    # El modelo lgbm fue entrenado con log_pop_sem como feature agregada
    # (ver mme.features.augment.augment_with_offset). Replicamos aquí.
    row = snap.panel[
        snap.panel["cod_mpio"].astype(str).str.zfill(5) == cod_mpio
    ]
    if anio is not None:
        row = row[row["ano"] == anio]
    pop_sem = float(row["pop_sem"].mean()) if "pop_sem" in row.columns else 1.0
    pop_sem = max(pop_sem, 1.0)
    log_pop_sem = float(np.log(pop_sem))
    x = np.concatenate([features_df.to_numpy(dtype=float)[0], [log_pop_sem]])
    y_point = store.predict(x)

    # Intervalo bootstrap
    residuals = bundle.residuals
    if residuals is None:
        residuals = np.empty(0, dtype=float)
    ci = compute_ci(
        y_point,
        residuals,
        alpha=settings.ci_alpha,
        n_bootstrap=settings.n_bootstrap,
        seed=settings.bootstrap_seed,
    )

    # Población para la razón: la columna que el panel lleva (pop_sem).
    # Si el panel fue promediado por muni, la columna pop_sem sigue presente.
    row = snap.panel[snap.panel["cod_mpio"].astype(str).str.zfill(5) == cod_mpio]
    if anio is not None:
        row = row[row["ano"] == anio]
    pop_sem = float(row["pop_sem"].mean()) if "pop_sem" in row.columns else 1.0
    pop_sem = max(pop_sem, 1.0)  # evita div/0
    razon = y_point * 1000.0 / pop_sem

    cod_dpto = (
        str(row["cod_dpto"].iloc[0])
        if "cod_dpto" in row.columns and len(row)
        else cod_mpio[:2]
    )
    anio_used = int(row["ano"].max()) if len(row) and anio is None else (anio or 0)

    return PredictResponse(
        cod_mpio=cod_mpio,
        departamento_cod=cod_dpto,
        anio=anio_used,
        casos_mme_predichos=round(y_point, 4),
        ci_low=round(ci.low, 4),
        ci_high=round(ci.high, 4),
        ci_level=round(1.0 - settings.ci_alpha, 2),
        razon_mme_por_1000=round(razon, 4),
        risk_tier=classify_risk(razon),  # type: ignore[arg-type]
        n_bootstrap=ci.n_bootstrap,
        feature_spec_version=bundle.feature_spec_version,
    )


@router.post("/municipio", response_model=PredictResponse)
async def predict_municipio(
    body: PredictRequest, request: Request,
) -> PredictResponse:
    """Predicción para un municipio individual con 90% CI bootstrap."""
    return _predict_one(request, body.cod_mpio, body.anio)


@router.post("/batch", response_model=list[PredictResponse])
async def predict_batch(
    body: BatchPredictRequest, request: Request,
) -> list[PredictResponse]:
    """Predicción batch para múltiples municipios (mismo año)."""
    out: list[PredictResponse] = []
    for cod in body.cod_mpios:
        try:
            out.append(_predict_one(request, cod, body.anio))
        except HTTPException:
            # Skip municipios no encontrados; reporta solo los que existen
            continue
    return out


@router.get("/ranking", response_model=list[RankingItem])
async def ranking(
    request: Request,
    departamento: str | None = None,
    top_n: int = 10,
    anio: int | None = None,
) -> list[RankingItem]:
    """Top-N municipios por razón MME predicha, opcionalmente filtrados por dpto."""
    from app.services.panel_loader import filter_departamento

    settings = request.app.state.settings
    store = request.app.state.model_store
    cache = request.app.state.panel_cache

    try:
        bundle = store.bundle
    except ChampionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc),
        ) from exc

    snap = cache.get()
    try:
        df = filter_departamento(
            snap.panel, departamento, bundle.feature_names, anio,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc),
        ) from exc

    # Agregar log_pop_sem como 15º feature (consistente con training)
    pop_sem_by_muni = {}
    for _, r in df.iterrows():
        panel_row = snap.panel[
            (snap.panel["cod_mpio"].astype(str).str.zfill(5) ==
             str(r["cod_mpio"]).zfill(5))
            & (snap.panel["ano"] == r["_anio"])
        ]
        pop_sem_by_muni[str(r["cod_mpio"]).zfill(5)] = (
            max(float(panel_row["pop_sem"].mean()), 1.0) if len(panel_row) else 1.0
        )
    log_pop_col = np.array([
        np.log(pop_sem_by_muni[str(cm).zfill(5)]) for cm in df["cod_mpio"]
    ])
    x_base = df[bundle.feature_names].to_numpy(dtype=float)
    x = np.column_stack([x_base, log_pop_col])
    # Predict vectorial para LightGBM (rápido). GLM NegBin: loop.
    if bundle.family.startswith("lgbm"):
        y_pred = bundle.model.predict(x)
    else:
        y_pred = [store.predict(row) for row in x]

    # Bootstrap CI por muni (escala lineal, fast)
    residuals = bundle.residuals if bundle.residuals is not None else np.empty(0)

    items: list[RankingItem] = []
    for i, cod_mpio in enumerate(df["cod_mpio"].tolist()):
        y_point = float(y_pred[i])
        ci = compute_ci(
            y_point, residuals,
            alpha=settings.ci_alpha,
            n_bootstrap=settings.n_bootstrap,
            seed=settings.bootstrap_seed,
        )
        # Razón por 1000: reutilizo pop_sem mínimo 1.0
        pop_row = snap.panel[
            (snap.panel["cod_mpio"].astype(str) == str(cod_mpio))
            & (snap.panel["ano"] == df.iloc[i]["_anio"])
        ]
        pop = max(float(pop_row["pop_sem"].mean()), 1.0) if len(pop_row) else 1.0
        razon = y_point * 1000.0 / pop
        items.append(
            RankingItem(
                cod_mpio=str(cod_mpio),
                departamento_cod=str(df.iloc[i]["cod_dpto"]),
                casos_mme_predichos=round(y_point, 4),
                ci_low=round(ci.low, 4),
                ci_high=round(ci.high, 4),
                razon_mme_por_1000=round(razon, 4),
                risk_tier=classify_risk(razon),  # type: ignore[arg-type]
            ),
        )
    items.sort(key=lambda it: it.razon_mme_por_1000, reverse=True)
    return items[:top_n]
