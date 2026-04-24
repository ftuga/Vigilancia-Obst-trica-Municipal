"""Detección de drift multivariable con Evidently + PSI/KS propio.

Dos salidas:
    - ``DriftReport`` (dict-like) con PSI/KS por feature — consumido por el
      DAG para publicar al Pushgateway.
    - HTML de Evidently con ``DataDriftPreset(method='psi')`` para inspección
      humana / tesis.

Por qué computamos PSI/KS aparte en vez de parsear Evidently:
    El layout del ``Snapshot.dict()`` cambia entre versiones minor de
    Evidently (0.4 → 0.6 → 0.7). Los cálculos propios nos protegen de ese
    drift de API y garantizan reproducibilidad en las métricas que alimentan
    el Pushgateway.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
from evidently import Report
from evidently.presets import DataDriftPreset
from scipy.stats import ks_2samp

if TYPE_CHECKING:
    from pathlib import Path

    import pandas as pd
    from numpy.typing import NDArray

logger = logging.getLogger(__name__)

PSI_STRONG_THRESHOLD = 0.25  # convención: ≥0.25 = strong drift
PSI_WEAK_THRESHOLD = 0.10  # 0.10-0.25 = weak drift
KS_ALPHA_DEFAULT = 0.01  # p-value threshold KS
_MIN_BINS_FOR_PSI = 3  # edges únicos mínimos (distribución no degenerada)


@dataclass(frozen=True)
class DriftReport:
    """Resultado de un drift check sobre las features del modelo."""

    drift_detected: bool
    psi_by_feature: dict[str, float]
    ks_stat_by_feature: dict[str, float]
    ks_pvalue_by_feature: dict[str, float]
    features_drifted: list[str]
    html_report_path: Path | None
    n_baseline: int
    n_current: int
    metadata: dict[str, str] = field(default_factory=dict)


def compute_psi(
    baseline: NDArray[np.float64],
    current: NDArray[np.float64],
    *,
    bins: int = 10,
) -> float:
    """Calcula Population Stability Index con quantile-binning del baseline.

    Laplace smoothing (``+1`` por bin) evita ``log(0)`` cuando una
    distribución tiene un bucket vacío. Edges se extienden a ``±inf`` para
    absorber valores del current fuera del rango del baseline.

    Args:
        baseline: Serie de referencia (el que el champion vio).
        current: Serie nueva a evaluar.
        bins: Número de quantile-bins (default 10).

    Returns:
        PSI escalar ≥ 0. Convenciones:
            - PSI < 0.10: estable
            - 0.10 ≤ PSI < 0.25: weak drift
            - PSI ≥ 0.25: strong drift
    """
    baseline = np.asarray(baseline, dtype=np.float64)
    current = np.asarray(current, dtype=np.float64)
    baseline = baseline[np.isfinite(baseline)]
    current = current[np.isfinite(current)]
    if baseline.size == 0 or current.size == 0:
        return 0.0

    edges = np.quantile(baseline, np.linspace(0, 1, bins + 1))
    edges = np.unique(edges)
    if edges.size < _MIN_BINS_FOR_PSI:  # distribución degenerada (casi-constante)
        return 0.0
    edges[0] = -np.inf
    edges[-1] = np.inf

    base_counts = np.histogram(baseline, bins=edges)[0].astype(np.float64)
    curr_counts = np.histogram(current, bins=edges)[0].astype(np.float64)

    n_bins = float(base_counts.size)
    base_p = (base_counts + 1.0) / (base_counts.sum() + n_bins)
    curr_p = (curr_counts + 1.0) / (curr_counts.sum() + n_bins)
    return float(np.sum((curr_p - base_p) * np.log(curr_p / base_p)))


def _compute_per_feature_metrics(
    baseline_df: pd.DataFrame,
    current_df: pd.DataFrame,
    feature_cols: list[str],
) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    """PSI + KS statistic + KS p-value por feature."""
    psi: dict[str, float] = {}
    ks_stat: dict[str, float] = {}
    ks_p: dict[str, float] = {}
    for col in feature_cols:
        if col not in baseline_df.columns or col not in current_df.columns:
            logger.warning("feature %s no presente en ambos DataFrames — skip", col)
            continue
        base = baseline_df[col].to_numpy(dtype=np.float64)
        curr = current_df[col].to_numpy(dtype=np.float64)
        psi[col] = compute_psi(base, curr)
        ks = ks_2samp(base, curr)
        ks_stat[col] = float(ks.statistic)
        ks_p[col] = float(ks.pvalue)
    return psi, ks_stat, ks_p


def _try_save_evidently_html(
    baseline_df: pd.DataFrame,
    current_df: pd.DataFrame,
    feature_cols: list[str],
    html_path: Path,
) -> Path | None:
    """Genera el HTML de Evidently. Si falla, retorna None — no bloquea."""
    try:
        report = Report([DataDriftPreset(method="psi")])
        snapshot = report.run(
            reference_data=baseline_df[feature_cols],
            current_data=current_df[feature_cols],
        )
        html_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot.save_html(str(html_path))
    except Exception:  # noqa: BLE001 — HTML es bonus, no crítico
        logger.exception("evidently HTML generation falló — continuando sin HTML")
        return None
    return html_path


def run_drift_check(
    current_df: pd.DataFrame,
    baseline_df: pd.DataFrame,
    feature_cols: list[str],
    *,
    out_dir: Path | None = None,
    html_name: str | None = None,
    psi_threshold: float = PSI_STRONG_THRESHOLD,
) -> DriftReport:
    """Chequea drift feature-a-feature entre baseline y current.

    Args:
        current_df: Panel actual (post-PCA, mismas cols que baseline).
        baseline_df: Panel de referencia del champion vigente.
        feature_cols: Columnas sobre las que calcular drift.
        out_dir: Si se pasa, escribe HTML de Evidently. None = skip HTML.
        html_name: Nombre del HTML. Default ``drift_<N>.html``.
        psi_threshold: PSI ≥ threshold marca la feature como drifted.
            Default 0.25 (strong drift).

    Returns:
        ``DriftReport`` con flags y métricas por feature.
    """
    psi, ks_stat, ks_p = _compute_per_feature_metrics(
        baseline_df, current_df, feature_cols,
    )
    features_drifted = sorted(f for f, v in psi.items() if v >= psi_threshold)
    drift_detected = len(features_drifted) > 0

    html_path: Path | None = None
    if out_dir is not None:
        name = html_name or f"drift_{len(feature_cols)}feat.html"
        html_path = _try_save_evidently_html(
            baseline_df, current_df, feature_cols, out_dir / name,
        )

    return DriftReport(
        drift_detected=drift_detected,
        psi_by_feature=psi,
        ks_stat_by_feature=ks_stat,
        ks_pvalue_by_feature=ks_p,
        features_drifted=features_drifted,
        html_report_path=html_path,
        n_baseline=len(baseline_df),
        n_current=len(current_df),
        metadata={
            "psi_threshold": f"{psi_threshold}",
            "ks_alpha": f"{KS_ALPHA_DEFAULT}",
        },
    )
