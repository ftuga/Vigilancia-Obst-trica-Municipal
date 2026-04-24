"""Publica métricas de entrenamiento y drift al Pushgateway de Prometheus.

Namespace: `mme_*`. Labels comunes: family, dataset_cycle, regime.

Convención con Prometheus rules (proyecto_01/prometheus/rules/mme.rules.yml):
- mme_model_{train|val|test}_{spearman_dpto,precision_at_50,mae_razon,r2_log_counts}
- mme_feature_psi{feature="..."}, mme_feature_ks_stat{feature="..."}
- mme_drift_detected (gauge 0/1)
"""
from __future__ import annotations

import logging
import os
from typing import Any

from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

logger = logging.getLogger(__name__)

_DEFAULT_GATEWAY = os.environ.get("PUSHGATEWAY_URL", "pushgateway:9091")
_JOB = "mme_training"

_METRIC_FAMILIES = {
    "spearman_dpto": "mme_model_{split}_spearman_dpto",
    "precision_at_50": "mme_model_{split}_precision_at_50",
    "mae_razon": "mme_model_{split}_mae_razon",
    "r2_log_counts": "mme_model_{split}_r2_log_counts",
}


def push_model_metrics(
    report: dict[str, Any],
    *,
    gateway: str = _DEFAULT_GATEWAY,
    grouping: dict[str, str] | None = None,
) -> None:
    """Empuja métricas del reporte train_c3_*.json al pushgateway.

    `report` debe tener forma:
        {
          "results": [
            {"family": "...", "train": {...}, "val": {...}, "test": {...}}, ...
          ],
          "dataset_cycle": "YYYY-MM-DD",
          "regime": "..."
        }
    """
    registry = CollectorRegistry()
    gauges: dict[tuple[str, str], Gauge] = {}

    def _get(metric_key: str, split: str) -> Gauge:
        name = _METRIC_FAMILIES[metric_key].format(split=split)
        if (name,) not in gauges:
            gauges[(name,)] = Gauge(
                name,
                f"MME {split} {metric_key}",
                labelnames=["family", "dataset_cycle", "regime"],
                registry=registry,
            )
        return gauges[(name,)]

    dataset_cycle = str(report.get("dataset_cycle", "unknown"))
    regime = str(report.get("regime", "unknown"))

    for r in report.get("results", []):
        family = str(r.get("family", "unknown"))
        for split in ("train", "val", "test"):
            block = r.get(split) or {}
            for metric_key in _METRIC_FAMILIES:
                v = block.get(metric_key)
                if v is None:
                    continue
                _get(metric_key, split).labels(
                    family=family, dataset_cycle=dataset_cycle, regime=regime
                ).set(float(v))

    push_to_gateway(
        gateway,
        job=_JOB,
        registry=registry,
        grouping_key=grouping or {"dataset_cycle": dataset_cycle},
    )
    logger.info("Pushed %d metric families to %s", len(gauges), gateway)


def push_drift_status(
    *,
    drift_detected: bool,
    psi_by_feature: dict[str, float] | None = None,
    ks_by_feature: dict[str, float] | None = None,
    gateway: str = _DEFAULT_GATEWAY,
    grouping: dict[str, str] | None = None,
) -> None:
    """Publica el estado de drift detectado por el check semanal."""
    registry = CollectorRegistry()

    g_drift = Gauge(
        "mme_drift_detected", "1 si el check_drift marcó drift, 0 si estable", registry=registry
    )
    g_drift.set(1.0 if drift_detected else 0.0)

    if psi_by_feature:
        g_psi = Gauge(
            "mme_feature_psi",
            "PSI por feature vs baseline del champion",
            labelnames=["feature"],
            registry=registry,
        )
        for feat, val in psi_by_feature.items():
            g_psi.labels(feature=feat).set(float(val))

    if ks_by_feature:
        g_ks = Gauge(
            "mme_feature_ks_stat",
            "KS statistic por feature vs baseline",
            labelnames=["feature"],
            registry=registry,
        )
        for feat, val in ks_by_feature.items():
            g_ks.labels(feature=feat).set(float(val))

    push_to_gateway(
        gateway,
        job="mme_drift",
        registry=registry,
        grouping_key=grouping or {},
    )
    logger.info("Pushed drift status=%s to %s", drift_detected, gateway)
