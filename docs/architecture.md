# Arquitectura del sistema

> Stub. Se expande en B13 con diagrama C4 completo. Versión actual: vista lógica + flujo de datos.

---

## Vista lógica

Sistema single-cluster MicroK8s con 4 dominios:

1. **Datos** (`namespace: data`)
   Ingesta bronze → silver → gold. MinIO como object store para parquets crudos y artifacts MLflow. Postgres separado para metadata MLflow.

2. **Orquestación** (`namespace: airflow`)
   Airflow CeleryExecutor con scheduler + N workers. DAGs sincronizados desde este repo vía gitSync. Postgres separado para metadata Airflow.

3. **Modelos** (`namespace: mlflow`)
   MLflow tracking + registry con alias `@champion`. Backend Postgres, artifact root MinIO.

4. **Aplicaciones** (`namespace: apps`)
   API de inferencia FastAPI + frontend Next.js. Conectados al MLflow registry para descubrir el champion vigente.

5. **Observabilidad** (`namespace: observability`)
   kube-prometheus-stack (Prometheus + Alertmanager + Grafana) + Loki + Tempo. Scraping automático de pods con annotations Prometheus.

6. **GitOps** (`namespace: argocd`)
   ArgoCD App-of-Apps. Pull desde este mismo repo (`k8s/argo-cd/apps/`).

---

## Flujo de datos

```
SIVIGILA 549/550, DANE Censo, MinSalud REPS, BDUA Supersalud
   │
   ▼
[Airflow DAG 1: ETL bronze→silver→gold]
   │
   ├─→ MinIO bronze: parquets crudos por fuente
   ├─→ MinIO silver: panel tipado + DIVIPOLA reconciliado
   └─→ MinIO gold: panel_muni_semestre + panel_muni_semana
                      │
                      ▼
[Airflow DAG 2: train + promote]
   │
   ├─→ check_drift  (PSI vs baseline del champion)
   ├─→ train_c3     (NegBin + LGBM Poisson + Optuna)
   ├─→ validate     (5 gates)
   └─→ promote      (alias @champion si nuevo ≥ prev × 0.95 OR ≥ 0.65)
                      │
                      ▼
[MLflow registry]  →  [api_predict_mme carga champion al startup]
                                            │
                                            ▼
                            [frontend_mme renderiza /mme]
```

---

## CI/CD

```
git push main
   │
   ▼
[GHA build-and-push.yml]
   │
   ├─ matrix: api-predict-mme, frontend-mme, mlflow, airflow, jupyterlab
   ├─ multi-arch: linux/amd64 + linux/arm64
   └─ tag: YYYYMMDD-{short-sha}
        │
        ▼
[Docker Hub luisfrontuso10/mme-*]
        │
        ▼
[GHA bump-image-tags.yml]
   │
   └─ sed bump en k8s/apps/*/deployment.yaml
        │
        ▼
[Commit chore(k8s): bump <svc> to <tag> en main]
        │
        ▼
[ArgoCD detecta diff]  →  sync automated  →  rollout en cluster
```

---

## Parametrización multi-host

Stack hoy single-node. Las IPs/hosts/puertos se inyectan vía `k8s/.env` y se renderizan a un ConfigMap base. Migrar un servicio a otro host requiere:

1. Añadir el nodo al cluster con `microk8s add-node` + `microk8s join`.
2. Editar `MLFLOW_INTERNAL_URL` (o variable equivalente) en `.env` apuntando a `IP-nuevo-host:NodePort`.
3. Re-render de ConfigMap (`bash k8s/scripts/02-render-env-configmap.sh`).
4. `kubectl rollout restart` del deployment cliente.

Detalle: `code/docs/mme/runbook.md` §10.

---

## Pendiente (REQ-003)

- B2-B3: skeleton `k8s/` + namespaces + secrets/configmaps
- B4-B7: Helm releases (Airflow, postgres × 2, MinIO) + manifests propios
- B8: re-aplicar dashboards MME al kube-prometheus-stack
- B9-B10: GHA build matrix + bump tags
- B11: ArgoCD app-of-apps
- B12-B13: smoke E2E + deprecar compose + diagrama C4

Estado tracking en `.claude/memory/helix-plan-REQ-003.md` (privado en `ent_tesis`).
