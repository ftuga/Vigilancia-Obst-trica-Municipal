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

```bash
# 1. Cluster + addons
bash k8s/scripts/00-setup-microk8s.sh

# 2. Configurar variables
cp k8s/.env.example k8s/.env
$EDITOR k8s/.env

# 3. Crear namespaces
microk8s kubectl apply -f k8s/infra/00-namespaces.yaml

# 4. Generar secrets y configmaps
bash k8s/scripts/01-bootstrap-secrets.sh
bash k8s/scripts/02-render-env-configmap.sh
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

## Replicación a otro host

Ver `code/docs/mme/runbook.md` §10 (multi-host con `microk8s join`).
