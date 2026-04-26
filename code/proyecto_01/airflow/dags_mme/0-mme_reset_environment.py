"""
DAG 0-mme_reset_environment — limpieza idempotente del entorno MME.

Manual-only (schedule=None). Útil para probar boot from scratch:
  1. Vacía /opt/airflow/data/mme/* (PVC mme-data).
  2. Vacía buckets MinIO mme-bronze, mme-silver, mme-gold (sin destruir bucket).
  3. Elimina registered model 'mme_vulnerability_baseline' del MLflow Registry
     (con todas sus versions y aliases).

Todas las operaciones son idempotentes — no fallan si no hay nada que borrar.

Gate de seguridad: requiere Airflow Variable confirm_reset=YES.
Setear con `airflow variables set confirm_reset YES` o desde la UI antes de trigger.
"""
from __future__ import annotations

import os
import shutil
from datetime import timedelta
from pathlib import Path
from typing import Any

import pendulum
from airflow.decorators import dag, task

DATA_MME = "/opt/airflow/data/mme"


@dag(
    dag_id="0-mme_reset_environment",
    description="Reset destructivo idempotente del entorno MME (PVC + MinIO + MLflow Registry)",
    schedule=None,
    start_date=pendulum.datetime(2026, 4, 25, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=10),
    tags=["mme", "ops", "destructive"],
    default_args={
        "owner": "mme",
        "depends_on_past": False,
        "retries": 0,
    },
)
def mme_reset_environment():

    @task.short_circuit(task_id="confirm_gate")
    def confirm_gate() -> bool:
        """Gate: solo procede si Airflow Variable confirm_reset=YES."""
        from airflow.models import Variable
        val = Variable.get("confirm_reset", default_var="NO").strip().upper()
        proceed = val == "YES"
        print(f"[reset-gate] confirm_reset={val} → proceed={proceed}")
        if not proceed:
            print(
                "[reset-gate] Para ejecutar: "
                "airflow variables set confirm_reset YES (re-disparar después).",
            )
        return proceed

    @task(task_id="reset_pvc")
    def reset_pvc() -> dict[str, Any]:
        """Vacía cada subcarpeta del PVC mme-data (bronze, silver, gold, reports, staging)."""
        root = Path(DATA_MME)
        if not root.exists():
            print(f"[reset-pvc] {root} no existe — nada que borrar")
            return {"status": "noop", "removed_dirs": []}

        targets = ["bronze", "silver", "gold", "reports", "staging"]
        removed = []
        for sub in targets:
            p = root / sub
            if not p.exists():
                continue
            try:
                shutil.rmtree(p)
                removed.append(sub)
                print(f"[reset-pvc] borrado {p}")
            except Exception as e:  # noqa: BLE001
                print(f"[reset-pvc] error borrando {p}: {e!r} — continuando")
        return {"status": "ok", "removed_dirs": removed}

    @task(task_id="reset_minio")
    def reset_minio() -> dict[str, Any]:
        """Vacía contenido de buckets mme-bronze, mme-silver, mme-gold (no destruye bucket)."""
        try:
            import boto3
            from botocore.exceptions import ClientError
        except ImportError as e:
            print(f"[reset-minio] boto3 no disponible: {e!r} — skipping")
            return {"status": "skipped", "reason": "boto3 missing"}

        endpoint = os.environ.get("MLFLOW_S3_ENDPOINT_URL")
        ak = os.environ.get("AWS_ACCESS_KEY_ID")
        sk = os.environ.get("AWS_SECRET_ACCESS_KEY")
        if not endpoint or not ak or not sk:
            print("[reset-minio] credenciales S3 no presentes en env — skipping")
            return {"status": "skipped", "reason": "no creds"}

        s3 = boto3.client("s3", endpoint_url=endpoint,
                          aws_access_key_id=ak, aws_secret_access_key=sk)

        deleted_total = 0
        per_bucket: dict[str, int] = {}
        for bucket in ("mme-bronze", "mme-silver", "mme-gold"):
            try:
                paginator = s3.get_paginator("list_objects_v2")
                keys: list[dict[str, str]] = []
                for page in paginator.paginate(Bucket=bucket):
                    for obj in page.get("Contents", []):
                        keys.append({"Key": obj["Key"]})
                if not keys:
                    per_bucket[bucket] = 0
                    print(f"[reset-minio] {bucket}: vacío")
                    continue
                # delete_objects acepta hasta 1000 a la vez
                count = 0
                for i in range(0, len(keys), 1000):
                    batch = keys[i:i + 1000]
                    s3.delete_objects(Bucket=bucket, Delete={"Objects": batch})
                    count += len(batch)
                per_bucket[bucket] = count
                deleted_total += count
                print(f"[reset-minio] {bucket}: borrados {count} objetos")
            except ClientError as e:
                code = e.response.get("Error", {}).get("Code", "")
                if code in ("NoSuchBucket", "404"):
                    per_bucket[bucket] = 0
                    print(f"[reset-minio] {bucket}: no existe — skip")
                else:
                    print(f"[reset-minio] {bucket}: error {e!r} — continuando")
            except Exception as e:  # noqa: BLE001
                print(f"[reset-minio] {bucket}: error {e!r} — continuando")
        return {"status": "ok", "deleted_total": deleted_total, "per_bucket": per_bucket}

    @task(task_id="reset_mlflow_registry")
    def reset_mlflow_registry() -> dict[str, Any]:
        """Elimina registered model + todas sus versions y aliases.

        Modelo: ``mme_vulnerability_baseline`` (definido en .env como
        ``MLFLOW_REGISTRY_MODEL_NAME``).
        """
        try:
            import mlflow
            from mlflow.client import MlflowClient
            from mlflow.exceptions import MlflowException
        except ImportError as e:
            print(f"[reset-mlflow] mlflow no disponible: {e!r} — skipping")
            return {"status": "skipped", "reason": "mlflow missing"}

        tracking_uri = os.environ.get("MLFLOW_TRACKING_URI")
        if not tracking_uri:
            print("[reset-mlflow] MLFLOW_TRACKING_URI no seteado — skipping")
            return {"status": "skipped", "reason": "no tracking uri"}
        mlflow.set_tracking_uri(tracking_uri)

        model_name = os.environ.get("MLFLOW_REGISTRY_MODEL_NAME",
                                    "mme_vulnerability_baseline")
        client = MlflowClient()

        try:
            model = client.get_registered_model(model_name)
        except MlflowException as e:
            if "RESOURCE_DOES_NOT_EXIST" in str(e) or "not found" in str(e).lower():
                print(f"[reset-mlflow] modelo '{model_name}' no existe — noop")
                return {"status": "noop", "model": model_name}
            print(f"[reset-mlflow] error obteniendo modelo: {e!r} — skipping")
            return {"status": "error", "error": str(e)}

        # Borrar aliases primero (no hay API list-aliases en client viejo,
        # iteramos sobre versions y leemos alias_list).
        deleted_aliases = []
        deleted_versions = []
        try:
            versions = client.search_model_versions(f"name='{model_name}'")
            for v in versions:
                # alias_list / aliases según versión de MLflow.
                aliases = getattr(v, "aliases", None) or []
                for alias in aliases:
                    try:
                        client.delete_registered_model_alias(model_name, alias)
                        deleted_aliases.append(alias)
                        print(f"[reset-mlflow] alias '{alias}' borrado")
                    except Exception as e:  # noqa: BLE001
                        print(f"[reset-mlflow] error borrando alias {alias}: {e!r}")
                try:
                    client.delete_model_version(model_name, v.version)
                    deleted_versions.append(v.version)
                    print(f"[reset-mlflow] version {v.version} borrada")
                except Exception as e:  # noqa: BLE001
                    print(f"[reset-mlflow] error borrando version {v.version}: {e!r}")
        except Exception as e:  # noqa: BLE001
            print(f"[reset-mlflow] error listando versions: {e!r} — continuando")

        try:
            client.delete_registered_model(model_name)
            print(f"[reset-mlflow] registered model '{model_name}' borrado")
        except Exception as e:  # noqa: BLE001
            print(f"[reset-mlflow] error borrando modelo: {e!r}")

        return {
            "status": "ok",
            "model": model_name,
            "deleted_aliases": deleted_aliases,
            "deleted_versions": deleted_versions,
        }

    @task(task_id="summary")
    def summary(pvc: dict, minio: dict, mlflow_reg: dict) -> dict[str, Any]:
        """Reporte final."""
        out = {"pvc": pvc, "minio": minio, "mlflow": mlflow_reg}
        print(f"[reset-summary] {out}")
        return out

    # Wiring
    gate = confirm_gate()
    pvc = reset_pvc()
    minio = reset_minio()
    mlflow_reg = reset_mlflow_registry()
    final = summary(pvc, minio, mlflow_reg)

    gate >> [pvc, minio, mlflow_reg] >> final


mme_reset_environment()
