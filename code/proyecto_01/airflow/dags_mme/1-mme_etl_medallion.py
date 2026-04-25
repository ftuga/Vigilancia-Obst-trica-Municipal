"""
DAG 1-mme_etl_medallion — ingesta medallón MME Colombia.

Wrapping Airflow de los scripts de ingesta `scripts/mme/*.py`. Ejecuta en paralelo
las 7 fuentes (ninguna depende de otra) y converge en build_silver → build_gold_panel
→ validate_gold_invariants.

Arquitectura:
  - `/opt/repo` es RO (repo montado). Los scripts se ejecutan vía subprocess con
    PYTHONPATH apuntando al repo. Esto evita problemas de imports y mantiene los
    scripts reusables standalone + dentro de Airflow.
  - `/opt/airflow/data/mme` es RW (el staging real del medallón). Los scripts
    escriben ahí; el gold_panel.parquet consumido por DAG 2 (training) vive acá.
  - DuckDB resuelve read/write sin problemas de lockfile (1 proceso por task).

Schedule: diario 03:00 UTC. Timeout 2h. Retries 1 con delay 10min.

Fail-fast: si `validate_gold_invariants` falla, el DAG se marca FAIL y no se
propaga al DAG 2 de training (dependencia por ExternalTaskSensor en DAG 2).
"""
from __future__ import annotations

import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pendulum
from airflow.decorators import dag, task

try:
    # Callback compartido (opcional — si falla el import, DAG sigue sin callback)
    from _callbacks import on_failure_callback
except ImportError:  # pragma: no cover
    on_failure_callback = None


REPO_ROOT = "/opt/repo"
DATA_MME = "/opt/airflow/data/mme"

# Override que los scripts leen para decidir dónde escriben. Por default
# usan REPO_ROOT/data/mme pero /opt/repo está RO, así que redirigimos a /opt/airflow/data/mme.
SCRIPT_ENV = {
    **os.environ,
    "MME_DATA_ROOT": DATA_MME,
    "MME_REPORTS_ROOT": f"{DATA_MME}/reports",
    "PYTHONPATH": REPO_ROOT,
}


def _run_script(script_path: str, extra_args: list[str] | None = None) -> str:
    """Ejecuta un script bajo /opt/repo/scripts/mme con stderr capturado.

    Los scripts MME calculan REPO_ROOT vía ``Path(__file__).parents[2]`` y escriben
    en ``REPO_ROOT/data/mme/...``. Como /opt/repo está montado RO, hacemos un
    bind-mount overlay: copiamos el script a un tempdir con REPO_ROOT falso que
    apunta al mount RW `/opt/airflow/data/mme`. En práctica levantamos el REPO
    del script para que ``data/mme`` apunte a ``/opt/airflow/data/mme``.

    Patrón más simple y robusto: usar env var `MME_REPO_OVERRIDE` que los scripts
    mme consulten si existe. Si no la consultan, cae a un sym-link.
    """
    cmd = ["python", f"{REPO_ROOT}/scripts/mme/{script_path}"]
    if extra_args:
        cmd.extend(extra_args)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=SCRIPT_ENV,
        cwd=DATA_MME,  # los scripts escriben relativo al cwd si detectan override
        timeout=1800,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"{script_path} failed: rc={result.returncode}\n"
            f"stdout:\n{result.stdout[-2000:]}\n"
            f"stderr:\n{result.stderr[-2000:]}"
        )
    return result.stdout


default_args = {
    "owner": "mme",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
    "on_failure_callback": on_failure_callback,
}


@dag(
    dag_id="1-mme_etl_medallion",
    description="Ingesta medallón MME (bronze → silver → gold)",
    schedule="0 3 * * *",  # diario 03:00 UTC
    start_date=pendulum.datetime(2026, 4, 23, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(hours=2),
    default_args=default_args,
    tags=["mme", "etl", "medallion"],
)
def mme_etl_medallion():
    """Pipeline ETL MME en 3 fases: ingesta (7 paralelas) → silver → gold."""

    # ─── Ingesta bronze (paralelo) ─────────────────────────────────
    @task(task_id="fetch_sivigila_mme")
    def fetch_sivigila_mme():
        return _run_script("ingest_sivigila_bronze.py")

    @task(task_id="fetch_sivigila_mm")
    def fetch_sivigila_mm():
        return _run_script("ingest_sivigila_mm_bronze.py")

    @task(task_id="fetch_divipola")
    def fetch_divipola():
        return _run_script("ingest_divipola_bronze.py")

    @task(task_id="ingest_nbi")
    def ingest_nbi():
        return _run_script("ingest_censo2018_bronze.py")

    @task(task_id="ingest_poblacion")
    def ingest_poblacion():
        return _run_script("ingest_censo2018_poblacion_bronze.py")

    @task(task_id="ingest_bdua")
    def ingest_bdua():
        return _run_script("ingest_bdua_bronze.py")

    @task(task_id="ingest_reps")
    def ingest_reps():
        return _run_script("ingest_reps_bronze.py")

    @task(task_id="eevv_staging_check")
    def eevv_staging_check() -> dict[str, Any]:
        """Ingesta condicional: solo corre si hay CSVs en staging.

        Los CSV EEVV requieren descarga manual de DANE microdatos.
        Documentación: docs/mme/dane-eevv-procedure.md.
        """
        staging = Path(DATA_MME) / "staging" / "dane_eevv"
        csvs = list(staging.glob("*.csv")) if staging.exists() else []
        if not csvs:
            return {"status": "no_staging_data", "files": 0}
        _run_script("ingest_dane_eevv_bronze.py")
        return {"status": "ingested", "files": len(csvs)}

    # ─── Silver (reglas 549 + reconciliación DIVIPOLA) ──────────────
    @task(task_id="build_silver")
    def build_silver():
        return _run_script("build_silver.py")

    # ─── Gold panel (join de 5-6 fuentes) ───────────────────────────
    @task(task_id="build_gold_panel")
    def build_gold_panel():
        return _run_script("build_gold_panel.py")

    # ─── Validación invariantes (fail-fast) ─────────────────────────
    @task(task_id="validate_gold_invariants")
    def validate_gold_invariants() -> dict[str, Any]:
        """Assertions duras sobre el gold construido.

        Rompe el DAG si:
          - panel_muni_semestre no tiene 15.708 filas.
          - falta alguna columna del feature_spec v1.
          - cobertura NBI < 99%.
          - cobertura Población < 99%.
          - cobertura REPS IPS < 75%.
        """
        import duckdb

        gold = f"{DATA_MME}/gold/panel_muni_semestre.parquet"
        con = duckdb.connect(":memory:")

        n = con.execute(f"SELECT COUNT(*) FROM '{gold}'").fetchone()[0]
        if n != 15708:
            raise AssertionError(f"panel_muni_semestre tiene {n} filas, esperado 15.708")

        required = {"cod_mpio", "ano", "semestre", "casos_mme", "nbi_total_pct",
                    "poblacion_total_2018", "pct_subsidiado_muni_bdua", "n_ips_total",
                    "score_capacidad_obstetrica", "casos_mm_anual"}
        cols = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM '{gold}'").fetchall()}
        missing = required - cols
        if missing:
            raise AssertionError(f"Columnas faltantes en gold: {missing}")

        cov_nbi = con.execute(
            f"SELECT 100.0*SUM(CASE WHEN nbi_total_pct IS NOT NULL THEN 1 ELSE 0 END)/COUNT(*) FROM '{gold}'"
        ).fetchone()[0]
        cov_pobl = con.execute(
            f"SELECT 100.0*SUM(CASE WHEN poblacion_total_2018 IS NOT NULL THEN 1 ELSE 0 END)/COUNT(*) FROM '{gold}'"
        ).fetchone()[0]
        cov_reps = con.execute(
            f"SELECT 100.0*SUM(CASE WHEN n_ips_total > 0 THEN 1 ELSE 0 END)/COUNT(*) FROM '{gold}'"
        ).fetchone()[0]

        if cov_nbi < 99.0:
            raise AssertionError(f"Cobertura NBI {cov_nbi:.1f}% < 99%")
        if cov_pobl < 99.0:
            raise AssertionError(f"Cobertura Población {cov_pobl:.1f}% < 99%")
        if cov_reps < 75.0:
            raise AssertionError(f"Cobertura REPS IPS {cov_reps:.1f}% < 75%")

        con.close()
        return {"rows": n, "cov_nbi": cov_nbi, "cov_pobl": cov_pobl, "cov_reps": cov_reps}

    # ─── MinIO mirror (bronze/silver/gold → S3) ─────────────────────
    @task(task_id="sync_minio")
    def sync_minio():
        """Espejo del medallón a buckets MinIO para consumo por DAG 2 y api_predict_mme."""
        aws = {
            "endpoint": os.environ["MLFLOW_S3_ENDPOINT_URL"],
            "ak": os.environ["AWS_ACCESS_KEY_ID"],
            "sk": os.environ["AWS_SECRET_ACCESS_KEY"],
        }
        import boto3
        s3 = boto3.client(
            "s3", endpoint_url=aws["endpoint"],
            aws_access_key_id=aws["ak"], aws_secret_access_key=aws["sk"],
        )
        for bucket in ("mme-bronze", "mme-silver", "mme-gold"):
            try:
                s3.create_bucket(Bucket=bucket)
            except Exception:
                pass  # ya existe

        synced = 0
        for layer in ("bronze", "silver", "gold"):
            src = Path(DATA_MME) / layer
            if not src.exists():
                continue
            for p in src.rglob("*.parquet"):
                key = str(p.relative_to(src))
                s3.upload_file(str(p), f"mme-{layer}", key)
                synced += 1
        return {"files_synced": synced}

    # ─── Wiring ─────────────────────────────────────────────────────
    sivigila = fetch_sivigila_mme()
    sivigila_mm = fetch_sivigila_mm()
    divipola = fetch_divipola()
    nbi = ingest_nbi()
    pobl = ingest_poblacion()
    bdua = ingest_bdua()
    reps = ingest_reps()
    eevv = eevv_staging_check()

    # ingest_reps lee divipola/municipios.parquet — dependencia explícita.
    divipola >> reps

    silver = build_silver()
    [sivigila, divipola] >> silver

    gold = build_gold_panel()
    [silver, sivigila_mm, nbi, pobl, bdua, reps, eevv] >> gold

    validate = validate_gold_invariants()
    gold >> validate

    mirror = sync_minio()
    validate >> mirror


mme_etl_medallion()
