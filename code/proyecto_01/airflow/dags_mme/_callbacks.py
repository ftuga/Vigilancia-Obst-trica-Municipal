"""Callbacks compartidos por los DAGs MME.

Diseño: un único `on_failure_callback` que empuja el error al log estructurado,
opcionalmente a Slack/Teams (via env `MME_ALERTS_WEBHOOK`) y registra un
heartbeat negativo en Prometheus Pushgateway.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def on_failure_callback(context: dict[str, Any]) -> None:
    ti = context.get("task_instance")
    dag_id = context.get("dag").dag_id if context.get("dag") else "?"
    task_id = ti.task_id if ti else "?"
    run_id = context.get("run_id", "?")
    exc = context.get("exception")

    logger.error(
        "MME DAG failure | dag=%s task=%s run=%s | exc=%s",
        dag_id, task_id, run_id, exc,
    )

    webhook = os.environ.get("MME_ALERTS_WEBHOOK", "").strip()
    if webhook:
        try:
            import requests
            requests.post(webhook, json={
                "text": f":rotating_light: MME DAG {dag_id} | task `{task_id}` | run `{run_id}`\n```{exc}```"
            }, timeout=5)
        except Exception as e:  # no bloquear el failure path
            logger.warning("MME alerts webhook no respondió: %s", e)

    # Pushgateway opcional (si PUSHGATEWAY_URL está disponible)
    pg_url = os.environ.get("PUSHGATEWAY_URL", "http://pushgateway:9091").strip()
    if pg_url:
        try:
            from prometheus_client import CollectorRegistry, Gauge, push_to_gateway
            reg = CollectorRegistry()
            g = Gauge("mme_dag_failure_ts", "timestamp del último failure por dag/task",
                     ["dag_id", "task_id"], registry=reg)
            import time
            g.labels(dag_id=dag_id, task_id=task_id).set(time.time())
            push_to_gateway(pg_url, job=f"mme_dag_{dag_id}", registry=reg)
        except Exception as e:
            logger.warning("Pushgateway no disponible: %s", e)
