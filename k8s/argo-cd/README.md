# ArgoCD App-of-Apps

GitOps source para el cluster MicroK8s. ArgoCD pollea este repo y reconcilia
los recursos en el cluster.

## Patrón

`app-of-apps.yaml` es la Application raíz. Apunta a `k8s/argo-cd/apps/` y
desde ahí descubre las Applications hijas que ArgoCD gestiona:

| Application | Tipo | Source | Destino |
|---|---|---|---|
| `postgres-airflow` | Helm chart | bitnami/postgresql 18.6.2 | ns airflow |
| `postgres-mlflow` | Helm chart | bitnami/postgresql 18.6.2 | ns mlflow |
| `minio` | Helm chart | minio/minio 5.4.0 | ns data |
| `airflow` | Helm chart | apache-airflow/airflow 1.16.0 | ns airflow |
| `airflow-pvcs` | Manifests propios | k8s/apps/airflow-pvcs/ | ns airflow |
| `mlflow` | Helm chart | bitnami/mlflow 5.1.17 | ns mlflow |
| `api-predict-mme` | Manifests propios | k8s/apps/api-predict-mme/ | ns apps |
| `frontend-mme` | Manifests propios | k8s/apps/frontend-mme/ | ns apps |
| `jupyterlab` | Manifests propios | k8s/apps/jupyterlab/ | ns apps |
| `pgadmin` | Manifests propios | k8s/apps/pgadmin/ | ns apps |
| `locust` | Manifests propios | k8s/apps/locust/ | ns observability |
| `observability-extras` | Manifests propios | k8s/apps/observability-extras/ | ns observability |

## Sync policies

| App | automated | prune | selfHeal | Razón |
|---|---|---|---|---|
| Apps stateless (api, frontend) | sí | sí | sí | Idempotentes; recrear pods OK |
| Charts stateful (postgres, minio) | sí | **no** | sí | `prune=false` evita borrar PVCs por accidente |
| Charts complejos (airflow, mlflow) | sí | no | **no** | Diferencias post-deploy (admin user, DB inicializadas) son esperadas |

## Multi-source pattern

Cada chart Helm usa la convención multi-source de ArgoCD:

```yaml
sources:
  - repoURL: <chart-repo>
    chart: <chart-name>
    targetRevision: <version>
    helm:
      valueFiles:
        - $values/k8s/infra/<chart>-values.yaml
  - repoURL: https://github.com/ftuga/Vigilancia-Obst-trica-Municipal.git
    targetRevision: main
    ref: values
```

El `ref: values` permite que ArgoCD lea el `values.yaml` desde este repo
(no del repo del chart), manteniendo la fuente de verdad acá.

## Aplicar

Después de tener Secrets + ConfigMaps + DBs auxiliares (mlflow_auth) creados:

```bash
microk8s kubectl apply -f k8s/argo-cd/app-of-apps.yaml
```

ArgoCD detectará la app raíz, creará las Applications hijas, y empezará a
sincronizar. Verificar:

```bash
microk8s kubectl get applications -n argocd
microk8s kubectl get application mme-root -n argocd -o yaml
```

## UI ArgoCD

```bash
microk8s kubectl port-forward -n argocd svc/argo-cd-argocd-server 8080:80 &
# Browser → http://localhost:8080
# Password inicial:
microk8s kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d
```

## Limitaciones conocidas

- **Auth password de Airflow / MLflow**: el admin user se crea fuera de
  ArgoCD (post-install, ver [docs/runbook.md](../../docs/runbook.md) §6).
  ArgoCD ignora diffs en el Secret `airflow-runtime` porque sería ruido
  constante.
- **Imagen tags de api-predict-mme y frontend-mme**: las bumpea el workflow
  GHA `bump-image-tags.yml` después de cada build exitoso. ArgoCD detecta
  el commit en main y sync automated reduce el cambio al cluster.
- **Imagen tag custom de airflow/mlflow**: no se bumpea automáticamente.
  Para activarla: editar `k8s/infra/airflow-values.yaml` con
  `defaultAirflowRepository: luisfrontuso10/mme-airflow` + tag, y push.
  ArgoCD detecta el cambio y sincroniza via helm.
