# k8s/

Manifests, Helm values, scripts y ArgoCD apps para desplegar el stack en MicroK8s.

---

## Layout

```
k8s/
├── .env.example              Variables parametrizadas (NodePorts, hosts, passwords)
├── infra/
│   ├── 00-namespaces.yaml    4 namespaces: airflow, mlflow, data, apps
│   └── *-values.yaml         Helm values por chart upstream (B4-B5)
├── apps/                     Manifests propios (B7)
│   ├── api-predict-mme/
│   ├── frontend-mme/
│   ├── mlflow/
│   └── jupyterlab/
├── argo-cd/
│   ├── app-of-apps.yaml      Application root (B11)
│   └── apps/                 Applications hijas, una por servicio
└── scripts/
    ├── 00-setup-microk8s.sh        Bootstrap del cluster + addons
    ├── 01-bootstrap-secrets.sh     Genera Secrets desde .env (en cada namespace)
    ├── 02-render-env-configmap.sh  Genera ConfigMap base mme-env desde .env
    └── teardown.sh                 Borra workloads MME (no toca el cluster)
```

---

## Setup desde cero

### Express (1 comando, recomendado)

```bash
cp k8s/.env.example k8s/.env
bash k8s/scripts/deploy.sh
```

`deploy.sh` instala MicroK8s + addons si faltan, rota placeholders `changeme-*` del `.env` con creds reales, despliega los 5 charts + manifests propios + observability + ArgoCD app-of-apps, e imprime URLs y credenciales al final.

Si MicroK8s acaba de ser instalado, el script termina pidiendo reabrir terminal. Volvé a correrlo.

### Manual paso a paso

```bash
# 1. Cluster + addons
bash k8s/scripts/00-setup-microk8s.sh

# 2. Configurar variables
cp k8s/.env.example k8s/.env
```

### 2.0 Atajo: rotar todas las creds en una pasada

```bash
bash k8s/scripts/rotate-credentials.sh   # reemplaza changeme-* en k8s/.env
```

### 2.1 Generar credenciales (manualmente)

Los placeholders `changeme-*` en `.env` deben reemplazarse antes de aplicar Secrets. Comandos exactos:

```bash
# Postgres x2 y MinIO root y Airflow admin y Redis (24 bytes hex = 48 chars)
openssl rand -hex 24   # → POSTGRES_AIRFLOW_PASSWORD
openssl rand -hex 24   # → POSTGRES_MLFLOW_PASSWORD
openssl rand -hex 24   # → MINIO_ROOT_PASSWORD
openssl rand -hex 24   # → AIRFLOW_ADMIN_PASSWORD
openssl rand -hex 24   # → REDIS_PASSWORD

# Airflow secret (32 bytes hex = 64 chars, requerido por gunicorn)
openssl rand -hex 32   # → AIRFLOW_SECRET_KEY

# Airflow Fernet key (44 chars base64, formato fijo)
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# → AIRFLOW_FERNET_KEY
```

Editar `k8s/.env` y reemplazar cada `changeme-*` con los valores generados.

Atajo en una pasada con `python3` (no requiere entrada manual):

```bash
python3 - <<'PY'
import secrets
from cryptography.fernet import Fernet

vals = {
    'POSTGRES_AIRFLOW_PASSWORD': secrets.token_hex(24),
    'POSTGRES_MLFLOW_PASSWORD':  secrets.token_hex(24),
    'MINIO_ROOT_PASSWORD':       secrets.token_hex(24),
    'AIRFLOW_FERNET_KEY':        Fernet.generate_key().decode(),
    'AIRFLOW_SECRET_KEY':        secrets.token_hex(32),
    'AIRFLOW_ADMIN_PASSWORD':    secrets.token_hex(24),
    'REDIS_PASSWORD':            secrets.token_hex(24),
}
src = open('k8s/.env').read()
placeholders = {
    'POSTGRES_AIRFLOW_PASSWORD':'changeme-airflow',
    'POSTGRES_MLFLOW_PASSWORD':'changeme-mlflow',
    'MINIO_ROOT_PASSWORD':'changeme-minio-root',
    'AIRFLOW_FERNET_KEY':'changeme-fernet-44chars-base64',
    'AIRFLOW_SECRET_KEY':'changeme-secret-64hex',
    'AIRFLOW_ADMIN_PASSWORD':'changeme-admin',
    'REDIS_PASSWORD':'changeme-redis',
}
for k, v in vals.items():
    src = src.replace(f'{k}={placeholders[k]}', f'{k}={v}')
open('k8s/.env','w').write(src)
print('rotated:', sorted(vals.keys()))
PY
```

Backup recomendado: copiar `k8s/.env` a un gestor de secretos personal (1Password, Bitwarden). Si se pierde, los datos persistidos en Postgres/MinIO quedan inaccesibles salvo migración.

### 2.2 Aplicar al cluster

```bash
# 3. Crear namespaces
microk8s kubectl apply -f k8s/infra/00-namespaces.yaml

# 4. Generar Secrets y ConfigMap base desde .env
bash k8s/scripts/01-bootstrap-secrets.sh
bash k8s/scripts/02-render-env-configmap.sh
```

### 2.3 Recuperar credenciales después

```bash
# Desde el .env local
grep '^AIRFLOW_ADMIN_PASSWORD=' k8s/.env

# O desde el cluster (Secret K8s base64-encoded)
microk8s kubectl get secret airflow-runtime -n airflow \
  -o jsonpath='{.data.admin-password}' | base64 -d
```

Después de esto, los siguientes bloques (B4-B11) instalan los servicios vía Helm + ArgoCD.

---

## Secrets vs ConfigMaps

| Tipo | Contiene | Aplicar con |
|---|---|---|
| **Secret** | Passwords, API keys, Fernet, SSH keys | `01-bootstrap-secrets.sh` |
| **ConfigMap** `mme-env` | NodePorts, hosts internos, URLs públicas, nombres de buckets/experimentos | `02-render-env-configmap.sh` |

Ningún manifest del repo tiene credenciales hardcodeadas. Todo viene de `.env` (gitignored).

---

## Acceso a las UIs

```bash
bash k8s/scripts/show-urls.sh
```

Imprime las URLs con la IP del nodo y los NodePorts de `.env`. En WSL2 detecta la IP de `eth0` (cambia entre reboots, re-ejecutar). En Linux nativo / VPS usa `MICROK8S_NODE_IP` del `.env`.

Servicios expuestos:

| Servicio | NodePort default | UI |
|---|---:|---|
| ArgoCD | 30443 (https) | login `admin` + secret inicial |
| Airflow webserver | 30080 | login admin + Secret `airflow-runtime` |
| MLflow tracking | 30500 | login admin + Secret `mlflow-tracking` |
| api-predict-mme | 30601 | OpenAPI en `/docs` |
| frontend-mme | 30602 | mapa coroplético + ranking |
| MinIO console | 30901 | login con `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD` |
| MinIO API (S3) | 30900 | endpoint para clientes mc/aws |
| JupyterLab | 30888 | sin auth (solo dev local) |

### Kubernetes Dashboard

```bash
bash k8s/scripts/dashboard.sh
```

Despliega y configura el dashboard de microk8s. Idempotente: re-ejecutable cuantas veces quieras, no rompe estado existente.

Lo que hace:

1. Habilita el addon `dashboard` si está disabled.
2. Patchea el Service `kubernetes-dashboard` a `NodePort 30444`.
3. Crea el ServiceAccount `dashboard-admin` (kube-system) con `ClusterRoleBinding cluster-admin`. **Esto es necesario:** el secret default `microk8s-dashboard-token` apunta al SA `default` sin permisos y devuelve `401 Invalid credentials` al loguear.
4. Crea el Secret persistente `dashboard-admin-token` (tipo `kubernetes.io/service-account-token`). El JWT efímero de `kubectl create token` puede no ser aceptado por Dashboard v2.7.0; el secret persistente sí.
5. Detecta la IP del nodo (`eth0` en WSL2 o `MICROK8S_NODE_IP` en Linux nativo) y arma la URL clickeable.
6. **Copia el token al portapapeles del sistema** automáticamente:
   - WSL2 → `clip.exe` (portapapeles de Windows).
   - Linux Wayland → `wl-copy`.
   - Linux X11 → `xclip`.
   - Si no hay ninguno → imprime el token en pantalla para triple-click + copy.

Output incluye la longitud del token (sirve de checksum: si pegás menos caracteres, perdiste algo en el copy).

Tras ejecutar el script:

1. Abrí la URL `https://<NODE_IP>:30444`. Cert self-signed → "Avanzado → Continuar".
2. Elegí **Token**.
3. `Ctrl+V` en el campo (o pegá manualmente).

Si sale `401 Invalid credentials`:

- Hard-refresh del login: `Ctrl+Shift+R` (limpia sesión cacheada del browser).
- O abrí la URL en **modo incógnito**.
- Verificá que pegaste exactamente `N` caracteres (lo imprime el script).

Variables opcionales:

- `DASHBOARD_NODEPORT` (default `30444`) — cambiar si choca con otro Service.
- `KUBECTL` (default `microk8s kubectl`).

> **Seguridad.** El SA `dashboard-admin` tiene `cluster-admin`. Solo apto para entornos locales (WSL/dev). En producción usar un SA con permisos restringidos por namespace.

## Cuotas de recursos

Política: todo container tiene `requests` y `limits`. Sin excepciones (incluye sidecars, exporters, statsd, gitSync, post-install jobs).

Tiers base:

| Tier | requests.mem | limits.mem | requests.cpu | limits.cpu | Aplica a |
|---|---|---|---|---|---|
| `minimal` | 64Mi | 256Mi | 50m | 500m | sidecars, exporters, gitSync, statsd, post-jobs |
| `small` | 128Mi | 512Mi | 100m | 1000m | redis, dagProcessor |
| `medium` | 256Mi | 1Gi | 100m | 1000m | postgres, triggerer |
| `large` | 512Mi | 2Gi | 200m | 2000m | webserver, scheduler, workers, mlflow, api_predict_mme, frontend_mme |

Suma estimada (1 réplica de cada componente, 2 workers Airflow):

| Categoría | Mem requests | Mem limits | CPU requests | CPU limits |
|---|---:|---:|---:|---:|
| postgres × 2 (medium + metrics minimal × 2) | ~640Mi | ~2.5Gi | ~300m | ~3000m |
| minio (large + 2 jobs minimal) | ~640Mi | ~2.5Gi | ~300m | ~3000m |
| airflow (web large + sched large + 2 workers + triggerer + redis + statsd + gitSync) | ~3Gi | ~12Gi | ~1.4 | ~13 |
| mlflow (large) | ~512Mi | ~2Gi | ~200m | ~2000m |
| apps (api + frontend + jupyter, large × 3) | ~1.5Gi | ~6Gi | ~600m | ~6000m |
| **Total mínimo del stack MME** | **~6.3Gi** | ~25Gi | ~2.8 cores | ~27 cores |
| Observability addon (kube-prom-stack + Loki + Tempo) | ~2Gi | ~6Gi | ~500m | ~5 |
| ArgoCD addon | ~512Mi | ~1Gi | ~200m | ~2 |

Verificar capacidad del nodo:

```bash
microk8s kubectl describe node $(microk8s kubectl get nodes -o name | head -1) | grep -A 5 "Allocatable"
```

Regla: requests totales ≤ 80% allocatable. Limits pueden sumar más (no se reservan).

---

## Desmontar el stack

```bash
bash k8s/scripts/down.sh --apps      # default: borra apps + airflow + mlflow, conserva PVCs
bash k8s/scripts/down.sh --all       # + postgres × 2 + minio + PVCs (datos perdidos)
bash k8s/scripts/down.sh --purge     # + microk8s reset (DESTRUYE el cluster entero)
```

Confirma con `yes` antes de cada destructivo.

## Replicación a otro host

Ver `code/docs/mme/runbook.md` §10 (multi-host con `microk8s join`).
