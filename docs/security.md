# Modelo de seguridad

Controles de seguridad aplicados al stack. Alcance: gestión de secrets, autenticación entre servicios, exposición de red, RBAC del cluster, integridad del pipeline CI/CD y cumplimiento Habeas Data.

---

## 1. Gestión de secrets

### 1.1 Fuente de verdad

Todos los secrets se generan a partir de `k8s/.env` (gitignored). El template `k8s/.env.example` documenta las variables requeridas con valores placeholder.

```bash
# Bootstrap inicial — crea secrets en cada namespace desde .env
bash k8s/scripts/01-bootstrap-secrets.sh
```

El script lee `.env` y crea Secrets nativos de K8s (`type: Opaque` o `type: kubernetes.io/dockerconfigjson` para registry pulls). **No usa SealedSecrets ni External Secrets Operator** — trade-off intencional: stack académico de un solo dueño, sin requerimiento de GitOps puro para secrets.

### 1.2 Inventario de secrets

| Secret | Namespace | Contenido | Consumido por |
|---|---|---|---|
| `mlflow-auth` | `mlflow`, `apps`, `airflow` | `MLFLOW_TRACKING_USERNAME`, `MLFLOW_TRACKING_PASSWORD` | mlflow-tracking, api-predict-mme, airflow workers |
| `mlflow-s3` | `mlflow`, `airflow`, `apps` | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `MLFLOW_S3_ENDPOINT_URL` | mlflow, workers, api |
| `postgres-airflow` | `airflow` | `postgres-password`, `replication-password` | postgres-airflow, scheduler, workers |
| `postgres-mlflow` | `mlflow` | `postgres-password` | postgres-mlflow, mlflow-tracking |
| `minio-creds` | `data`, `mlflow`, `airflow` | `root-user`, `root-password` | minio, consumers |
| `airflow-fernet-key` | `airflow` | `fernet-key` (32 bytes b64) | scheduler, workers (cifra connections + variables) |
| `airflow-webserver-secret` | `airflow` | `webserver-secret-key` | webserver (sesiones flask) |
| `pgadmin-creds` | `apps` | `email`, `password` | pgadmin |
| `jupyter-creds` | `apps` | `password` (fallback, hoy desactivado) | jupyterlab |

### 1.3 Replicación entre namespaces

`mlflow-auth` y `mlflow-s3` se replican manualmente a 3 namespaces (`mlflow`, `apps`, `airflow`) porque K8s Secrets son namespace-scoped. Patrón:

```bash
microk8s kubectl get secret mlflow-auth -n mlflow -o yaml \
  | sed 's/namespace: mlflow/namespace: apps/' \
  | microk8s kubectl apply -f -
```

Idempotente. El script `01-bootstrap-secrets.sh` ya lo hace.

### 1.4 Rotación

| Secret | Procedimiento | Downtime |
|---|---|---|
| `mlflow-auth` | actualizar `.env` → re-run `01-bootstrap-secrets.sh` → reset de mlflow + restart de api/workers | ~30s API, ~2min DAG en cola |
| `postgres-*` | rolling update con flag `--reset-passwords` del chart bitnami | ~1min |
| `minio-creds` | re-bootstrap MinIO + actualizar consumidores | ~3min |
| `airflow-fernet-key` | **NO rotar sin re-encriptar connections existentes** (riesgo: pérdida de credenciales internas) |

### 1.5 ArgoCD `ignoreDifferences` para Secrets auto-generados

Charts bitnami auto-generan passwords al instalar si no se proveen explícitos. ArgoCD los detecta como diff cada sync. Patrón aplicado:

```yaml
ignoreDifferences:
  - group: ""
    kind: Secret
    name: postgres-airflow
    jsonPointers:
      - /data/postgres-password
      - /data/replication-password
```

---

## 2. Autenticación entre servicios

### 2.1 Matriz de auth

| Origen → Destino | Mecanismo | Credencial |
|---|---|---|
| api-predict-mme → MLflow tracking | HTTP Basic Auth | `mlflow-auth` Secret (envFrom) |
| api-predict-mme → MinIO (load model artifacts) | AWS SigV4 | `mlflow-s3` Secret |
| airflow workers → MLflow tracking | HTTP Basic Auth | `mlflow-auth` |
| airflow workers → MinIO | AWS SigV4 | `mlflow-s3` |
| mlflow-tracking → postgres-mlflow | password | `postgres-mlflow` Secret |
| mlflow-tracking → MinIO | AWS SigV4 | `mlflow-s3` |
| frontend-mme → api-predict-mme | sin auth (red interna cluster) | — |
| webserver → postgres-airflow | password + Fernet-encrypted connections | `postgres-airflow` + `airflow-fernet-key` |

### 2.2 Postura de auth interna

**No mTLS entre servicios.** Justificación:

- Tráfico interno cluster microk8s, sin egress al internet.
- NetworkPolicies (§3) limitan qué pods pueden hablar con qué.
- Auth a nivel aplicación (HTTP Basic, AWS SigV4) protege endpoints específicos.

Re-evaluable si se llega a multi-tenant o se expone API a redes no confiables.

---

## 3. Red y exposición

### 3.1 Topología

```
[Internet / LAN]
       │
       ▼
[NodePort 300xx]  ←── única superficie expuesta al host/LAN
       │
       ▼
[Service ClusterIP]
       │
       ▼
[Pod en namespace]  ←── tráfico Pod-to-Pod via DNS interno cluster
```

### 3.2 NodePorts expuestos

| Servicio | Puerto | Auth |
|---|---:|---|
| Airflow webserver | 30080 | Basic auth (`airflow-users`) |
| MLflow tracking | 30500 | Basic auth (`mlflow-auth`) |
| MinIO API | 30900 | AWS SigV4 |
| MinIO console | 30901 | password (`minio-creds`) |
| api-predict-mme | 30601 | sin auth (asumido red privada) |
| frontend-mme | 30602 | sin auth |
| JupyterLab | 30888 | **sin token** (decisión: red privada cluster) |
| pgAdmin | 30050 | password (`pgadmin-creds`) |
| Grafana | 30030 | admin/`prom-operator` (default kube-prom-stack) |
| Prometheus | 30090 | sin auth |
| Locust | 30089 | sin auth |

**Disclaimer**: este modelo asume que el nodo está en LAN privada o WSL2 host (`localhost`). Para exposición pública obligatorio agregar:

- TLS via cert-manager (Let's Encrypt staging primero, prod después).
- OAuth2 Proxy delante de UIs (Grafana, Prometheus, Airflow, ArgoCD).
- IP allowlist en firewall del nodo.

### 3.3 NetworkPolicies (deuda)

**Estado**: no aplicadas hoy. Default microk8s permite tráfico Pod-to-Pod entre cualquier namespace.

**Plan**: aplicar NetworkPolicies tier 1 a corto plazo:

```yaml
# ejemplo: solo apps puede llamar a mlflow
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: mlflow-allow-apps-airflow
  namespace: mlflow
spec:
  podSelector: { matchLabels: { app: mlflow-tracking } }
  ingress:
    - from:
        - namespaceSelector: { matchLabels: { name: apps } }
        - namespaceSelector: { matchLabels: { name: airflow } }
```

Tracking en risk-map del proyecto. Bloqueante: `cni: calico` en microk8s (default está en `cni: flannel` que tiene soporte limitado de NetworkPolicy).

---

## 4. RBAC del cluster

### 4.1 ServiceAccounts por componente

Cada Deployment usa su propio SA con permisos mínimos:

| ServiceAccount | Namespace | Permisos relevantes |
|---|---|---|
| `argocd-application-controller` | `argocd` | cluster-admin (ArgoCD necesita aplicar manifests en cualquier namespace) |
| `airflow-worker` | `airflow` | `get/list/watch pods` (para Celery health) |
| `airflow-scheduler` | `airflow` | `get/list/watch pods` + `create/delete jobs` |
| `default` (api, frontend, jupyter) | `apps` | sin permisos extras (no usan K8s API) |

### 4.2 ArgoCD admin

Credencial inicial:

```bash
microk8s kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 -d
```

**Acción requerida tras primer login**: cambiar password admin via UI o CLI argocd, eliminar el secret inicial:

```bash
microk8s kubectl -n argocd delete secret argocd-initial-admin-secret
```

### 4.3 Acceso al cluster

| Quién | Cómo | Qué puede |
|---|---|---|
| Owner del nodo (root o `microk8s` group) | `microk8s kubectl` | full cluster-admin |
| ArgoCD application-controller | SA con CRB cluster-admin | aplicar manifests, pero solo lo que está en repo git |
| CI (GitHub Actions) | **no toca el cluster** | solo build + push imágenes y commit a main |

ArgoCD es el único componente que aplica cambios al cluster en operación normal. CI nunca usa `kubectl`.

---

## 5. Pipeline CI/CD

### 5.1 Permisos por workflow

| Workflow | Permisos GHA |
|---|---|
| `build-and-push.yml` | `contents: read` |
| `bump-image-tags.yml` | `contents: write` (commit a main) |
| `docs.yml` | `contents: read`, `pages: write`, `id-token: write` |

Principio: cada workflow recibe el mínimo necesario. Build no necesita write — solo bump.

### 5.2 Secrets en CI

| Secret | Workflow | Rotación |
|---|---|---|
| `DOCKERHUB_USERNAME` | build-and-push | n/a (username) |
| `DOCKERHUB_TOKEN` | build-and-push | PAT con scope read+write+delete; rotar cada 90 días |
| `GITHUB_TOKEN` | bump, docs | auto-provisto, ephemeral por job |

`DOCKERHUB_TOKEN` debe tener scopes mínimos: `read`, `write`, `delete` (para limpiar tags antiguos eventualmente). **Nunca admin scope**.

### 5.3 Image provenance

Imágenes publicadas a Docker Hub `luisfrontuso10/mme-*` con tags inmutables (`YYYYMMDD-{short-sha}`). Tags reproducibles desde el SHA de git: dado un SHA puedo reconstruir la imagen byte-a-byte si los Dockerfiles + base images siguen disponibles.

**Deuda**: firma con cosign + verificación en admisión. No aplicado hoy. Tracking en risk-map.

### 5.4 Build del repo

`Dockerfile`s:

- No corren como `root` en runtime (`USER 1000` o equivalente).
- `apt-get update && apt-get install -y --no-install-recommends ... && rm -rf /var/lib/apt/lists/*` (best practice cache).
- `pip install --no-cache-dir` para reducir imagen.
- `.dockerignore` excluye `.git`, `__pycache__`, `tests`, `.env*`.

---

## 6. Datos sensibles y Habeas Data

### 6.1 Marco regulatorio

- **Ley 1581 de 2012** (Colombia) — Habeas Data: protección de datos personales.
- **Resolución 3280/2018 MinSalud** — Ruta Materno Perinatal: marco operativo.
- **Política PAREMM v5** — usa indicadores agregados, no individuales.

### 6.2 Postura del proyecto

**Todos los datos son agregados municipales**. INS (custodio upstream) ya anonimiza casos individuales antes de publicar SIVIGILA. El proyecto no tiene acceso a datos identificables (HC, nombres, direcciones).

| Capa | Granularidad | Sensibilidad |
|---|---|---|
| Bronze (parquets crudos) | muni × evento × fecha | bajo (público en Socrata) |
| Silver | muni × evento × fecha (deduplicado) | bajo |
| Gold (panel) | **muni × semestre** | nulo (totalmente agregado) |
| Modelo + predicciones | muni × semestre | nulo (no expone individuos) |

### 6.3 Disclaimer obligatorio en UI

El frontend `/mme/municipio/[cod]` muestra un disclaimer permanente:

> Este modelo predice **vulnerabilidad municipal agregada**, no riesgo individual. SHAP de features municipales NO debe interpretarse como factor de riesgo de una mujer concreta (ecological fallacy).

Detalle metodológico: [`code/docs/mme/ml-problem-definition.md` §5](https://github.com/ftuga/Vigilancia-Obst-trica-Municipal/blob/main/code/docs/mme/ml-problem-definition.md).

### 6.4 Logs y trazas

OpenTelemetry traces capturan paths HTTP y duraciones, **no el body** de requests/responses. Loki almacena stdout de pods sin redacción adicional — verificar que los DAGs no logueen casos individuales (auditado: solo se loguean conteos y métricas agregadas).

---

## 7. Backups y disaster recovery

### 7.1 Estado actual

| Componente | Backup | Restore |
|---|---|---|
| postgres-airflow | manual `pg_dump` (no programado) | manual |
| postgres-mlflow | manual `pg_dump` | manual |
| MinIO (artifacts MLflow) | snapshot del PVC del StatefulSet (manual) | restore PVC |
| PVC `mme-data` (medallón) | reproducible desde DAG 1 | re-correr DAG 1 |

**Aceptable porque** el medallón es reproducible desde fuentes públicas + DAGs idempotentes. Pérdida de MLflow registry implicaría re-entrenar (DAG 2), pero el modelo es reproducible (seeds fijos, panel versionado).

### 7.2 Plan deuda

- Cronjob `pg_dump` diario a MinIO (retención 14 días).
- `velero` para snapshots PVC programados.
- Test de restore documentado en runbook.

---

## 8. Auditoría y trazabilidad

| Acción | Trazada en |
|---|---|
| Push a main | git log + GHA logs |
| Cambio de manifest k8s | git log (todo va por commit) |
| Sync de ArgoCD | UI ArgoCD + `microk8s kubectl describe app` |
| Promoción de modelo | MLflow Registry events (`get_model_version_history`) |
| Predicción servida | Tempo trace + Loki log línea |
| Cambio de password Postgres | manual, sin auditoría dedicada (deuda) |

Postura: **git es la fuente de verdad operacional**. Cualquier cambio en producción debe haber pasado por commit + ArgoCD sync. Cambios out-of-band (kubectl manual) son **anti-pattern** y se deben revertir vía git revert.

---

## 9. Checklist de hardening pre-producción real

Si este stack se llevara a producción real (PAREMM, INS, MinSalud) — fuera del alcance de este ejercicio investigativo —, los siguientes son requisitos no-negociables:

- [ ] TLS en todos los NodePorts via cert-manager + Let's Encrypt prod.
- [ ] OAuth2 Proxy delante de UIs (Grafana, Airflow, MLflow, ArgoCD).
- [ ] NetworkPolicies tier 1 aplicadas (cni: calico).
- [ ] Cosign signing + admission verification de imágenes.
- [ ] Rotación automatizada de secrets (External Secrets Operator + Vault o cloud KMS).
- [ ] Velero backup programado de PVCs + Postgres dumps.
- [ ] Pen-test del API y frontend (OWASP API Top 10).
- [ ] Audit log de acciones administrativas (kubernetes audit policy).
- [ ] Runbook de incidentes con escalation paths.
- [ ] DPIA (Data Protection Impact Assessment) bajo Ley 1581 firmada por DPO.

Para el alcance del ejercicio investigativo actual, los controles aplicados son **suficientes y proporcionales** al riesgo (cluster privado, datos públicos agregados, sin PII).
