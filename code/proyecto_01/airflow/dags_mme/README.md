# DAGs MME — `dags_mme/`

Pipelines Airflow específicos del proyecto MME Colombia.
Arquitectura completa en `docs/mme/mlops-plan.md`.

## DAGs actuales

| DAG | Schedule | Descripción | Estado |
|---|---|---|---|
| `1-mme_etl_medallion` | `@daily 03:00 UTC` | Ingesta 7 fuentes → silver → gold panel | 🟢 v1 |
| `2-mme_train_and_promote` | `@weekly Lun 04:00 UTC` | Drift + train 4 modelos C3 + promote a Registry | ⏳ |
| `3-mme_outbreak_weekly` | `@weekly Lun 05:00 UTC` | Scoring C1 semanal por municipio | ⏳ |

## Convenciones

- **Nombrado:** `<N>-mme_<verbo>` (N = orden en el pipeline, verbo descriptivo).
- **Tags Airflow:** `["mme", "<fase>", ...]` — facilita filtrado en UI.
- **TaskFlow API:** preferir `@task` y `@dag` sobre clases legacy.
- **Subprocess-based tasks:** los scripts en `scripts/mme/*.py` se ejecutan vía subprocess. Mantiene deps aisladas y scripts standalone-runnables.
- **/opt/repo es RO:** cualquier escritura va a `/opt/airflow/data/mme` (montado RW).
- **Callbacks:** importar `on_failure_callback` desde `_callbacks.py`. Usa Pushgateway si disponible y webhook opcional vía `MME_ALERTS_WEBHOOK`.

## Validación local

```bash
# Syntax
uv run python -c "import sys; sys.path.insert(0, 'proyecto_01/airflow/dags_mme'); \
  exec(open('proyecto_01/airflow/dags_mme/1-mme_etl_medallion.py').read())"

# Via Airflow CLI dentro del scheduler
docker exec proyecto_01-airflow-scheduler-1 airflow dags list-import-errors
docker exec proyecto_01-airflow-scheduler-1 airflow dags test 1-mme_etl_medallion 2026-04-23
```

## Permisos de `data/mme/` (importante)

El worker Airflow corre como UID 50000 (ver compose `user: "${AIRFLOW_UID:-50000}:0"`).
El mount `../data/mme:/opt/airflow/data/mme` debe ser **escribible por UID 50000**.

Si el host monta desde `data/mme/` owned por el usuario humano (uid típico 1000), el
primer DAG run falla con `Cannot open file ... Permission denied`. Fix una sola vez:

```bash
docker run --rm -v $PWD/data/mme:/target alpine \
  sh -c 'chown -R 50000:0 /target && chmod -R 775 /target'
```

Tras esto, el worker puede escribir y el humano sigue pudiendo leer (775 + grupo 0).

## Buckets MinIO usados

- `mme-bronze/` — ingesta raw (particionada por fuente).
- `mme-silver/` — silver normalizado (`mme_clean.parquet`).
- `mme-gold/` — feature store (panel municipio-semestre y semana).
- `mlflows3/` — artifacts MLflow (modelos, SHAP, reports).

Se crean automáticamente en `sync_minio` si no existen.
