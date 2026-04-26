"""Endpoints de predicción individual, batch y A/B compare."""
from __future__ import annotations

import numpy as np
from fastapi import APIRouter, HTTPException, Request, status

from app.schemas import (
    ABCompareResponse,
    BatchPredictRequest,
    PredictRequest,
    PredictResponse,
    RankingItem,
)
from app.services.bootstrap import classify_risk, compute_ci
from app.services.model_store import ChampionNotFoundError, ModelStore
from app.services.panel_loader import filter_municipio

router = APIRouter(prefix="/predict", tags=["predict"])


def _predict_one(
    request: Request,
    cod_mpio: str,
    anio: int | None,
    *,
    store: ModelStore | None = None,
) -> PredictResponse:
    """Lógica central: filtra panel, predice, bootstrap CI, retorna DTO.

    Si ``store`` es None usa el champion (default).  Pasar el store
    challenger habilita A/B testing sin duplicar lógica.
    """
    settings = request.app.state.settings
    if store is None:
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
        str(int(row["cod_dpto"].iloc[0])).zfill(2)
        if "cod_dpto" in row.columns and len(row)
        else cod_mpio[:2]
    )
    nom_mpio = (
        str(row["nom_mpio"].iloc[0])
        if "nom_mpio" in row.columns and len(row)
        else None
    )
    nom_dpto = (
        str(row["nom_dpto"].iloc[0])
        if "nom_dpto" in row.columns and len(row)
        else None
    )
    anio_used = int(row["ano"].max()) if len(row) and anio is None else (anio or 0)

    return PredictResponse(
        cod_mpio=cod_mpio,
        nom_mpio=nom_mpio,
        departamento_cod=cod_dpto,
        nom_dpto=nom_dpto,
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


@router.post("/compare", response_model=ABCompareResponse)
async def predict_compare(
    body: PredictRequest, request: Request,
) -> ABCompareResponse:
    """A/B compare champion vs challenger para un municipio.

    Si el alias ``challenger`` no existe en el Registry, ``challenger`` queda
    en ``null`` y los deltas también. La predicción del champion siempre
    se devuelve.
    """
    champ = _predict_one(request, body.cod_mpio, body.anio)

    chal_store: ModelStore = request.app.state.model_store_challenger
    challenger: PredictResponse | None = None
    delta_casos: float | None = None
    delta_razon: float | None = None
    try:
        challenger = _predict_one(
            request, body.cod_mpio, body.anio, store=chal_store,
        )
        delta_casos = round(
            challenger.casos_mme_predichos - champ.casos_mme_predichos, 4,
        )
        delta_razon = round(
            challenger.razon_mme_por_1000 - champ.razon_mme_por_1000, 4,
        )
    except (ChampionNotFoundError, HTTPException):
        pass

    return ABCompareResponse(
        cod_mpio=champ.cod_mpio,
        anio=champ.anio,
        champion=champ,
        challenger=challenger,
        delta_casos_mme=delta_casos,
        delta_razon=delta_razon,
    )


@router.get("/ranking", response_model=list[RankingItem])
async def ranking(
    request: Request,
    departamento: str | None = None,
    top_n: int = 10,  # límite real ~1.122 (todos los muni del panel)
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

    # Agregar log_pop_sem como 15º feature (consistente con training).
    # Importante: castear cod_mpio a int siempre — iterrows() upcastea Series
    # a float64 cuando hay otras cols float, lo que rompe el zfill.
    pop_sem_by_muni: dict[str, float] = {}
    cod_anio = df[["cod_mpio", "_anio"]].to_numpy()
    for cm_raw, anio_raw in cod_anio:
        cm_key = str(int(cm_raw)).zfill(5)
        panel_row = snap.panel[
            (snap.panel["cod_mpio"].astype(str).str.zfill(5) == cm_key)
            & (snap.panel["ano"] == int(anio_raw))
        ]
        pop_sem_by_muni[cm_key] = (
            max(float(panel_row["pop_sem"].mean()), 1.0) if len(panel_row) else 1.0
        )
    log_pop_col = np.array([
        np.log(pop_sem_by_muni[str(int(cm)).zfill(5)]) for cm in df["cod_mpio"]
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
        row_i = df.iloc[i]
        nom_mpio = (
            str(row_i["nom_mpio"]) if "nom_mpio" in df.columns else None
        )
        nom_dpto = (
            str(row_i["nom_dpto"]) if "nom_dpto" in df.columns else None
        )
        items.append(
            RankingItem(
                cod_mpio=str(int(cod_mpio)).zfill(5),
                nom_mpio=nom_mpio,
                departamento_cod=str(int(row_i["cod_dpto"])).zfill(2),
                nom_dpto=nom_dpto,
                casos_mme_predichos=round(y_point, 4),
                ci_low=round(ci.low, 4),
                ci_high=round(ci.high, 4),
                razon_mme_por_1000=round(razon, 4),
                risk_tier=classify_risk(razon),  # type: ignore[arg-type]
            ),
        )
    items.sort(key=lambda it: it.razon_mme_por_1000, reverse=True)
    return items[:top_n]
