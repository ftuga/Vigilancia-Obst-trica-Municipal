"""Descubrimiento y carga del champion desde MLflow Registry.

Singleton con ``threading.Lock`` para hot-swap seguro vía ``POST /model/reload``.
Carga:
    - El booster lgb.Booster (flavor ``mlflow.lightgbm``) o el pyfunc
      ``_NegBinPyFunc`` (para GLM NegBin).
    - Residuos (``diagnostics/residuals.npy``) para bootstrap CI.
    - Baseline (``drift/baseline.parquet``) — informativo, no se usa en predict.
    - Metadata del run (family, métricas, feature_spec_version).
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import mlflow
import numpy as np
from mlflow.client import MlflowClient
from mlflow.exceptions import MlflowException
from mme.tracking.mlflow_ops import (
    DRIFT_BASELINE_ARTIFACT,
    RESIDUALS_ARTIFACT,
    load_champion_baseline,
    load_champion_residuals,
)

if TYPE_CHECKING:
    import pandas as pd
    from numpy.typing import NDArray

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChampionBundle:
    """Todo lo que el API necesita sobre el champion vigente."""

    version: str
    run_id: str
    family: str
    model: Any  # lgb.Booster o pyfunc wrapper
    residuals: NDArray[np.float64] | None
    baseline_df: pd.DataFrame | None
    test_spearman_dpto: float
    test_precision_at_50: float
    dataset_cycle: str
    feature_spec_version: str
    feature_names: list[str]


class ChampionNotFoundError(RuntimeError):
    """Raised cuando no existe champion en el Registry."""


class ModelStore:
    """Singleton thread-safe que mantiene el ``ChampionBundle`` activo."""

    def __init__(
        self,
        *,
        registered_model_name: str,
        champion_alias: str,
        tracking_uri: str,
    ) -> None:
        self._registered_model_name = registered_model_name
        self._champion_alias = champion_alias
        self._tracking_uri = tracking_uri
        self._lock = threading.RLock()
        self._bundle: ChampionBundle | None = None
        mlflow.set_tracking_uri(tracking_uri)

    @property
    def bundle(self) -> ChampionBundle:
        """Bundle activo. Levanta ``ChampionNotFoundError`` si no se cargó."""
        with self._lock:
            if self._bundle is None:
                raise ChampionNotFoundError(
                    f"No hay champion cargado para {self._registered_model_name}. "
                    "Llamá a reload() primero.",
                )
            return self._bundle

    def _discover_version(self, client: MlflowClient) -> tuple[str, str]:
        """Retorna ``(version, run_id)`` del alias champion actual."""
        try:
            mv = client.get_model_version_by_alias(
                self._registered_model_name, self._champion_alias,
            )
        except MlflowException as exc:
            msg = (
                f"Alias '{self._champion_alias}' no encontrado para "
                f"'{self._registered_model_name}'"
            )
            raise ChampionNotFoundError(msg) from exc
        if mv.run_id is None:
            msg = f"Version {mv.version} no tiene run_id asociado"
            raise ChampionNotFoundError(msg)
        return str(mv.version), str(mv.run_id)

    def _load_model(self, run_id: str, family: str) -> Any:
        """Carga el modelo según la familia."""
        model_uri = f"runs:/{run_id}/model"
        if family.startswith("lgbm"):
            return mlflow.lightgbm.load_model(model_uri)
        if family == "glm_negbin":
            return mlflow.pyfunc.load_model(model_uri)
        msg = f"Familia desconocida para load_model: {family}"
        raise ChampionNotFoundError(msg)

    def reload(self) -> tuple[str | None, str]:
        """Re-descubre champion y recarga bundle. Retorna ``(prev_version, new_version)``."""
        client = MlflowClient()
        with self._lock:
            prev_version = self._bundle.version if self._bundle else None
            new_version, run_id = self._discover_version(client)

            run = client.get_run(run_id)
            family = run.data.tags.get("family", "unknown")
            feature_spec_version = run.data.tags.get("feature_spec_version", "v1")
            dataset_cycle = run.data.tags.get("dataset_cycle", "unknown")

            model = self._load_model(run_id, family)
            residuals = load_champion_residuals(
                self._registered_model_name,
                champion_alias=self._champion_alias,
                artifact_name=RESIDUALS_ARTIFACT,
                client=client,
            )
            baseline_df = load_champion_baseline(
                self._registered_model_name,
                champion_alias=self._champion_alias,
                artifact_name=DRIFT_BASELINE_ARTIFACT,
                client=client,
            )
            feature_names = (
                list(baseline_df.columns) if baseline_df is not None else []
            )

            self._bundle = ChampionBundle(
                version=new_version,
                run_id=run_id,
                family=family,
                model=model,
                residuals=residuals,
                baseline_df=baseline_df,
                test_spearman_dpto=float(
                    run.data.metrics.get("test_spearman_dpto", float("nan")),
                ),
                test_precision_at_50=float(
                    run.data.metrics.get("test_precision_at_50", float("nan")),
                ),
                dataset_cycle=dataset_cycle,
                feature_spec_version=feature_spec_version,
                feature_names=feature_names,
            )
            logger.info(
                "ModelStore reload: prev=%s new=%s family=%s run=%s",
                prev_version, new_version, family, run_id,
            )
            return prev_version, new_version

    def predict(self, x_features: NDArray[np.float64]) -> float:
        """Predicción puntual escalar para un único municipio (fila)."""
        bundle = self.bundle
        if bundle.family.startswith("lgbm"):
            y = bundle.model.predict(x_features.reshape(1, -1))
            return float(y[0])
        # GLM NegBin vía pyfunc → input DataFrame
        import pandas as pd
        df = pd.DataFrame([dict(zip(bundle.feature_names, x_features, strict=True))])
        y = bundle.model.predict(df)
        return float(np.asarray(y).flatten()[0])
