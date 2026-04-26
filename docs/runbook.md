# Runbook de deployment

Pasos para levantar el stack completo en un nodo microk8s nuevo.

## Pre-requisitos

- Ubuntu 22.04+ (o WSL2).
- microk8s 1.28+ con addons: `dns`, `hostpath-storage`, `metallb`, `metrics-server`, `ingress`.
- `git`, `bash`, `kubectl` (alias del microk8s).
- Acceso a `docker.io/luisfrontuso10/*` (público) o credenciales propias.

## 1. Clonar repo y completar `.env`

```bash
git clone https://github.com/ftuga/Vigilancia-Obst-trica-Municipal.git
cd Vigilancia-Obst-trica-Municipal
cp k8s/.env.example k8s/.env
# Editar k8s/.env: passwords, MICROK8S_NODE_IP, etc.
```

## 2. Bootstrap

```bash
# Namespaces.
microk8s kubectl apply -f k8s/infra/00-namespaces.yaml

# Secrets en cada namespace desde .env.
bash k8s/scripts/01-bootstrap-secrets.sh

# ConfigMap mme-env replicado en 4 namespaces.
bash k8s/scripts/02-render-env-configmap.sh

# Stack observabilidad (kube-prom-stack + Loki + Tempo via Helm).
bash k8s/scripts/03-bootstrap-observability.sh
```

## 3. ArgoCD app-of-apps

```bash
# Instalar ArgoCD.
microk8s helm repo add argo https://argoproj.github.io/argo-helm
microk8s helm install argocd argo/argo-cd -n argocd --create-namespace

# Aplicar la "raíz": mme-root descubre todas las Argo Apps en k8s/argo-cd/apps/.
microk8s kubectl apply -f k8s/argo-cd/repos.yaml
microk8s kubectl apply -f k8s/argo-cd/app-of-apps.yaml
```

ArgoCD reconcilia automáticamente: postgres x2 → MinIO → MLflow → Airflow → API → frontend → Jupyter → pgAdmin → Locust.

## 4. Patch DNS (microk8s + WSL2)

Si tu host tiene search domain corporativo, los pods heredan `ndots:5` y se rompen lookups externos. Aplicar fix runtime:

```bash
bash k8s/scripts/apply-airflow-dns-patch.sh
```

(El chart Apache Airflow 1.16.0 no expone `dnsConfig` en values.)

## 5. Validar

```bash
bash k8s/scripts/show-urls.sh
```

Imprime URLs + credenciales de ArgoCD, Airflow, MLflow, MinIO, API, Frontend, Jupyter, pgAdmin, Grafana, Prometheus, Locust.

## 6. Disparar pipeline ML

```bash
# Webserver Airflow → unpause + trigger DAG 1 (ingesta).
SCHED=$(microk8s kubectl get pods -n airflow -l component=scheduler -o jsonpath='{.items[0].metadata.name}')
microk8s kubectl exec -n airflow "$SCHED" -c scheduler -- airflow dags unpause 1-mme_etl_medallion
microk8s kubectl exec -n airflow "$SCHED" -c scheduler -- airflow dags trigger 1-mme_etl_medallion

# Esperar success, después DAG 2 (train + promote).
microk8s kubectl exec -n airflow "$SCHED" -c scheduler -- airflow dags unpause 2-mme_train_and_promote
microk8s kubectl exec -n airflow "$SCHED" -c scheduler -- airflow dags trigger 2-mme_train_and_promote
```

Cuando el DAG 2 termine, validar API:

```bash
API_POD=$(microk8s kubectl get pods -n apps -l app.kubernetes.io/name=api-predict-mme -o jsonpath='{.items[0].metadata.name}')
microk8s kubectl exec -n apps "$API_POD" -- python -c \
  'import urllib.request,json; print(json.dumps(json.loads(urllib.request.urlopen("http://localhost:8001/readyz").read()),indent=2))'
```

Status `ok` confirma champion cargado y panel disponible.

## Reset full

```bash
# DAG 0: borra PVC + MinIO + MLflow Registry, idempotente.
microk8s kubectl exec -n airflow "$SCHED" -c scheduler -- airflow variables set confirm_reset YES
microk8s kubectl exec -n airflow "$SCHED" -c scheduler -- airflow dags trigger 0-mme_reset_environment
```

## Troubleshooting común

| Síntoma | Causa | Fix |
|---|---|---|
| Airflow workers en CrashLoopBackOff | bug Celery + Airflow 2.10.5 (`pidfile=None`) | bypass: `workers.args` invoca `celery worker` directo |
| DAG 1 ingesta falla con `SSLError self-signed` | DNS hijack via search domain corp | aplicar `apply-airflow-dns-patch.sh` (`ndots:1`) |
| `/readyz` degraded `feature_set no encontrado` | API sin acceso al PVC | verificar mount `/opt/airflow/data/mme` y env `MME_REPORTS_ROOT` |
| pgAdmin rechaza email `@*.local` | `email_validator` bloquea TLDs no-deliverable | usar dominio `.dev` o `.com` |
