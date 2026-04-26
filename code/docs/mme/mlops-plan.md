# Arquitectura MLOps — Proyecto MME Colombia

> Cómo se implementa el problema ML definido en [`ml-problem-definition.md`](ml-problem-definition.md).
> Versión 1.1 · 2026-04-26 (migración del stack Compose `proyecto_01/` → microk8s + ArgoCD).

> **Nota.** Las referencias a `proyecto_01/` y `docker compose` en este documento describen el **stack histórico**. El stack productivo actual corre sobre microk8s (ver [`docs/runbook.md`](../../../docs/runbook.md) y [`k8s/README.md`](../../../k8s/README.md)). El diseño de DAGs, registry, métricas y métodos descritos abajo se mantiene; solo cambia la capa de despliegue. Los DAGs siguen viviendo en `code/proyecto_01/airflow/dags_mme/` porque Airflow los carga vía sidecar `gitSync`.

---

## 1. Principios

1. **Reproducibilidad:** todo el pipeline se levanta desde cero con `bash k8s/scripts/deploy.sh` (microk8s + ArgoCD app-of-apps). El stack histórico `docker compose up` en `proyecto_01/` queda como referencia.
2. **Degradación graceful:** fuentes opcionales (EEVV, étnia) degradan a NULL sin romper.
3. **Observabilidad por defecto:** cada DAG emite métricas a Prometheus; cada run loggea a MLflow; cada fallo dispara `_callbacks.on_failure_callback` con detalle suficiente para diagnóstico.
4. **Audit trail:** manifests JSON con SHA256 por cada parquet bronze/silver/gold. Cambios de schema bumps `feature_spec_version`.
5. **Separación de responsabilidades:** data engineering (DAG ETL) vs ML (DAG training) vs serving (API) vs UI (frontend).
6. **Defensa en profundidad frente a la falacia ecológica:** el disclaimer aparece en la API, en el frontend, en el SHAP y en el reporte final. Nunca se omite.

---

## 2. Arquitectura end-to-end

```
                ┌───────────────────────────────────────────────────────────┐
                │                 FUENTES 100% PÚBLICAS                      │
                │  Socrata INS (4hyg-wa9d MME + SIVIGILA MM)                │
                │  DANE CNPV 2018 (NBI, Población ajustada)                 │
                │  DANE EEVV Nacimientos (descarga manual — staging)        │
                │  MinSalud BDUA (hn4i-593p)                                │
                │  MinSalud REPS (ugc5-acjp + s2ru-bqt6)                    │
                └───────────────────────────┬───────────────────────────────┘
                                            │ Airflow CeleryExecutor
                                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  DAG  1-mme_etl_medallion    (@daily 03:00 UTC)                             │
│                                                                              │
│  fetch_sivigila_mme ─┐                                                       │
│  fetch_sivigila_mm  ─┤     → build_silver → build_gold_panel                 │
│  fetch_divipola     ─┤       (reglas 549)   (join 5 bronzes, 69 cols)       │
│  ingest_nbi         ─┤              │                                        │
│  ingest_poblacion   ─┤              ▼                                        │
│  ingest_bdua        ─┤     validate_gold_invariants (fail fast si falla)    │
│  ingest_reps        ─┘              │                                        │
│  eevv_staging_check (opcional, ingiere si hay CSVs)                          │
└─────────────────────────────────────────┬───────────────────────────────────┘
                                          │
                                          │ gold en disco + S3 MinIO mirror
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  DAG  2-mme_train_and_promote    (@weekly Lun 04:00 UTC)                    │
│                                                                              │
│  check_drift (Evidently+PSI/KS vs último champion → Pushgateway)            │
│     └─► gate_train (ShortCircuit: no_drift ∧ champion vigente → skip)       │
│            └─► train_c3:                                                     │
│                  poisson | negbin | lightgbm_tweedie | lightgbm_count        │
│                  + Clayton-Kaldor + SHAP                                     │
│                  → MLflow experimento mme_vulnerability_v1                   │
│                  → Artifacts: model, shap_summary.png, ranking_top_50.csv    │
│                  → Tags: feature_spec_version, dataset_cycle, regime         │
│            └─► validate_report (assert criterios Go/No-Go)                  │
│                   └─► promote_c3:                                            │
│                         champion/challenger → Registry mme_vulnerability_*   │
└─────────────────────────────────────────┬───────────────────────────────────┘
                                          │
                                          │ hot reload vía /model/reload
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  api_predict_mme  (FastAPI :8002)                                           │
│    POST /mme/score {cod_mpio, ano} → {score, razon_esperada, shap_top_5}    │
│    GET  /mme/ranking?year=2022 → top 50 municipios con SHAP                 │
│    GET  /models/production                                                   │
│    POST /model/reload                                                        │
│    /healthz, /readyz, /metrics                                               │
└─────────────────────────────────────────┬───────────────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Frontend Next.js 14  /mme                                                   │
│    Mapa coroplético Colombia (DIVIPOLA GeoJSON + Recharts/Leaflet)          │
│    Drill-down municipio: serie temporal + features + SHAP top-5             │
│    Panel outbreak C1 (cuando DAG 3 esté listo)                              │
│    Disclaimer ecological fallacy persistente                                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Observabilidad (Prometheus + Grafana + cAdvisor + statsd-exporter)         │
│    Dashboard `mme-overview`: freshness ingesta, salud DAGs, razón nacional  │
│    Dashboard `mme-modelo`: drift features, métricas test, ranking inferido  │
│    Dashboard `mme-outbreak`: alertas activas C1 por municipio               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. DAGs en detalle

### DAG 1 — `1-mme_etl_medallion`

**Schedule:** `@daily` a las 03:00 UTC (sin colisionar con crons del usuario).
**Timeout DAG:** 2h. Tasks individuales 30min con retry exponential.

**Tasks (TaskFlow API):**

| Task | Upstream | Wraps | Output |
|---|---|---|---|
| `fetch_sivigila_mme` | — | `ingest_sivigila_bronze.py` | `data/mme/bronze/year=YYYY/*.parquet` |
| `fetch_sivigila_mm` | — | `ingest_sivigila_mm_bronze.py` | `data/mme/bronze/sivigila_mm/year=YYYY/*.parquet` |
| `fetch_divipola` | — | `ingest_divipola_bronze.py` | `data/mme/bronze/divipola/*.parquet` |
| `ingest_nbi` | — | `ingest_censo2018_bronze.py` | `data/mme/bronze/censo2018/nbi_municipios.parquet` |
| `ingest_poblacion` | — | `ingest_censo2018_poblacion_bronze.py` | `...poblacion_municipios.parquet` |
| `ingest_bdua` | — | `ingest_bdua_bronze.py` | `data/mme/bronze/bdua/*.parquet` |
| `ingest_reps` | — | `ingest_reps_bronze.py` | `data/mme/bronze/reps/{ips,capacidad}_por_muni.parquet` |
| `eevv_staging_check` | — | ingesta condicional de staging | `data/mme/bronze/dane/eevv/year=YYYY/*.parquet` (si hay CSVs) |
| `build_silver` | fetch_sivigila_mme, fetch_divipola | `build_silver.py` | `data/mme/silver/mme_clean.parquet` |
| `build_gold_panel` | build_silver, ingest_nbi, ingest_poblacion, ingest_bdua, ingest_reps, fetch_sivigila_mm | `build_gold_panel.py` | `data/mme/gold/{panel_muni_semestre, panel_muni_semana}.parquet` |
| `validate_gold_invariants` | build_gold_panel | test asserts | fail si invariantes rotos |
| `sync_minio` | validate_gold_invariants | mc mirror | `s3://mme-gold/` |

**Connections Airflow requeridas:**
- `postgres_default` (Airflow backend).
- `aws_default` (MinIO endpoint, creds desde .env).

**Paralelización:** 7 tareas fetch/ingest en paralelo (ninguna depende de otra). build_silver depende de 2. build_gold de 6. validate_gold de 1.

**Invariantes validadas post-gold:**
- `panel_muni_semestre` tiene 15.708 filas exactas (1.122 muni × 7 años × 2 sem).
- Todos los `cod_mpio` son DIVIPOLA válidos.
- `casos_mme ≥ 0`, `is_silent_period ∈ {0,1}`.
- Cobertura NBI ≥ 99%.
- Cobertura REPS ≥ 75% (IPS).
- Al menos 1 fila con `razon_mme_por_1000_nv` no NULL cuando EEVV está poblada.

---

### DAG 2 — `2-mme_train_and_promote`

**Schedule:** `@weekly` Lunes 04:00 UTC.
**Condicional:** solo corre train si (a) drift detectado O (b) champion >30 días sin retrain O (c) manual trigger.

**Tasks:**

1. **`check_drift`** — `scripts/mme/check_drift_c3.py` (nuevo):
   - Baseline: gold panel del último champion (tag `dataset_cycle`).
   - Current: gold panel actual.
   - Evidently `DataDriftPreset` → HTML a `data/drift_reports/mme/`.
   - PSI/KS propios sobre features Demora I/II/III → Prometheus Pushgateway:
     - `mme_feature_psi{feature, cycle}`
     - `mme_feature_ks_pvalue{feature, cycle}`
     - `mme_drift_status{status="no_drift|drift"}`
     - `mme_drift_last_run_ts`
   - Thresholds: PSI 0.10 / 0.25, KS α=0.01.

2. **`gate_train`** — ShortCircuit: skip si no_drift AND champion < 30 días.

3. **`train_c3`** — `scripts/mme/train_baselines_c3.py` (nuevo):
   - Input: `data/mme/gold/panel_muni_semestre.parquet`.
   - Split: train ≤ 2020, val 2021, test 2022.
   - Suavizamiento Clayton-Kaldor pre-modelo para muni NV<50.
   - 4 familias de modelos:
     - **Poisson GLM** con offset `log(nv_esperados)` (fallback `log(poblacion/2)`).
     - **NegBin GLM** (sobredispersión común en counts).
     - **LightGBM objective=tweedie** (no-lineal, offset vía `init_score`).
     - **LightGBM objective=regression** sobre `razon_mme_por_1000_nv` directa.
   - Features: del feature_spec v1 (sin las `*_eevv` si EEVV ausente).
   - Métricas: MAE razón, Spearman dpto, precision@top-50, Brier, calibración.
   - SHAP: summary plot + 10 muni ejemplares (5 top vulnerabilidad, 5 fondo).
   - MLflow experimento: `mme_vulnerability_v1`.
   - Tags obligatorios: `feature_spec_version=v1`, `dataset_cycle=<date>`, `regime=pre-eevv|post-eevv`, `model_family=poisson|negbin|lgbm_tweedie|lgbm_count`, `split_strategy=temporal`.
   - Artifacts: modelo sklearn/lightgbm, `shap_summary.png`, `shap_local_<muni>.png`×10, `ranking_top_50.csv`, `classification_report.txt`.

4. **`validate_report`** — assert criterios Go/No-Go del `ml-problem-definition.md` §6. Si falla → DAG FAIL sin promoción.

5. **`promote_c3`** — `scripts/mme/promote_model.py` (nuevo, adaptado):
   - Lee los 4 runs del experimento, rankea por (Spearman_dpto, MAE_razon).
   - Registra el mejor en Registry `mme_vulnerability_baseline`, transition a Staging.
   - Si supera al champion actual (Spearman ≥ champion × 0.98) → Production (archive anterior).
   - Aliases: `@champion` / `@challenger`.

**Reporte:** `data/mme/promotion_reports/{run_id}.md` + `last_run.md`.

---

### DAG 3 — `3-mme_outbreak_weekly` (Fase posterior)

**Schedule:** `@weekly` Lun 05:00 UTC (después del train).
**Tasks:**
1. `load_champion_c1` — carga modelo outbreak (EARS/Farrington/Prophet).
2. `score_all_munis` — genera alertas por (cod_mpio, semana_actual).
3. `push_grafana` — Pushgateway → dashboard MME outbreak.
4. `write_alerts_log` — `data/mme/alerts/alerts_<YYYYWW>.parquet`.

---

## 4. Stack físico (reusa `proyecto_01/`)

| Servicio | Rol MME | Cambios |
|---|---|---|
| `postgres_airflow` :5432 | Metadata DAGs MME | — |
| `postgres_mlflow` :5433 | Backend MLflow (nuevo experimento `mme_vulnerability_v1`) | — |
| `redis` | Broker Celery | — |
| `minio` :9000/9001 | Buckets `mme-bronze`, `mme-silver`, `mme-gold` (nuevos) | Crear buckets |
| `mlflow` :5000 | Tracking + Registry MME | Agregar experimento |
| `airflow-webserver` :8080 | UI con DAGs `dags_mme/` | Montar `dags_mme/` |
| `airflow-worker` | Ejecutor DAGs MME | Montar `scripts/mme/` y `data/mme/` |
| `prometheus` :9090 | Métricas | Agregar scrape config api_predict_mme |
| `grafana` :3000 | Dashboards MME nuevos | Provisioning JSON |
| `pushgateway` | Métricas drift + outbreak | — |
| `statsd-exporter` | Métricas Airflow | — |
| `pgadmin` :5050 | DBA | — |
| `jupyter_dev` :8888 | Notebooks MME exploración | Acceso a `data/mme/` |

**Servicios removidos** (legacy rugpull): `api_datos`, `api_predict`, `frontend`.

**Servicios a agregar** (Fase MME-F):
- `api_predict_mme` :8002 — FastAPI inferencia MME.
- `frontend_mme` :3001 — Next.js `/mme`.

---

## 5. Versionado y tags MLflow

**Experimento:** `mme_vulnerability_v1`.

**Tags por run:**
```
feature_spec_version: "v1" | "v2" …
dataset_cycle:        ISO date del gold usado (derivado de _manifest.json)
regime:               "pre-eevv" | "post-eevv"
model_family:         "poisson" | "negbin" | "lgbm_tweedie" | "lgbm_count"
split_strategy:       "temporal_train2020_val2021_test2022"
clayton_kaldor:       "applied" | "not_applied"
offset_source:        "nv_eevv" | "poblacion_censo"
n_features:           int
n_muni_train:         int
data_eevv_joined:     "true" | "false"
data_nbi_joined:      "true" | "false"
data_bdua_joined:     "true" | "false"
data_reps_joined:     "true" | "false"
```

**Registry models:** `mme_vulnerability_baseline`.
**Stages:** None → Staging → Production. Archive cuando se reemplaza.

---

## 6. Observabilidad

### Métricas custom nuevas (api_predict_mme)

```
mme_predict_latency_seconds{endpoint, model_name}
mme_predict_total{endpoint, model_name, outcome}
mme_ranking_top50_drift_vs_previous{}
mme_model_loaded_info{model_name, version, is_active}
```

### Métricas Pushgateway (DAG drift)

```
mme_feature_psi{feature, cycle}
mme_feature_ks_pvalue{feature, cycle}
mme_drift_status{status}
mme_drift_share{}
mme_drift_last_run_timestamp_seconds{}
mme_train_last_run_timestamp_seconds{}
mme_train_status{status}
```

### Métricas DAG (vía StatsD → Prometheus ya configurado)

Incluye automáticamente `airflow_dagrun_duration_seconds{dag_id="1-mme_etl_medallion", status}`.

### Dashboards Grafana (JSON provisioning)

1. **`mme-overview.json`** — freshness de ingesta por fuente, última razón nacional, número de silentes detectados, estado DAGs MME.
2. **`mme-modelo.json`** — drift features (PSI/KS heatmap), métricas test por run, ranking top-20 muni predichos vs observados, champion actual.
3. **`mme-outbreak.json`** — alertas semanales activas, top 10 muni con alerta, distribución por dpto.

---

## 7. Testing

### Tests pytest (nuevos, `tests/mme/`)

- `test_silver_invariants.py` — reglas 549 aplicadas, 0 duplicados, 0 huérfanos DIVIPOLA.
- `test_gold_shape.py` — panel tiene 15.708 filas exactas, todas las columnas del spec v1.
- `test_gold_coverage.py` — cobertura NBI/Pobl/BDUA ≥99%, REPS ≥75%.
- `test_clayton_kaldor.py` — suavizamiento se aplica correctamente en muni NV<50.
- `test_model_metrics_gate.py` — los 4 modelos superan umbrales mínimos.

### CI (`.github/workflows/ci.yml` a reescribir)

Jobs:
1. `lint` — ruff check/format.
2. `test-mme-contract` — pytest tests/mme/.
3. `dag-syntax` — `airflow dags list-import-errors` = 0 sobre `dags_mme/`.
4. `compose-validate` — `docker compose config --quiet`.
5. `build-images` — `api_predict_mme`, `frontend_mme` (cuando existan).

---

## 8. Hoja de ruta de implementación

| # | Paso | Archivo | Estado |
|---|---|---|---|
| 1 | `docs/mme/ml-problem-definition.md` | este doc | 🟢 |
| 2 | `docs/mme/mlops-plan.md` | este doc | 🟢 |
| 3 | `docs/mme/features-spec-v1.md` | previo | 🟢 |
| 4 | `proyecto_01/airflow/dags_mme/1-mme_etl_medallion.py` | DAG ETL | 🟡 en progreso |
| 5 | `proyecto_01/airflow/dags_mme/{silver_lib, features_lib, _callbacks}.py` | helpers | 🟡 |
| 6 | `proyecto_01/compose.yaml` | cleanup + add buckets MinIO | 🟡 |
| 7 | `scripts/mme/train_baselines_c3.py` | training | ⏳ |
| 8 | `scripts/mme/check_drift_c3.py` | drift | ⏳ |
| 9 | `scripts/mme/promote_c3.py` | registry | ⏳ |
| 10 | `proyecto_01/airflow/dags_mme/2-mme_train_and_promote.py` | DAG train | ⏳ |
| 11 | `api_predict_mme/` | serving | ⏳ |
| 12 | `frontend_mme/` ruta `/mme` | UI | ⏳ |
| 13 | `proyecto_01/grafana/mme-*.json` | dashboards | ⏳ |
| 14 | `tests/mme/*.py` | tests | ⏳ |
| 15 | `.github/workflows/ci.yml` | CI | ⏳ |
| 16 | `README.md` root | refresh | 🟡 |

**Hito 1 (ETL funcional):** pasos 1-6. Entregable: gold se regenera por DAG Airflow diario.
**Hito 2 (Modelado baseline):** pasos 7-10. Entregable: modelo en Registry Production.
**Hito 3 (Serving + UI):** pasos 11-13. Entregable: API +mapa coroplético navegable.
**Hito 4 (Calidad):** pasos 14-15. Entregable: CI verde.

---

## Versionado

| Versión | Fecha | Cambio |
|---|---|---|
| v1.0 | 2026-04-23 | Primera versión post-limpieza rugpull + EDA M-009. |
