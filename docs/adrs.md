# Architecture Decision Records (ADRs)

Decisiones arquitectónicas formalizadas. Cada ADR captura el contexto, las opciones evaluadas, la decisión tomada y las consecuencias. Inmutables una vez aceptadas — si una decisión cambia, se crea un ADR nuevo que supersede al anterior.

| ID | Título | Estado | Fecha |
|---|---|---|---|
| [ADR-001](#adr-001-microk8s-single-node-vs-k3d-gke) | microk8s single-node vs k3d / GKE | Aceptada | 2026-04-23 |
| [ADR-002](#adr-002-helm-charts-upstream-manifests-propios) | Helm charts upstream + manifests propios | Aceptada | 2026-04-23 |
| [ADR-003](#adr-003-celeryexecutor-vs-kubernetesexecutor) | CeleryExecutor vs KubernetesExecutor | Aceptada | 2026-04-23 |
| [ADR-004](#adr-004-mlflow-aliases-en-lugar-de-stages) | MLflow aliases en lugar de stages | Aceptada | 2026-04-24 |
| [ADR-005](#adr-005-pvc-rwx-compartido-vs-s3-puro-para-medallon) | PVC RWX compartido vs S3 puro para medallón | Aceptada | 2026-04-25 |
| [ADR-006](#adr-006-multi-source-argocd-applications) | Multi-source ArgoCD Applications | Aceptada | 2026-04-23 |
| [ADR-007](#adr-007-bypass-airflow-celery-worker-cli) | Bypass `airflow celery worker` CLI | Aceptada | 2026-04-25 |
| [ADR-008](#adr-008-hostnames-cortos-vs-fqdn-completo-ndots1) | Hostnames cortos vs FQDN completo (`ndots:1`) | Aceptada | 2026-04-25 |
| [ADR-009](#adr-009-bootstrap-ci-residual-en-tiempo-de-prediccion) | Bootstrap CI residual en tiempo de predicción | Aceptada | 2026-04-24 |
| [ADR-010](#adr-010-bump-de-image-tags-via-gha-vs-argocd-image-updater) | Bump de image tags via GHA vs ArgoCD Image Updater | Aceptada | 2026-04-25 |

---

## ADR-001 — microk8s single-node vs k3d / GKE

**Contexto.** Ejercicio investigativo con presupuesto cero, requiere reproducibilidad y camino a multi-host eventual. Cualquier persona evaluando el trabajo debe poder levantar el stack en su máquina.

**Opciones evaluadas.**

| Opción | Pros | Contras |
|---|---|---|
| GKE / EKS | Producción real, batteries-included | Costo $$, requiere cuenta cloud, no reproducible offline |
| k3d (k3s en Docker) | Liviano, rápido boot | Sin add-ons one-liner, requiere setup manual de Helm controllers |
| **microk8s** | Add-ons (`enable observability argocd metallb registry`), camino a multi-host con `microk8s join` | Requiere snap + systemd; en WSL2 implica habilitar systemd opt-in |

**Decisión.** microk8s 1.28+ single-node sobre Ubuntu 22.04 / WSL2.

**Consecuencias.**

- ✓ Setup en <30 min en máquina nueva.
- ✓ Mismo cluster extensible a VPS Ubuntu con `microk8s join`.
- ✓ Add-ons incluidos: dns, hostpath-storage, metallb, metrics-server, ingress, observability, registry.
- ✗ Snap impone restricciones de filesystem (no rutas en `~`).
- ✗ WSL2 requiere `.wslconfig` apropiado para evitar OOM con stack completo (ver [ADR-008](#adr-008-hostnames-cortos-vs-fqdn-completo-ndots1) y runbook).

---

## ADR-002 — Helm charts upstream + manifests propios

**Contexto.** Stack tiene 12 servicios. Reescribir todos los manifests desde cero no es escalable; depender 100% de charts no permite customizar apps propias.

**Decisión.**

- **Charts upstream** (postgres × 2, MinIO, MLflow, Airflow): probes, resources, secrets, métricas estandarizados ya resueltos por la comunidad.
- **Manifests propios** (api-predict-mme, frontend-mme, jupyterlab, pgadmin, locust): apps custom del proyecto con manifests simples (Deployment + Service + HPA + Ingress).

**Consecuencias.**

- ✓ No re-inventar StatefulSets de Postgres ni el chart de Airflow (cientos de líneas).
- ✓ Apps propias se versionan en este repo, sin dependencia de un chart museum.
- ✗ Mix de patrones (Helm vs raw manifests) requiere documentación clara — resuelto en [docs/gitops.md](gitops.md).

---

## ADR-003 — CeleryExecutor vs KubernetesExecutor

**Contexto.** Airflow 2.10.5 ofrece dos executors viables en K8s: `KubernetesExecutor` (un pod por task) y `CeleryExecutor` (workers persistentes).

**Opciones evaluadas.**

| Aspecto | KubernetesExecutor | CeleryExecutor |
|---|---|---|
| Aislamiento por task | Sí (pod efímero) | No (workers compartidos) |
| Latencia de start | 5–15s por pod | <1s |
| Recursos en idle | 0 | workers always-on |
| Compatibilidad scripts/ y datos compartidos | Requiere PVC RWX o re-mount por task | PVC mountado al worker, todos los tasks lo ven |
| Bug `pidfile=None` Airflow 2.10.5 | No aplica | **Aplica — requiere bypass** |

**Decisión.** CeleryExecutor con 2 workers, mem 4Gi cada uno (subido desde 2Gi tras OOM de `train_c3` con Optuna+LightGBM).

**Consecuencias.**

- ✓ Latencia de DAG runs predecible (<1s entre tasks).
- ✓ PVC `mme-data` mountado RWX en workers permite acceso unificado al medallón.
- ✗ Workers always-on consumen ~8Gi RAM permanente.
- ✗ Bug Airflow 2.10.5 + provider-celery 3.10.0 no propaga `--pidfile` → ver [ADR-007](#adr-007-bypass-airflow-celery-worker-cli).

---

## ADR-004 — MLflow aliases en lugar de stages

**Contexto.** MLflow 2.9 deprecó stages (`None/Staging/Production/Archived`). MLflow 3.x los elimina en favor de **aliases** (etiquetas mutables sobre versiones del modelo).

**Decisión.** Usar aliases `@champion` y `@challenger` (resolvibles via `models:/<name>@champion`). Promoción gestionada por `mme.tracking.mlflow_ops.promote_champion()`.

**Consecuencias.**

- ✓ Compatible con MLflow 3.3.2 (chart bitnami actual).
- ✓ Permite A/B testing (champion vs challenger) sin acoplar a un workflow rígido.
- ✓ Rollback inmediato: re-asignar `@champion` a versión previa + `/model/reload`.
- ✗ Código que aún use `mlflow.transition_model_version_stage()` no compila — resuelto en `mlflow_ops.py`.
- ✗ Modelos sin flavor nativo (statsmodels GLM NegBin) requieren wrap en `mlflow.pyfunc.PythonModel` con `infer_signature(sample_in, sample_out)`.

---

## ADR-005 — PVC RWX compartido vs S3 puro para medallón

**Contexto.** El medallón bronze/silver/gold se escribe desde Airflow workers y se lee desde la API y JupyterLab. Hay dos esquemas viables: (a) escribir solo a MinIO S3 y leer desde S3 en todos los consumidores; (b) PVC RWX compartido + sync a S3 al final del DAG.

**Decisión.** **PVC RWX `mme-data`** (5Gi, `microk8s-hostpath`) montado en scheduler + triggerer + workers + api-predict-mme + jupyterlab. `sync_minio` al final del DAG 1 hace mirror PVC → S3 (backup/distribución externa).

**Razones.**

- Latencia: lectura desde PVC es local (~5ms vs ~50ms via S3 con boto3).
- Atomicidad: durante el DAG, los tasks ven el filesystem consistente sin esperar sync a S3.
- DuckDB queries sobre parquet: file-system based, no soporta S3 streaming nativo sin httpfs extension.
- API arranca rápido en cluster fresco si el PVC ya tiene panel (no espera DAG 1 + sync).

**Consecuencias.**

- ✓ DAG runs ~3× más rápidos en silver/gold builds.
- ✓ API `/readyz` puede chequear panel en filesystem directamente.
- ✗ RWX requiere driver compatible (microk8s-hostpath OK; en single-node funciona; en multi-node requiere NFS o longhorn).
- ✗ `accessModes` es **inmutable** post-creación. Si se cambia a multi-node, hay que re-crear el PVC (registrado en risk-map).

---

## ADR-006 — Multi-source ArgoCD Applications

**Contexto.** Charts oficiales (bitnami, apache-airflow) son repos externos. Hay tres formas de pasar values:

1. Inline en `Application.spec.helm.values` — strings JSON gigantes.
2. Fork del chart al repo propio.
3. **Multi-source**: chart upstream + values en otro repo, conectados por `$values` ref.

**Decisión.** Multi-source pattern documentado en [docs/gitops.md §multi-source](gitops.md#multi-source-para-charts-upstream).

**Consecuencias.**

- ✓ Single source of truth para values (`k8s/infra/<chart>-values.yaml` en este repo).
- ✓ No acoplamos ciclo de release del chart con el del proyecto.
- ✓ Permite editar values sin tocar la `Application` CR.
- ✗ Spec del CR más compleja (2 sources con `ref: values`).
- ✗ Versión mínima ArgoCD 2.6+ (multi-source GA).

---

## ADR-007 — Bypass `airflow celery worker` CLI

**Contexto.** Bug confirmado en Airflow 2.10.5 + provider-celery hasta 3.10.0: el comando `airflow celery worker` no propaga `--pidfile` a las opciones de Celery. Cualquier celery 5.x explota con `nodesplit` cuando se usa el chart oficial.

**Decisión.** En `airflow-values.yaml` → `workers.args`, invocar el CLI de Celery directamente:

```yaml
workers:
  args:
    - "celery"
    - "--app"
    - "airflow.providers.celery.executors.celery_executor.app"
    - "worker"
    - "--loglevel=INFO"
    - "--concurrency=2"
```

**Consecuencias.**

- ✓ Workers arrancan correctamente, DAGs ejecutan OK.
- ✗ Logs in-task no se sirven al webserver vía 8793 (path interno asume invocación via `airflow celery worker`). Mitigación: logs van igual a Loki via Promtail, accesibles desde Grafana.
- 🔄 Re-evaluar al upgradear a Airflow 2.11+ (parche upstream esperado).

---

## ADR-008 — Hostnames cortos vs FQDN completo (`ndots:1`)

**Contexto.** WSL2 host inyecta un `search domain` corporativo con `ndots:5` (default K8s). Dominios externos como `www.datos.gov.co` (3 dots < 5) resuelven primero contra el wildcard interno del dominio corporativo, devolviendo IPs públicas con cert self-signed → SSLError en ingesta.

**Decisión.** Patch runtime via script `k8s/scripts/apply-airflow-dns-patch.sh` que aplica `dnsConfig.options.ndots=1` a los deployments del namespace airflow. Re-ejecutable post-sync de ArgoCD (idempotente).

**Por qué no values del chart.** Apache Airflow chart 1.16.0 **no expone** `dnsConfig` en values (ignora silenciosamente la key). Issue trackeable upstream.

**Consecuencias.**

- ✓ Ingesta SIVIGILA / DANE / BDUA / REPS funciona.
- ✗ Cada rotación de pods de Airflow (sync de ArgoCD, restart manual) requiere re-aplicar el patch.
- ✗ Solución es WSL2-specific; en cluster multi-node sin search domain corporativo no aplica.
- 🔄 Re-evaluar al upgradear chart Apache Airflow ≥1.17 si exponen `dnsConfig`.

---

## ADR-009 — Bootstrap CI residual en tiempo de predicción

**Contexto.** PAREMM v5 necesita no solo el ranking de municipios sino una **medida de incertidumbre** sobre la razón predicha para tomar decisiones de asignación de recursos.

**Opciones evaluadas.**

| Opción | Pros | Contras |
|---|---|---|
| CI por error estándar GLM | Cerrado, rápido | Solo aplica a Poisson/NegBin GLM, no a LightGBM challenger |
| CI bayesiano (NUTS) | Riguroso, posterior completo | Costo computacional prohibitivo en serving online |
| **Bootstrap residual** | Funciona para cualquier modelo, paraleable | Requiere n=200 resamples → ~20ms por predicción |

**Decisión.** Bootstrap residual con n=200, seed=42, CI al 90%. Calculado en `app/services/bootstrap.py` al servir cada predicción.

**Consecuencias.**

- ✓ Latencia p99 del endpoint `/predict/municipio` se mantiene <150ms (verificado con Locust).
- ✓ Mismo procedimiento aplica a champion (LightGBM) y challenger (GLM).
- ✓ Resultado reproducible (seed fijo).
- ✗ n=200 es trade-off; CI puede ser ruidoso en muni con NV<50 (mitigado por Clayton-Kaldor smoothing aguas arriba).

---

## ADR-010 — Bump de image tags via GHA vs ArgoCD Image Updater

**Contexto.** Tras un build exitoso, los manifests Kubernetes deben referenciar el tag nuevo para que ArgoCD aplique la nueva versión.

**Opciones evaluadas.**

| Opción | Pros | Contras |
|---|---|---|
| ArgoCD Image Updater | Pull-based, sin commits a main | Componente extra a mantener, write-back a git con SSH key adicional |
| **GHA bump-image-tags.yml** | Pipeline transparente en Actions, commit visible en git log | Requiere `contents: write` permission, commits ruidosos en main |

**Decisión.** GHA workflow `bump-image-tags.yml` triggered por `workflow_run` del build job exitoso. Hace `sed -i` sobre los deployment.yaml afectados y commit con mensaje `chore(k8s): bump image tags to <YYYYMMDD-sha>`.

**Consecuencias.**

- ✓ Trazabilidad: cada deploy a producción es un commit en main con SHA y fecha.
- ✓ Sin componentes extras en el cluster.
- ✗ Commits "ruido" en main (mitigable con squash o branch dedicada).
- ✗ Charts custom (`mme-airflow`, `mme-mlflow`) no se bumpean automáticamente — requiere editar `image.repository` en `k8s/infra/<chart>-values.yaml` manualmente.

---

## Decisiones rechazadas (negative ADRs)

Decisiones consideradas y descartadas, documentadas para que no se reabran sin contexto.

### NACK-001 — Migración de Compose a K8s vía `kompose convert`

**Por qué se descartó.** `kompose convert` genera manifests pobres: sin probes, sin PVCs (usa hostPath), sin HPAs, mezcla ConfigMaps y Secrets, deja `imagePullPolicy` inconsistente. Migración manual con Helm + manifests escritos da mucha mayor calidad. (2026-04-23)

### NACK-002 — Service Mesh (Istio / Linkerd)

**Por qué se descartó.** Overhead operacional alto (sidecars en cada pod) sin justificación clara: no hay requerimientos de mTLS forzado, traffic shifting avanzado ni circuit breaking que no resuelva K8s nativo. OpenTelemetry → Tempo cubre observabilidad inter-servicio. Re-evaluable si se llega a multi-tenant o multi-cluster. (2026-04-25)

### NACK-003 — Feature Store dedicado (Feast / Tecton)

**Por qué se descartó.** El gold panel `panel_muni_semestre.parquet` (15.708 filas × 14 cols) cabe en RAM. Feature store agregaría latencia de red y un servicio más a mantener para 0 ganancia operacional. Re-evaluable si granularidad pasa a semanal con join en línea, o si se incorporan features streaming. (2026-04-23)

### NACK-004 — Modelo en ONNX para serving

**Por qué se descartó.** LightGBM nativo + bootstrap residual + SHAP requiere el árbol original. ONNX export pierde la capacidad de calcular SHAP, y el bootstrap residual requiere acceso al `predict()` del modelo para resamplear. Performance gain marginal (LightGBM ya predice en <5ms). (2026-04-24)
