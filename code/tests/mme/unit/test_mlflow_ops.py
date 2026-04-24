"""Tests de promoción gated — ``src/mme/tracking/mlflow_ops.py``.

Cubre el gate combinado (``new >= prev*tolerance OR new >= absolute_floor``)
y el wiring con MLflow Registry (aliases). Usa mocks de MlflowClient —
no requiere server MLflow ni artifacts reales.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from mlflow.exceptions import MlflowException

from mme.tracking.mlflow_ops import PromotionDecision, promote_champion


def _make_run(run_id: str, family: str, score: float) -> SimpleNamespace:
    """Build a fake MLflow run with the minimum shape used by promote_champion."""
    return SimpleNamespace(
        info=SimpleNamespace(run_id=run_id, status="FINISHED"),
        data=SimpleNamespace(
            tags={"family": family},
            metrics={"test_spearman_dpto": score},
        ),
    )


def _fake_client(
    *,
    champion_run: tuple[str, str, float] | None = None,
    candidates: list[tuple[str, str, float]] | None = None,
    experiment_exists: bool = True,
) -> MagicMock:
    """Builds a MagicMock MlflowClient with realistic behavior.

    Args:
        champion_run: (version, run_id, score) del alias ``@champion``, o
            ``None`` si no existe.
        candidates: runs del experimento, en el orden que deben salir al
            rankear (top primero). Cada uno ``(run_id, family, score)``.
        experiment_exists: si el experimento se encuentra por nombre.
    """
    client = MagicMock()

    if champion_run is None:
        client.get_model_version_by_alias.side_effect = MlflowException(
            "alias not found",
        )
    else:
        version, run_id, _score = champion_run
        client.get_model_version_by_alias.return_value = SimpleNamespace(
            version=version, run_id=run_id,
        )
        client.get_run.return_value = _make_run(
            run_id, "lgbm_poisson", champion_run[2],
        )

    if experiment_exists:
        client.get_experiment_by_name.return_value = SimpleNamespace(
            experiment_id="1",
        )
    else:
        client.get_experiment_by_name.return_value = None

    if candidates:
        client.search_runs.return_value = [
            _make_run(rid, fam, score) for rid, fam, score in candidates
        ]
    else:
        client.search_runs.return_value = []

    # create_registered_model: succeed first time, raise on duplicate
    client.create_registered_model.return_value = None
    # create_model_version returns something with .version
    client.create_model_version.return_value = SimpleNamespace(version="7")
    return client


def _call(client: MagicMock, **overrides: Any) -> PromotionDecision:
    kwargs: dict[str, Any] = {
        "experiment_name": "mme_vulnerability_v1",
        "registered_model_name": "mme_vulnerability_baseline",
        "client": client,
    }
    kwargs.update(overrides)
    return promote_champion(**kwargs)


def test_first_time_promotion_passes_floor() -> None:
    """Sin champion previo y score >= floor → promueve."""
    client = _fake_client(
        champion_run=None,
        candidates=[("run-new", "lgbm_poisson", 0.83)],
    )
    decision = _call(client)

    assert decision.promoted is True
    assert decision.new_run_id == "run-new"
    assert decision.new_score == pytest.approx(0.83)
    assert decision.prev_version is None
    assert decision.new_version == "7"
    assert "first_champion" in decision.reason
    client.create_model_version.assert_called_once()
    client.set_registered_model_alias.assert_called_once_with(
        "mme_vulnerability_baseline", "champion", "7",
    )


def test_first_time_below_floor_rejected() -> None:
    """Sin champion previo y score < floor → NO promueve."""
    client = _fake_client(
        champion_run=None,
        candidates=[("run-weak", "lgbm_poisson", 0.40)],
    )
    decision = _call(client, absolute_floor=0.65)

    assert decision.promoted is False
    assert decision.new_run_id == "run-weak"
    assert decision.new_version is None
    assert "first_champion_rejected" in decision.reason
    client.create_model_version.assert_not_called()
    client.set_registered_model_alias.assert_not_called()


def test_gate_relative_pass_replaces_champion() -> None:
    """Champion previo 0.80, nuevo 0.78 → 0.78 >= 0.80*0.95=0.76 → promueve."""
    client = _fake_client(
        champion_run=("3", "run-prev", 0.80),
        candidates=[("run-new", "lgbm_poisson", 0.78)],
    )
    decision = _call(client, tolerance=0.95, absolute_floor=0.65)

    assert decision.promoted is True
    assert decision.prev_version == "3"
    assert decision.prev_score == pytest.approx(0.80)
    assert "gate_pass" in decision.reason
    client.set_registered_model_alias.assert_called_once()


def test_gate_absolute_floor_rescues_champion() -> None:
    """Champion previo 0.90 (outlier). Nuevo 0.70 < 0.90*0.95=0.855 pero >= floor 0.65 → promueve."""
    client = _fake_client(
        champion_run=("3", "run-prev", 0.90),
        candidates=[("run-new", "lgbm_poisson", 0.70)],
    )
    decision = _call(client, tolerance=0.95, absolute_floor=0.65)

    assert decision.promoted is True
    assert decision.new_score == pytest.approx(0.70)
    assert "gate_pass" in decision.reason


def test_gate_fails_new_too_low() -> None:
    """Nuevo < prev*tol AND nuevo < floor → NO promueve."""
    client = _fake_client(
        champion_run=("3", "run-prev", 0.80),
        candidates=[("run-weak", "lgbm_poisson", 0.50)],
    )
    decision = _call(client, tolerance=0.95, absolute_floor=0.65)

    assert decision.promoted is False
    assert "gate_fail" in decision.reason
    assert decision.new_version is None
    client.create_model_version.assert_not_called()


def test_dry_run_does_not_mutate_registry() -> None:
    """dry_run=True evalúa pero no registra ni mueve alias."""
    client = _fake_client(
        champion_run=None,
        candidates=[("run-new", "lgbm_poisson", 0.83)],
    )
    decision = _call(client, dry_run=True)

    assert decision.promoted is False
    assert "dry_run" in decision.reason
    client.create_model_version.assert_not_called()
    client.set_registered_model_alias.assert_not_called()


def test_no_candidates_returns_early() -> None:
    """Experimento vacío → no promueve, reason=no_candidates_found."""
    client = _fake_client(
        champion_run=("3", "run-prev", 0.80),
        candidates=[],
    )
    decision = _call(client)

    assert decision.promoted is False
    assert decision.reason == "no_candidates_found"
    assert decision.prev_version == "3"


def test_filters_by_allowed_families() -> None:
    """Runs de familias fuera del allowlist se ignoran."""
    client = _fake_client(
        champion_run=None,
        candidates=[
            ("run-xgb", "xgb_poisson", 0.95),
            ("run-lgbm", "lgbm_poisson", 0.70),
        ],
    )
    decision = _call(
        client,
        allowed_families={"lgbm_poisson", "glm_negbin"},
        absolute_floor=0.65,
    )

    # xgb_poisson se descarta → lgbm_poisson es el único candidato
    assert decision.promoted is True
    assert decision.new_run_id == "run-lgbm"
    assert decision.new_score == pytest.approx(0.70)


def test_experiment_not_found_returns_no_candidates() -> None:
    """Si el experimento no existe → no_candidates_found."""
    client = _fake_client(champion_run=None, experiment_exists=False)
    decision = _call(client)

    assert decision.promoted is False
    assert decision.reason == "no_candidates_found"
