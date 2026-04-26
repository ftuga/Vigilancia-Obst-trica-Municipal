# DAGs MME — `dags_mme/`

Pipelines Airflow del proyecto MME Colombia. Aunque el directorio cuelga del stack histórico `proyecto_01/`, **estos DAGs son la fuente de verdad activa**: Airflow en el cluster microk8s los carga vía sidecar `gitSync` (path `code/proyecto_01/airflow/dags_mme`, ver `k8s/infra/airflow-values.yaml`).

Arquitectura del pipeline ML en [`docs/mme/mlops-plan.md`](../../docs/mme/mlops-plan.md). Despliegue del cluster en [`docs/runbook.md`](../../../../docs/runbook.md).

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

## Validación local (sin cluster)

```bash
# Syntax-check standalone
uv run python -c "import sys; sys.path.insert(0, 'code/proyecto_01/airflow/dags_mme'); \
  exec(open('code/proyecto_01/airflow/dags_mme/1-mme_etl_medallion.py').read())"
```

## Validación dentro del cluster

```bash
SCHED=$(microk8s kubectl get pods -n airflow -l component=scheduler -o jsonpath='{.items[0].metadata.name}')

# Errores de import
microk8s kubectl exec -n airflow "$SCHED" -c scheduler -- airflow dags list-import-errors

# Test de un DAG run sin schedule
microk8s kubectl exec -n airflow "$SCHED" -c scheduler -- airflow dags test 1-mme_etl_medallion 2026-04-26
```

El sidecar `gitSync` re-clona el repo cada 60s — los cambios pusheados a `main` aparecen en el scheduler sin restart.

## Permisos del PVC `mme-data`

El worker Airflow corre como UID 50000. El PVC `mme-data` (RWX, montado en `/opt/airflow/data/mme`) debe ser escribible por ese UID. El chart Apache Airflow lo gestiona vía `securityContext.fsGroup: 50000` en `k8s/infra/airflow-values.yaml`. Si tras un cambio de chart aparecen errores `Permission denied`, verificar ese campo y los `accessModes` del PVC con `microk8s kubectl describe pvc mme-data -n airflow`.

## Buckets MinIO usados

- `mme-bronze/` — ingesta raw (particionada por fuente).
- `mme-silver/` — silver normalizado (`mme_clean.parquet`).
- `mme-gold/` — feature store (panel municipio-semestre y semana).
- `mlflows3/` — artifacts MLflow (modelos, SHAP, reports).

Se crean automáticamente en `sync_minio` si no existen.
