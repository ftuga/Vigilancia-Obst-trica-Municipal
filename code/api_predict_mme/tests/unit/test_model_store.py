"""Tests de ModelStore — descubrimiento + carga del champion.

Mockea ``MlflowClient`` y ``mlflow.lightgbm.load_model`` para evitar un
servidor real. Los helpers de ``mme.tracking.mlflow_ops``
(``load_champion_residuals``, ``load_champion_baseline``) también se
mockean porque reciben el mismo client.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from app.services.model_store import (
    ChampionNotFoundError,
    ModelStore,
)


def _fake_booster_predict(x: np.ndarray) -> np.ndarray:
    """Mock booster: devuelve suma de la fila como predicción."""
    return np.asarray(x).sum(axis=1).astype(float)


def _make_client(
    *,
    version: str = "1",
    run_id: str = "run-abc",
    family: str = "lgbm_poisson",
    spearman: float = 0.83,
    has_alias: bool = True,
) -> MagicMock:
    client = MagicMock()
    if has_alias:
        client.get_model_version_by_alias.return_value = SimpleNamespace(
            version=version, run_id=run_id,
        )
        client.get_run.return_value = SimpleNamespace(
            data=SimpleNamespace(
                tags={"family": family, "feature_spec_version": "v1",
                       "dataset_cycle": "2026-04-24"},
                metrics={"test_spearman_dpto": spearman, "test_precision_at_50": 0.24},
            ),
        )
    else:
        from mlflow.exceptions import MlflowException
        client.get_model_version_by_alias.side_effect = MlflowException("not found")
    return client


@pytest.fixture
def patched_store(monkeypatch: pytest.MonkeyPatch) -> tuple[ModelStore, MagicMock]:
    """ModelStore con deps mockeadas (sin contactar MLflow real)."""
    import app.services.model_store as module_under_test

    client = _make_client()

    fake_booster = MagicMock()
    fake_booster.predict = _fake_booster_predict

    monkeypatch.setattr(module_under_test, "MlflowClient", lambda: client)
    # Parcheamos el método `_load_model` directamente — evita gatillar la cadena
    # de imports de mlflow.lightgbm (que al resolverse conecta al tracking URI).
    monkeypatch.setattr(
        module_under_test.ModelStore,
        "_load_model",
        lambda self, run_id, family: fake_booster,  # noqa: ARG005
    )
    monkeypatch.setattr(
        module_under_test,
        "load_champion_residuals",
        lambda *args, **kwargs: np.array([0.1, -0.1, 0.2, -0.2, 0.0]),  # noqa: ARG005
    )
    monkeypatch.setattr(
        module_under_test,
        "load_champion_baseline",
        lambda *args, **kwargs: pd.DataFrame(  # noqa: ARG005
            {"feat_a": [1.0, 2.0], "feat_b": [0.1, 0.2]},
        ),
    )

    store = ModelStore(
        registered_model_name="mme_vulnerability_baseline",
        champion_alias="champion",
        tracking_uri="http://test:5000",
    )
    return store, client


def test_bundle_before_reload_raises() -> None:
    """Acceder a bundle antes de reload() → ChampionNotFoundError."""
    store = ModelStore(
        registered_model_name="foo",
        champion_alias="champion",
        tracking_uri="http://test:5000",
    )
    with pytest.raises(ChampionNotFoundError):
        _ = store.bundle


def test_reload_populates_bundle(
    patched_store: tuple[ModelStore, MagicMock],
) -> None:
    store, _client = patched_store
    prev, new = store.reload()
    assert prev is None
    assert new == "1"
    bundle = store.bundle
    assert bundle.family == "lgbm_poisson"
    assert bundle.residuals is not None
    assert bundle.residuals.size == 5
    assert bundle.baseline_df is not None
    assert bundle.feature_names == ["feat_a", "feat_b"]
    assert bundle.test_spearman_dpto == pytest.approx(0.83)


def test_reload_returns_prev_and_new(
    patched_store: tuple[ModelStore, MagicMock],
) -> None:
    store, client = patched_store
    store.reload()
    # Simulamos promoción de v2
    client.get_model_version_by_alias.return_value = SimpleNamespace(
        version="2", run_id="run-xyz",
    )
    client.get_run.return_value = SimpleNamespace(
        data=SimpleNamespace(
            tags={"family": "lgbm_poisson", "feature_spec_version": "v1",
                   "dataset_cycle": "2026-05-01"},
            metrics={"test_spearman_dpto": 0.85, "test_precision_at_50": 0.26},
        ),
    )
    prev, new = store.reload()
    assert prev == "1"
    assert new == "2"


def test_reload_no_alias_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_client(has_alias=False)
    monkeypatch.setattr(
        "app.services.model_store.MlflowClient", lambda: client,
    )
    store = ModelStore(
        registered_model_name="missing",
        champion_alias="champion",
        tracking_uri="http://test:5000",
    )
    with pytest.raises(ChampionNotFoundError):
        store.reload()


def test_predict_lgbm_vectorizes(
    patched_store: tuple[ModelStore, MagicMock],
) -> None:
    store, _ = patched_store
    store.reload()
    y = store.predict(np.array([1.0, 2.0]))  # suma = 3.0
    assert y == pytest.approx(3.0)


def test_unknown_family_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Familia fuera de {lgbm*, glm_negbin} → ChampionNotFoundError."""
    import app.services.model_store as module_under_test
    client = _make_client(family="xgb_poisson")
    monkeypatch.setattr(module_under_test, "MlflowClient", lambda: client)
    monkeypatch.setattr(
        module_under_test, "load_champion_residuals",
        lambda *args, **kw: None,  # noqa: ARG005
    )
    monkeypatch.setattr(
        module_under_test, "load_champion_baseline",
        lambda *args, **kw: None,  # noqa: ARG005
    )
    store = ModelStore(
        registered_model_name="foo", champion_alias="champion",
        tracking_uri="http://test:5000",
    )
    with pytest.raises(ChampionNotFoundError):
        store.reload()
