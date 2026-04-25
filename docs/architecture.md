# Arquitectura del sistema

Sistema MLOps para predecir vulnerabilidad obstétrica municipal. Stack desplegado sobre MicroK8s single-node, parametrizado para multi-host vía `.env`.

---

## 1. Vista de despliegue (deployment view)

```
┌───────────────────────────────────────────────────────────────────────┐
│  Nodo MicroK8s (Ubuntu 22.04 / WSL2 / VPS)                           │
│                                                                       │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐  │
│  │ ns: airflow     │  │ ns: mlflow      │  │ ns: data            │  │
│  │                 │  │                 │  │                     │  │
│  │ • webserver     │  │ • mlflow-       │  │ • minio             │  │
│  │ • scheduler     │  │   tracking      │  │   (StatefulSet)     │  │
│  │ • triggerer     │  │ • postgres-     │  │   PVC 50Gi          │  │
│  │ • worker × 2    │  │   mlflow        │  │                     │  │
│  │ • redis         │  │ • postgres-     │  └─────────────────────┘  │
│  │ • statsd        │  │   mlflow_auth   │                            │
│  │ • postgres-     │  └─────────────────┘  ┌─────────────────────┐  │
│  │   airflow       │                       │ ns: apps            │  │
│  └─────────────────┘                       │ • api-predict-mme   │  │
│                                            │ • frontend-mme      │  │
│  ┌─────────────────────────────────────────┴─────────────────────┴┐ │
│  │ ns: observability      │  ns: argocd                            │ │
│  │ • Prometheus           │  • argo-cd-server                      │ │
│  │ • Grafana              │  • argo-cd-controller                  │ │
│  │ • Alertmanager         │  • argo-cd-repo-server                 │ │
│  │ • Loki                 │                                         │ │
│  │ • Tempo                │                                         │ │
│  │ • Pushgateway          │                                         │ │
│  └────────────────────────┴─────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────┘
```

NodePorts expuestos al host:

| Servicio | Puerto | URL local |
|---|---:|---|
| airflow webserver | 30080 | http://node-ip:30080 |
| api-predict-mme | 30601 | http://node-ip:30601 |
| frontend-mme | 30602 | http://node-ip:30602 |
| mlflow tracking | 30500 | http://node-ip:30500 |
| minio API | 30900 | http://node-ip:30900 |
| minio console | 30901 | http://node-ip:30901 |
| jupyterlab | 30888 | http://node-ip:30888 |
| Grafana (addon) | 3000 | port-forward |
| ArgoCD (addon) | 8080 | port-forward |

---

## 2. Vista de componentes

### 2.1 Capa de datos (`ns: data` + `ns: airflow`)

- **MinIO** — object store S3-compatible. Bucket `mlflows3` para artifacts MLflow + buckets internos para parquets bronze/silver/gold (cuando se migren del filesystem actual a S3).
- **postgres-airflow** — metadata Airflow (DAG runs, task instances, connections, variables).
- **postgres-mlflow** — backend tracking + registry MLflow + DB auxiliar `mlflow_auth`.

Todos con PVC `microk8s-hostpath`. Backup: `microk8s kubectl cp` o `pg_dump` periódico (no automatizado).

### 2.2 Capa de orquestación (`ns: airflow`)

Apache Airflow 2.10.5 con `CeleryExecutor`:
- **scheduler** + **triggerer**: dispara DAGs y resuelve dependencias.
- **worker × 2**: ejecuta tareas Celery con Redis broker.
- **webserver**: UI en NodePort 30080.
- **statsd**: emite métricas a Prometheus.
- **gitSync sidecar**: clona este repo cada 60s, expone DAGs vía path `code/proyecto_01/airflow/dags_mme`.

DAGs activos:
- `1-mme_etl_medallion`: bronze → silver → gold (DuckDB queries).
- `2-mme_train_and_promote`: train + drift check + validate + promote @champion.

### 2.3 Capa de modelos (`ns: mlflow`)

MLflow 3.3.2 (chart bitnami):
- Backend: postgres-mlflow.
- Artifact root: s3://mlflows3 (MinIO).
- Registry: experimento `mme_vulnerability_v1`, modelo `mme_c3` con alias `@champion`.
- Auth interno auto-generado (admin user en Secret `mlflow-tracking`).

### 2.4 Capa de serving (`ns: apps`)

- **api-predict-mme**: FastAPI. Carga champion desde MLflow al startup. Endpoints `/predict/municipio`, `/predict/batch`, `/predict/ranking?departamento=`. Bootstrap CI residual al 90%. HPA 1-4 réplicas. NodePort 30601.
- **frontend-mme**: Next.js 14. Server Actions consumen api-predict-mme via DNS interno (`api-predict-mme.apps:8000`). Mapa coroplético + ranking + drill-down muni. NodePort 30602 + Ingress `mme.localhost`.
- **jupyterlab** (opcional): notebooks reproducibles con paquete MME montado read-only.

### 2.5 Capa de observabilidad (`ns: observability`)

`microk8s enable observability` despliega kube-prometheus-stack + Loki + Tempo:
- **Prometheus** scrapea: pods con annotations `prometheus.io/scrape=true`, ServiceMonitor CRDs (postgres × 2, minio, airflow, mlflow), kube-state-metrics.
- **Grafana** carga 3 dashboards MME (ConfigMaps con label `grafana_dashboard=1`).
- **Alertmanager** evalúa 9 alertas MME (PrometheusRule `mme-rules`).
- **Loki** indexa logs de pods.
- **Tempo** trazas distribuidas (no usado actualmente, disponible para futuro).

### 2.6 Capa de GitOps (`ns: argocd`)

ArgoCD reconcilia el cluster contra el repo `git@github.com:ftuga/Vigilancia-Obst-trica-Municipal`:
- **Application root** (`mme-root`) descubre las 7 apps hijas en `k8s/argo-cd/apps/`.
- Cada app hija sincroniza un chart Helm o un set de manifests propios.
- Sync policy automated por tier (ver `k8s/argo-cd/README.md`).

---

## 3. Flujo de datos (data flow)

```
Fuentes públicas (SIVIGILA, DANE, MinSalud REPS, BDUA)
        │
        │  (descargas manuales o scrapes scriptados)
        ▼
┌─────────────────────────────────────┐
│ Airflow DAG 1: mme_etl_medallion    │
│                                     │
│  • bronze   parquets crudos / fuente│
│  • silver   tipado + DIVIPOLA       │
│  • gold     panel_muni_semestre     │
│             panel_muni_semana       │
└─────────────────────────────────────┘
        │  (writes parquets)
        ▼
   MinIO bucket mlflows3 (artifacts)
        │
        ▼
┌─────────────────────────────────────┐
│ Airflow DAG 2: train + promote      │
│                                     │
│  1. check_drift   PSI + KS vs       │
│                   baseline @champion│
│  2. train_c3      LGBM Poisson +    │
│                   Optuna 50 trials  │
│  3. validate      5 gates           │
│  4. promote       @champion alias   │
└─────────────────────────────────────┘
        │  (logs run + artifacts)
        ▼
   MLflow (postgres + s3://mlflows3)
        │
        ▼
┌─────────────────────────────────────┐
│ api-predict-mme                     │
│                                     │
│  startup → load @champion           │
│  POST /predict/municipio            │
│   → bootstrap CI residual           │
│   → response con ci_low/high/tier   │
└─────────────────────────────────────┘
        │
        ▼
   frontend-mme renderiza
   /mme (mapa) + /mme/explorar (tabla)
   + /mme/municipio/[cod] (drill-down)
```

---

## 4. Flujo CI/CD

```
[Dev push a main del repo nuevo]
   │
   ▼
┌──────────────────────────────────────────────────────────────────┐
│ GHA build-and-push.yml                                           │
│  Trigger: push paths code/** o el workflow                       │
│  Matrix: api-predict-mme, frontend-mme, airflow, mlflow,         │
│          jupyterlab                                              │
│  Build: Docker buildx multi-arch (amd64+arm64 donde aplica)      │
│  Tag: YYYYMMDD-{short-sha} en main                               │
│  Push: luisfrontuso10/mme-<svc>:<tag> + :latest                  │
└──────────────────────────────────────────────────────────────────┘
   │
   ▼
[Imágenes en Docker Hub luisfrontuso10/mme-*]
   │
   ▼
┌──────────────────────────────────────────────────────────────────┐
│ GHA bump-image-tags.yml (depende del anterior con success)       │
│                                                                  │
│  sed -i en k8s/apps/{api-predict-mme,frontend-mme}/              │
│            deployment.yaml: image: ...:<NUEVO_TAG>               │
│  git commit "chore(k8s): bump image tags to <date>-<sha>"        │
│  git push origin main                                            │
└──────────────────────────────────────────────────────────────────┘
   │
   ▼
[main del repo: deployment.yaml con tag nuevo]
   │
   ▼
┌──────────────────────────────────────────────────────────────────┐
│ ArgoCD pollea cada 3 min                                         │
│  Detecta diff k8s/apps/<svc>/deployment.yaml                     │
│  Sync automated: kubectl apply                                   │
│  K8s rolling update con la imagen nueva                          │
└──────────────────────────────────────────────────────────────────┘
   │
   ▼
[Pod nuevo running, pod viejo terminated]
```

Las imágenes de Airflow y MLflow custom (`mme-airflow`, `mme-mlflow`) se buildean igual pero el bump al chart es manual (editar `k8s/infra/<chart>-values.yaml` con `defaultAirflowRepository` o `image.repository`).

---

## 5. Decisiones arquitectónicas

### 5.1 MicroK8s vs k3d / GKE

MicroK8s sobre WSL2 single-node. Razones:
- Camino directo a multi-host con `microk8s join` (mismo cluster en VPS Ubuntu).
- Add-ons one-liner (`enable observability argocd metallb registry`).
- Compatible con cualquier Ubuntu 20.04+ sin tooling adicional.

Trade-off: snap requiere systemd, lo cual en WSL2 es opt-in.

### 5.2 Helm para charts upstream + manifests propios para apps

- **Charts upstream**: postgres × 2, minio, airflow, mlflow. Razón: charts maduros con probes, recursos, secrets y métricas estandarizados; reescribirlos sería re-inventar la rueda.
- **Manifests propios**: api_predict_mme, frontend_mme, jupyterlab. Razón: apps custom del proyecto, manifests simples (Deployment + Service + HPA + Ingress).

### 5.3 No `kompose convert` desde compose

Kompose genera manifests pobres (sin probes, sin PVCs, sin HPAs, mezcla ConfigMaps y Secrets). Migración manual con Helm + manifests escritos da mucha mayor calidad.

### 5.4 Hostnames cortos (`<svc>.<ns>`) en lugar de FQDN

En entornos WSL2 con red corporativa, el host puede inyectar un search domain externo con wildcard que, combinado con `ndots:5` (default K8s), hace que FQDNs `<svc>.<ns>.svc.cluster.local` resuelvan a IPs públicas en lugar del cluster. Hostnames cortos `<svc>.<ns>` evitan el problema sin cambiar `dnsConfig` del cluster.

### 5.5 Resources requests + limits obligatorios

Single-node con RAM limitada — sin limits un OOM tira el nodo entero. Política de 4 tiers documentada en `k8s/README.md` § "Cuotas de recursos".

### 5.6 Bitnami legacy registry (`bitnamilegacy/...`)

Desde 2025-08-28, Bitnami movió tags free a `bitnamilegacy/`. Charts upgradados aceptan `image.repository: bitnamilegacy/<image>` + `global.security.allowInsecureImages: true`.

### 5.7 Multi-source ArgoCD para Helm charts

Charts upstream sin valores inline en `Application.spec.helm.values`. Patrón:
```yaml
sources:
  - chart: <chart>           ← chart repo upstream
    helm:
      valueFiles:
        - $values/k8s/infra/<chart>-values.yaml
  - repoURL: <este-repo>     ← values.yaml viven aquí
    ref: values
```

Single source of truth para values (este repo) sin acoplar al chart repo.

---

## 6. Limitaciones y deuda

| Item | Bloqueante | Tracking |
|---|---|---|
| **Imagen custom airflow con `pip install -e code/`** para que DAGs MME ejecuten (no solo se carguen) | Sí — DAG trigger falla con `ImportError: from mme.*` | Manual `helm upgrade` post-B9, o GHA workflow separado |
| Auth Airflow / MLflow gestionados out-of-band (admin password creada manualmente o por Job post-install) | No — funcional pero ruidoso para ArgoCD | `ignoreDifferences` en Secrets |
| `bitnami/mlflow` chart fuerza auth aunque `auth.enabled: false` | No — se accede vía API con basic auth | Tracking issue chart |
| Bump de imagen custom de charts (airflow, mlflow) no automatizado | No — manual editing de values | TODO workflow específico |
| Backup de PVCs no automatizado | Sí en producción real | `velero` o cronjob `pg_dump` |

---

## 7. Referencias

- `code/docs/mme/runbook.md` — despliegue desde cero
- `code/docs/mme/methodology.md` — decisiones del modelo
- `code/docs/mme/limitations.md` — limitaciones del modelo
- `k8s/README.md` — layout, cuotas de recursos, generación de credenciales
- `k8s/argo-cd/README.md` — App-of-Apps + sync policies
- `.github/workflows/build-and-push.yml` — CI build matrix
- `.github/workflows/bump-image-tags.yml` — CD bump tags + commit
