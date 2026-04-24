"""MLflow ops: logging de runs de training y promoción gated al Registry.

Dos entry points:
    - ``log_training_run(result, ...)`` — loguea un ModelResult a MLflow como
      run independiente (params + metrics + model). Retorna run_id.
    - ``promote_champion(...)`` — rankea runs del experimento por
      ``test_spearman_dpto`` y promueve el mejor al Registry si pasa el gate
      combinado ``new >= prev*tolerance OR new >= absolute_floor``.

Convenciones:
    - Stages están deprecated desde MLflow 2.9; acá usamos aliases
      (``@champion``). El champion vigente se referencia como
      ``models:/<registered_model_name>@champion``.
    - GLM NegBin se serializa con un pyfunc wrapper (statsmodels no tiene
      flavor nativo en MLflow). LightGBM Booster usa ``mlflow.lightgbm``.
"""
from __future__ import annotations

import contextlib
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import mlflow
import numpy as np
import pandas as pd
import statsmodels.api as sm
from mlflow.client import MlflowClient
from mlflow.exceptions import MlflowException
from mlflow.models.signature import infer_signature

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from mme.models.base import ModelResult

logger = logging.getLogger(__name__)

_FAMILIES_LOG_SUPPORTED = ("lgbm_poisson", "glm_negbin")
DRIFT_BASELINE_ARTIFACT = "drift/baseline.parquet"
RESIDUALS_ARTIFACT = "diagnostics/residuals.npy"


class _UnsupportedFamilyError(ValueError):
    """Raised when log_model cannot serialize the given ModelResult family."""

    def __init__(self, family: str) -> None:
        super().__init__(f"familia no soportada para log_model: {family}")

_CHAMPION_ALIAS_DEFAULT = "champion"
_METRIC_DEFAULT = "test_spearman_dpto"


class _NegBinPyFunc(mlflow.pyfunc.PythonModel):  # type: ignore[misc, name-defined]
    """Wrapper pyfunc para GLM NegBin packed (statsmodels + StandardScaler).

    Ver ``mme.models.glm_negbin.train`` — ``ModelResult.model`` es un dict con
    ``{model, scaler_mean, scaler_scale, features}``. Este wrapper replica el
    predict de statsmodels sin reentrenar el scaler.
    """

    def __init__(self, packed: dict[str, Any]) -> None:
        self._packed = packed

    def predict(
        self,
        context: Any,  # noqa: ARG002 — required by pyfunc.PythonModel signature
        model_input: pd.DataFrame,
        params: dict[str, Any] | None = None,
    ) -> NDArray[np.float64]:
        features = self._packed["features"]
        mean = np.asarray(self._packed["scaler_mean"], dtype=np.float64)
        scale = np.asarray(self._packed["scaler_scale"], dtype=np.float64)
        model = self._packed["model"]

        x = np.asarray(model_input[features].to_numpy(), dtype=np.float64)
        xs = (x - mean) / scale
        xc = sm.add_constant(xs, has_constant="add")
        if params and "offset" in params:
            offset = np.asarray(params["offset"], dtype=np.float64)
            return np.asarray(model.predict(xc, offset=offset), dtype=np.float64)
        return np.asarray(model.predict(xc), dtype=np.float64)


@dataclass(frozen=True)
class PromotionDecision:
    """Resultado de ``promote_champion``."""

    promoted: bool
    registered_model_name: str
    new_version: str | None
    new_run_id: str | None
    new_score: float | None
    prev_version: str | None
    prev_score: float | None
    reason: str


def _log_model_for_family(result: ModelResult, artifact_path: str = "model") -> None:
    """Loguea el objeto modelo según la familia. Mantiene artifact_path=, no name=."""
    if result.family.startswith("lgbm"):
        mlflow.lightgbm.log_model(result.model, artifact_path=artifact_path)
        return
    if result.family == "glm_negbin":
        features = result.model["features"]
        sample_input = pd.DataFrame({f: [0.0] for f in features})
        sample_output = np.array([0.0])
        signature = infer_signature(sample_input, sample_output)
        mlflow.pyfunc.log_model(
            artifact_path=artifact_path,
            python_model=_NegBinPyFunc(result.model),
            signature=signature,
        )
        return
    raise _UnsupportedFamilyError(result.family)


def _log_baseline_artifact(baseline_df: pd.DataFrame) -> None:
    """Persiste ``baseline_df`` como artifact del run activo (``drift/baseline.parquet``)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        bpath = Path(tmpdir) / "baseline.parquet"
        baseline_df.to_parquet(bpath, index=False)
        mlflow.log_artifact(str(bpath), artifact_path="drift")


def _log_residuals_artifact(residuals: NDArray[np.float64]) -> None:
    """Persiste residuos train+val como ``diagnostics/residuals.npy`` para bootstrap CI."""
    with tempfile.TemporaryDirectory() as tmpdir:
        rpath = Path(tmpdir) / "residuals.npy"
        np.save(rpath, residuals)
        mlflow.log_artifact(str(rpath), artifact_path="diagnostics")


def log_training_run(
    result: ModelResult,
    *,
    experiment_name: str,
    dataset_cycle: str,
    tracking_uri: str | None = None,
    extra_tags: dict[str, str] | None = None,
    baseline_df: pd.DataFrame | None = None,
    residuals: NDArray[np.float64] | None = None,
) -> str:
    """Loguea un ``ModelResult`` a MLflow como run independiente.

    Args:
        result: Resultado del training (ver ``mme.models.base.ModelResult``).
        experiment_name: Experimento MLflow (se crea si no existe).
        dataset_cycle: ISO date del ciclo de training.
        tracking_uri: Override del tracking server. Si ``None`` usa env/config.
        extra_tags: Tags adicionales (e.g. ``{"split_strategy": "temporal"}``).
        baseline_df: Si se provee, se persiste como artifact
            ``drift/baseline.parquet`` — usado por ``load_champion_baseline``
            en el próximo ciclo para detectar drift.
        residuals: Si se provee, se persiste como artifact
            ``diagnostics/residuals.npy`` — usado por la API de serving para
            computar intervalos de confianza bootstrap por predicción.

    Returns:
        run_id del run MLflow creado.
    """
    if tracking_uri:
        mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment_name)

    run_name = f"{result.family}__{dataset_cycle}"
    with mlflow.start_run(run_name=run_name) as mlrun:
        mlflow.set_tag("family", result.family)
        mlflow.set_tag("dataset_cycle", dataset_cycle)
        if extra_tags:
            for k, v in extra_tags.items():
                mlflow.set_tag(k, v)

        if result.params:
            mlflow.log_params(result.params)
        for key, value in result.metadata.items():
            if isinstance(value, (int, float, str, bool)):
                mlflow.set_tag(f"meta.{key}", str(value))

        for split_name, split_metrics in (
            ("train", None),
            ("val", result.val_metrics),
            ("test", result.test_metrics),
        ):
            if split_metrics is None:
                continue
            for metric_key, metric_value in split_metrics.as_dict().items():
                if metric_value is None or not np.isfinite(metric_value):
                    continue
                mlflow.log_metric(f"{split_name}_{metric_key}", float(metric_value))

        _log_model_for_family(result)
        if baseline_df is not None:
            _log_baseline_artifact(baseline_df)
        if residuals is not None:
            _log_residuals_artifact(residuals)
        return cast("str", mlrun.info.run_id)


def load_champion_residuals(
    registered_model_name: str,
    *,
    champion_alias: str = _CHAMPION_ALIAS_DEFAULT,
    artifact_name: str = RESIDUALS_ARTIFACT,
    client: MlflowClient | None = None,
) -> NDArray[np.float64] | None:
    """Descarga los residuos train+val del champion (para bootstrap CI en la API).

    Returns ``None`` si no hay champion o el artifact no fue logueado.
    """
    cli = client if client is not None else MlflowClient()
    try:
        version = cli.get_model_version_by_alias(
            registered_model_name, champion_alias,
        )
    except MlflowException:
        return None
    if version.run_id is None:
        return None
    try:
        local = cli.download_artifacts(version.run_id, artifact_name)
    except (MlflowException, OSError):
        logger.warning(
            "champion %s@%s (run %s) sin artifact %s — bootstrap CI no disponible",
            registered_model_name, champion_alias, version.run_id, artifact_name,
        )
        return None
    return cast("NDArray[np.float64]", np.load(local))


def load_champion_baseline(
    registered_model_name: str,
    *,
    champion_alias: str = _CHAMPION_ALIAS_DEFAULT,
    artifact_name: str = DRIFT_BASELINE_ARTIFACT,
    client: MlflowClient | None = None,
) -> pd.DataFrame | None:
    """Descarga el baseline.parquet del run asociado al champion vigente.

    Args:
        registered_model_name: Modelo en el Registry.
        champion_alias: Alias que identifica producción. Default ``"champion"``.
        artifact_name: Ruta relativa dentro de los artifacts del run.
            Default ``"drift/baseline.parquet"``.
        client: ``MlflowClient`` override (para tests).

    Returns:
        ``DataFrame`` si el champion existe y tiene el artifact. ``None`` si
        no hay champion o el artifact no está (primer run post-deploy).
    """
    cli = client if client is not None else MlflowClient()
    try:
        version = cli.get_model_version_by_alias(
            registered_model_name, champion_alias,
        )
    except MlflowException:
        return None
    if version.run_id is None:
        return None
    try:
        local = cli.download_artifacts(version.run_id, artifact_name)
    except (MlflowException, OSError):
        logger.warning(
            "champion %s@%s (run %s) no tiene artifact %s — drift=unknown",
            registered_model_name, champion_alias, version.run_id, artifact_name,
        )
        return None
    return pd.read_parquet(local)


def _get_current_champion(
    client: MlflowClient,
    registered_model_name: str,
    champion_alias: str,
    metric: str,
) -> tuple[str | None, float | None]:
    """Retorna (version, metric_value) del champion vigente, o (None, None) si no hay."""
    try:
        version = client.get_model_version_by_alias(
            registered_model_name, champion_alias,
        )
    except MlflowException:
        return None, None
    if version.run_id is None:
        return version.version, None
    run = client.get_run(version.run_id)
    prev_score = run.data.metrics.get(metric)
    return version.version, prev_score


def _rank_candidates(
    client: MlflowClient,
    experiment_name: str,
    metric: str,
    allowed_families: set[str],
) -> list[tuple[str, float]]:
    """Rankea runs FINISHED del experimento por ``metric`` descendente.

    Filtra por ``tags.family IN allowed_families``. Retorna lista de
    ``(run_id, metric_value)``.
    """
    exp = client.get_experiment_by_name(experiment_name)
    if exp is None:
        return []
    runs = client.search_runs(
        experiment_ids=[exp.experiment_id],
        filter_string="attributes.status = 'FINISHED'",
        order_by=[f"metrics.{metric} DESC"],
        max_results=200,
    )
    ranked: list[tuple[str, float]] = []
    for r in runs:
        family = r.data.tags.get("family")
        if family not in allowed_families:
            continue
        score = r.data.metrics.get(metric)
        if score is None or not np.isfinite(score):
            continue
        ranked.append((r.info.run_id, float(score)))
    return ranked


def _register_and_alias(
    client: MlflowClient,
    registered_model_name: str,
    run_id: str,
    champion_alias: str,
    artifact_path: str = "model",
) -> str:
    """Registra un run como nueva version y apunta el alias al resultado."""
    with contextlib.suppress(MlflowException):
        client.create_registered_model(registered_model_name)

    model_uri = f"runs:/{run_id}/{artifact_path}"
    mv = client.create_model_version(
        name=registered_model_name, source=model_uri, run_id=run_id,
    )
    client.set_registered_model_alias(
        registered_model_name, champion_alias, mv.version,
    )
    return mv.version


def promote_champion(
    *,
    experiment_name: str,
    registered_model_name: str,
    champion_alias: str = _CHAMPION_ALIAS_DEFAULT,
    metric: str = _METRIC_DEFAULT,
    tolerance: float = 0.95,
    absolute_floor: float = 0.65,
    allowed_families: set[str] | None = None,
    dry_run: bool = False,
    client: MlflowClient | None = None,
) -> PromotionDecision:
    """Promueve el mejor run del experimento al Registry si pasa el gate.

    Gate combinado: ``new >= prev * tolerance OR new >= absolute_floor``.
    Si no hay champion previo, solo aplica ``new >= absolute_floor``.

    Args:
        experiment_name: Experimento MLflow fuente.
        registered_model_name: Modelo en el Registry (se crea si no existe).
        champion_alias: Alias que marca el modelo en producción. Default
            ``"champion"``.
        metric: Métrica para rankear runs y aplicar gate. Default
            ``test_spearman_dpto``.
        tolerance: Factor multiplicativo del score previo. Default 0.95.
        absolute_floor: Score mínimo absoluto para promover sin champion
            previo, o para sobrescribir gate relativo. Default 0.65.
        allowed_families: Familias elegibles. Default
            ``{"lgbm_poisson", "glm_negbin"}``.
        dry_run: Si True, evalúa el gate pero no registra ni mueve alias.
        client: ``MlflowClient`` override (útil para tests). Si ``None`` se
            construye uno nuevo.

    Returns:
        ``PromotionDecision`` con detalle de la decisión.
    """
    if allowed_families is None:
        allowed_families = {"lgbm_poisson", "glm_negbin"}
    cli = client if client is not None else MlflowClient()

    prev_version, prev_score = _get_current_champion(
        cli, registered_model_name, champion_alias, metric,
    )
    ranked = _rank_candidates(cli, experiment_name, metric, allowed_families)
    if not ranked:
        return PromotionDecision(
            promoted=False,
            registered_model_name=registered_model_name,
            new_version=None,
            new_run_id=None,
            new_score=None,
            prev_version=prev_version,
            prev_score=prev_score,
            reason="no_candidates_found",
        )

    new_run_id, new_score = ranked[0]

    if prev_score is None:
        passes = new_score >= absolute_floor
        reason = (
            f"first_champion: score={new_score:.4f} >= floor={absolute_floor:.4f}"
            if passes
            else f"first_champion_rejected: score={new_score:.4f} < floor={absolute_floor:.4f}"
        )
    else:
        passes_relative = new_score >= prev_score * tolerance
        passes_absolute = new_score >= absolute_floor
        passes = passes_relative or passes_absolute
        reason = (
            f"gate_pass: new={new_score:.4f} prev={prev_score:.4f} "
            f"tolerance={tolerance} floor={absolute_floor:.4f}"
            if passes
            else f"gate_fail: new={new_score:.4f} prev={prev_score:.4f} "
                 f"tolerance={tolerance} floor={absolute_floor:.4f}"
        )

    if not passes or dry_run:
        return PromotionDecision(
            promoted=False,
            registered_model_name=registered_model_name,
            new_version=None,
            new_run_id=new_run_id,
            new_score=new_score,
            prev_version=prev_version,
            prev_score=prev_score,
            reason=f"{reason}{' [dry_run]' if dry_run else ''}",
        )

    new_version = _register_and_alias(
        cli, registered_model_name, new_run_id, champion_alias,
    )
    logger.info(
        "Promoted run %s to %s@%s as version %s",
        new_run_id, registered_model_name, champion_alias, new_version,
    )
    return PromotionDecision(
        promoted=True,
        registered_model_name=registered_model_name,
        new_version=new_version,
        new_run_id=new_run_id,
        new_score=new_score,
        prev_version=prev_version,
        prev_score=prev_score,
        reason=reason,
    )
