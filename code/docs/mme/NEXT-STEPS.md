# MME — próximos pasos (retomar desde aquí)

**Último checkpoint**: 2026-04-26 — Champion en Registry (Spearman dpto 0.836, backtest cv 0.073), drift Evidently funcionando, API `api-predict-mme` y frontend `frontend-mme` sirviendo en el cluster microk8s, stack completo bajo ArgoCD (`mme-root` app-of-apps).

---

## 🟢 Lo que quedó funcionando

| Área | Estado |
|---|---|
| Monorepo `vigilancia-obstetrica-municipal/` | ✅ carpeta autocontenida, nombre canónico salud pública CO |
| DAG 1 `1-mme_etl_medallion` | ✅ gold panel 15.694 × 69 |
| DAG 2 `2-mme_train_and_promote` | ✅ loop completo: drift → train → validate → promote |
| Paquete `src/mme/` | ✅ 50/50 tests unit, mypy --strict clean en archivos tocados |
| Loop de promoción (P1) | ✅ `mlflow_ops.promote_champion()` con gate combinado. Aliases MLflow 3.x |
| Drift real (P2) | ✅ `mme.drift.evidently_runner` + PSI/KS + HTML. Baseline adjunto al champion |
| `api_predict_mme` (F-001) | ✅ FastAPI:8001 con ModelStore + PanelCache + bootstrap residual. 13/13 tests |
| MLflow Registry `mme_vulnerability_baseline` | ✅ champion vigente @ Spearman dpto 0.836 |
| Frontend `frontend-mme` (F-002) | ✅ Next.js 14 + mapa coroplético + ranking + drill-down muni; NodePort 30602 |
| Migración a microk8s + ArgoCD | ✅ 12 Applications gestionadas, GitOps puro (sin `kubectl apply` manual) |
| CI/CD (build-and-push, bump-image-tags, docs) | ✅ 3 workflows verdes; deploy ~5–7 min push→prod |
| Observabilidad full-stack | ✅ Prometheus + Grafana + Loki + Tempo + Pushgateway + Locust |
| Prometheus rules MME + scrape api_predict_mme | ✅ alertas + métricas API |
| Grafana dashboards | ✅ 3 dashboards MME |
| Pushgateway wiring | ✅ DAG 2 publica drift + métricas modelo |

---

## 🔴 Bloqueadores conocidos (documentados, no urgentes)

1. **CeleryExecutor** queda deshabilitado (`profiles: ["celery"]`) por el bug `'NoneType' split` (Airflow #42737). Tasks corren en scheduler con LocalExecutor. Revisar cuando se upgrade a Airflow 2.11+ o celery ≥5.5 con fix.
2. **EEVV del DANE** no integrada aún. El target solo refleja notificación SIVIGILA 549 → subregistro conocido. Ver `docs/mme/dane-eevv-procedure.md`.
3. **Champion v2 sin residuals.npy**: promovido antes del cambio de Sprint 1.A. El drift real detecta `no drift` → no retrain → sigue así. No bloquea: la API cae al bootstrap degenerado (CI = punto). Se resuelve en el próximo ciclo con drift o forzando retrain (Airflow Variable `force_retrain=true`, pendiente de cablear).

---

## 📋 Próximos pasos ordenados por valor

### ✅ Prioridad 1 — CERRADA (2026-04-24)

- [x] **MME-E.3 · promote_c3.py** — `src/mme/tracking/mlflow_ops.py::promote_champion()` con gate `new>=prev*0.95 OR new>=0.65`. Aliases MLflow 3.x. 9 tests unit con MlflowClient mocked. DAG 2 `promote_c3` llama via Airflow Variables (`promote_tolerance`, `promote_absolute_floor`, `promote_dry_run`). Primera promoción ejecutada: champion v1→v2.
- [x] **Validation report enriquecido** — 5 gates: spearman≥0.3, p@50≥0.08, r2>0, overfit-gap≤0.2, mae finito.

### ✅ Prioridad 2 — CERRADA (2026-04-24)

- [x] **MME-E.2 · Evidently + PSI/KS** — `src/mme/drift/evidently_runner.py` con `compute_psi()` quantile-bins + Laplace smoothing. DAG 2 `check_drift` real: load baseline del champion → run_drift_check → push PSI/KS. Validado live: psi_max=0.0000476 (sin drift) → ShortCircuit correcto.

### ✅ Prioridad 3 — Fase MME-F (CERRADA en cluster k8s)

- [x] **F-001 · api-predict-mme** (backend) — FastAPI con `/predict/municipio`, `/predict/batch`, `/predict/ranking`, `/predict/compare` (A/B champion vs challenger), `/model/info`, `/model/reload`, health+metrics. ModelStore hot-swap, PanelCache TTL, residual bootstrap (90% CI). Smoke live OK: Medellín 459 casos. Sirviendo en NodePort 30601.
- [x] **F-002 · frontend-mme** Next.js 14 + ruta `/mme` — mapa coroplético Colombia, ranking departamental, drill-down municipal con SHAP. Tailwind + Recharts. NodePort 30602 + Ingress `mme.localhost`.
- [x] **F-005** Dashboards Grafana `api-predict-mme` + `frontend-mme` provisionados como ConfigMaps con label `grafana_dashboard=1`.
- [x] **F-006** Disclaimer ecological fallacy fijo en `/mme` y en `/mme/municipio/[cod]`.

### 🎯 Prioridad 4 — Rigor metodológico (pendiente)

- [ ] **MME-E.2-bis · check_drift_c3.py con Evidently** (ya hecho en P2)
  Reemplazar el stub en `check_drift` task del DAG 2 por:
  ```python
  from mme.drift.evidently_runner import run_drift_check
  info = run_drift_check(gold_panel_path, champion_baseline_path)
  # info = {"drift_detected": bool, "psi": {feat: val}, "ks": {feat: val}, "html_report": path}
  ```
  - Usar `DataDriftPreset(method="psi")` sobre feature_set_v1 (14 features post-PCA).
  - Publicar `psi_by_feature` y `ks_by_feature` a Pushgateway via `push_drift_status`.
  - Guardar el HTML en `reports/drift/drift_{dataset_cycle}.html`.
  - Gate: re-entrenar si `drift_detected == True` O si `mme_model_test_spearman_dpto` en prod lleva 2 semanas sin subir.

### 🎯 Prioridad 3 — API de servido + frontend (Fase MME-F, 2–3 sesiones)

- [ ] **api_predict_mme** — FastAPI que sirva el champion:
  - `POST /predict/municipio` con features municipales → expectativa de casos MME
  - `GET /predict/ranking?departamento=X` → top-10 municipios por vulnerabilidad
  - `GET /model/info` → metadata del champion (Spearman, fecha, feature_spec_version)
  - Prometheus: latencia p95, requests/s, model_loaded_info
  - Descubrimiento dinámico desde Registry (similar al patrón ModelStore del legacy).

- [ ] **frontend_mme** — Next.js 14:
  - Mapa de Colombia coropleto (municipios) con gradiente por razón MME predicha.
  - Drill-down a departamento → tabla top-N municipios con intervalos de confianza.
  - Filtro temporal (semestre).
  - Integración con MLflow UI vía link externo al run.

- [ ] Re-agregar los dashboards **api_predict_mme** y **frontend_mme** a Grafana cuando los servicios vuelvan.

### 🎯 Prioridad 4 — Rigor metodológico (1 sesión)

- [ ] **Backtesting rolling-window**
  Script `scripts/mme/backtest_rolling.py`:
  - Ventanas: train[2016–2018] → test[2019], train[2016–2019] → test[2020], … hasta 2022.
  - Métrica de estabilidad: coef de variación de Spearman test entre ventanas.
  - Alertar si `cv > 0.15` → modelo inestable temporalmente.

- [ ] **Calibración bayesiana con Clayton-Kaldor**
  El módulo `src/mme/data/clayton_kaldor.py` ya calcula α, β EB. Pendiente:
  - Usar `lambda_eb` como `init_score` en LightGBM (previo poisson-gamma).
  - Comparar vs modelo actual con split temporal → ¿sube Spearman en municipios <10k hab?

### 🎯 Prioridad 5 — Observabilidad avanzada

- [ ] **SLO dashboard** en Grafana:
  - Objetivo: DAG 2 éxito semanal ≥95% en 90 días.
  - Objetivo: modelo en producción con `test_spearman_dpto ≥ 0.65` sostenido.
  - Burn-rate alerts.

- [ ] **Alertmanager** (hoy `static_configs.targets: []`):
  - Webhook a Slack/Discord.
  - Silenciar durante ventana de mantenimiento.

- [ ] **Pushgateway job cleanup**: TTL automático para jobs muertos (hoy las métricas persisten indefinidamente).

### 🎯 Prioridad 6 — Documentación para publicación / paper

- [ ] `docs/mme/methodology.md` — redactar sección metodológica formal:
  - Unidad de análisis, split temporal, justificación de Spearman dpto
  - NegBin vs LGBM Poisson (resultado empírico: LGBM 0.83 vs NegBin 0.52)
  - Clayton-Kaldor EB citado (Clayton & Kaldor 1987)
  - PCA NBI + VIF como feature selection justificable

- [ ] `docs/mme/results.md` — tabla ordenada de experimentos con CI bootstrap.

- [ ] `docs/mme/limitations.md` — subregistro SIVIGILA, MAUP, falacia ecológica, EEVV pending.

---

## 🗂️ Estado de archivos relevantes

| Ruta | Rol |
|---|---|
| `src/mme/cli/train.py` | Entry point del DAG 2 |
| `src/mme/orchestration/train_c3.py` | Pipeline thin (orquesta data/features/models/eval/tracking) |
| `src/mme/tracking/pushgateway.py` | Publica métricas a Prometheus |
| `proyecto_01/airflow/dags_mme/2-mme_train_and_promote.py` | DAG productivo |
| `proyecto_01/grafana/dashboards/03_mme_ml.json` | Dashboard único MME (revisar tras cada cambio de métricas) |
| `proyecto_01/prometheus/rules/mme.rules.yml` | Alertas MME |
| `docs/mme/model-evaluation.md` | Explicación 0.834 + cómo usar MLflow |
| `proyecto_01/jupyterlab/notebook/mme/c3_analysis.ipynb` | Notebook reproducible |

---

## 🚀 Comando rápido para retomar

```bash
# 1. Levantar stack (cluster microk8s + ArgoCD app-of-apps)
cp k8s/.env.example k8s/.env   # llenar secrets
bash k8s/scripts/deploy.sh

# 2. Verificar pods + URLs
microk8s kubectl get pods -A
bash k8s/scripts/show-urls.sh

# 3. Abrir UIs (reemplazar <NODE_IP> con la IP del nodo)
# - Airflow:  http://<NODE_IP>:30080
# - MLflow:   http://<NODE_IP>:30500
# - Grafana:  http://<NODE_IP>:30030  (admin/prom-operator)
# - MinIO:    http://<NODE_IP>:30901
# - Jupyter:  http://<NODE_IP>:30888
# - API:      http://<NODE_IP>:30601/docs
# - Frontend: http://<NODE_IP>:30602/mme

# 4. Re-entrenar manualmente
SCHED=$(microk8s kubectl get pods -n airflow -l component=scheduler -o jsonpath='{.items[0].metadata.name}')
microk8s kubectl exec -n airflow "$SCHED" -c scheduler -- \
  airflow dags trigger 2-mme_train_and_promote
```

Detalle de bootstrap del cluster: [`docs/runbook.md`](../../../docs/runbook.md).
