"""Tests de detección de drift — ``src/mme/drift/evidently_runner.py``."""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from mme.drift.evidently_runner import (
    PSI_STRONG_THRESHOLD,
    compute_psi,
    run_drift_check,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_psi_identical_distributions_near_zero() -> None:
    """Baseline == current → PSI cerca de 0."""
    rng = np.random.default_rng(42)
    sample = rng.normal(0.0, 1.0, size=500)
    psi = compute_psi(sample, sample.copy())
    assert psi == 0.0 or psi < 0.01


def test_psi_mild_shift_below_strong_threshold() -> None:
    """Shift moderado (~0.2σ) → PSI debajo del strong threshold 0.25."""
    rng = np.random.default_rng(42)
    baseline = rng.normal(0.0, 1.0, size=2000)
    current = rng.normal(0.2, 1.0, size=2000)
    psi = compute_psi(baseline, current)
    assert 0.0 < psi < PSI_STRONG_THRESHOLD


def test_psi_strong_shift_crosses_threshold() -> None:
    """Shift fuerte (1σ) → PSI >> 0.25."""
    rng = np.random.default_rng(42)
    baseline = rng.normal(0.0, 1.0, size=2000)
    current = rng.normal(1.5, 1.0, size=2000)
    psi = compute_psi(baseline, current)
    assert psi >= PSI_STRONG_THRESHOLD


def test_psi_degenerate_constant_baseline() -> None:
    """Baseline casi-constante → PSI=0 (sin binning posible)."""
    baseline = np.full(100, 3.14)
    current = np.full(100, 3.14)
    assert compute_psi(baseline, current) == 0.0


def test_psi_empty_returns_zero() -> None:
    """Arrays vacíos → PSI=0 sin crashear."""
    assert compute_psi(np.array([]), np.array([])) == 0.0


def test_psi_handles_nan_and_inf() -> None:
    """NaN/inf se filtran antes de computar."""
    baseline = np.array([1.0, 2.0, 3.0, np.nan, np.inf, -np.inf])
    current = np.array([1.0, 2.0, 3.0])
    psi = compute_psi(baseline, current)
    assert np.isfinite(psi)


def test_run_drift_no_drift_identical_panels(tmp_path: Path) -> None:
    """Baseline == current → drift_detected=False, features_drifted=[]."""
    rng = np.random.default_rng(7)
    df = pd.DataFrame(
        {"a": rng.normal(0, 1, 500), "b": rng.normal(5, 2, 500)},
    )
    report = run_drift_check(
        current_df=df,
        baseline_df=df.copy(),
        feature_cols=["a", "b"],
        out_dir=tmp_path,
    )
    assert report.drift_detected is False
    assert report.features_drifted == []
    assert set(report.psi_by_feature.keys()) == {"a", "b"}
    assert report.n_baseline == 500
    assert report.n_current == 500


def test_run_drift_detects_strong_shift(tmp_path: Path) -> None:
    """Feature b fuertemente shifteada → drift_detected=True con b drifted."""
    rng = np.random.default_rng(11)
    baseline = pd.DataFrame(
        {"a": rng.normal(0, 1, 1000), "b": rng.normal(0, 1, 1000)},
    )
    current = pd.DataFrame(
        {"a": rng.normal(0, 1, 1000), "b": rng.normal(2.0, 1.0, 1000)},
    )
    report = run_drift_check(
        current_df=current,
        baseline_df=baseline,
        feature_cols=["a", "b"],
        out_dir=tmp_path,
    )
    assert report.drift_detected is True
    assert "b" in report.features_drifted
    assert report.psi_by_feature["b"] >= PSI_STRONG_THRESHOLD


def test_run_drift_missing_feature_is_skipped(tmp_path: Path) -> None:
    """Feature en la lista pero no en los DataFrames → skip con warning."""
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0, 5.0]})
    report = run_drift_check(
        current_df=df,
        baseline_df=df.copy(),
        feature_cols=["a", "missing_feature"],
        out_dir=None,
    )
    assert "missing_feature" not in report.psi_by_feature
    assert "a" in report.psi_by_feature


def test_run_drift_writes_html_when_out_dir_given(tmp_path: Path) -> None:
    """Con out_dir, el HTML de Evidently se genera."""
    rng = np.random.default_rng(13)
    df = pd.DataFrame({"a": rng.normal(0, 1, 200)})
    report = run_drift_check(
        current_df=df,
        baseline_df=df.copy(),
        feature_cols=["a"],
        out_dir=tmp_path,
        html_name="test.html",
    )
    assert report.html_report_path is not None
    assert report.html_report_path.exists()
    assert report.html_report_path.stat().st_size > 1000


def test_run_drift_no_html_when_out_dir_none() -> None:
    """Sin out_dir, html_report_path=None sin error."""
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0, 5.0]})
    report = run_drift_check(
        current_df=df,
        baseline_df=df.copy(),
        feature_cols=["a"],
        out_dir=None,
    )
    assert report.html_report_path is None
