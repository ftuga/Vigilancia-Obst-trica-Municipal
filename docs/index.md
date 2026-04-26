# Vigilancia Obstétrica Municipal · Arquitectura MLOps

Sistema MLOps end-to-end sobre **microk8s single-node** con GitOps (ArgoCD) para predecir vulnerabilidad de mortalidad materna a nivel municipal en Colombia.

!!! info "Foco de la tesis"
    El **dominio MME** (mortalidad materna extrema) es el caso de uso. La contribución principal es la **arquitectura MLOps** desplegable, reproducible y observable sobre Kubernetes.

## Stack desplegado

```mermaid
graph TB
    subgraph "GitOps · CI/CD"
        GH[GitHub repo]
        GHA[GitHub Actions<br/>build & push]
        ARGO[ArgoCD<br/>app-of-apps]
        DH[Docker Hub<br/>luisfrontuso10/*]
    end

    subgraph "Orquestación · ML"
        AF[Airflow CeleryExecutor<br/>DAG 0/1/2]
        MLF[MLflow Tracking<br/>+ Registry]
        MN[MinIO S3<br/>medallón bronze/silver/gold]
    end

    subgraph "Serving · UI"
        API[FastAPI predict<br/>OpenTelemetry]
        FE[Next.js frontend]
        JL[JupyterLab]
        PGA[pgAdmin]
    end

    subgraph "Observabilidad"
        PR[Prometheus]
        GR[Grafana]
        LK[Loki]
        TM[Tempo]
        LC[Locust]
    end

    GH -->|push main| GHA
    GHA -->|push image| DH
    GHA -->|bump tag| GH
    GH -->|polling| ARGO
    ARGO -->|sync| AF
    ARGO -->|sync| API
    ARGO -->|sync| MLF
    ARGO -->|sync| MN

    AF -->|track runs| MLF
    AF -->|read/write parquet| MN
    AF -->|panel| API

    API -->|load champion| MLF
    API -->|panel cache| MN
    API -->|metrics| PR
    API -->|traces| TM
    FE --> API
    LC -->|load test| API

    PR --> GR
    LK --> GR
    TM --> GR
```

## Características clave

- **GitOps puro**: cada cambio en `main` dispara CI → ArgoCD reconcilia. Sin `kubectl apply` manual en producción.
- **Pipeline ML completo**: ingesta multi-fuente (DANE, INS, BDUA, REPS) → silver/gold medallón → feature selection PCA+LASSO+MI → entrenamiento NegBin GLM + LightGBM con Optuna → promoción champion via alias MLflow.
- **Observabilidad full-stack**: métricas (Prometheus), logs (Loki), traces (Tempo), load testing (Locust), todo unificado en Grafana.
- **Self-service**: ArgoCD UI, Airflow UI, MLflow UI, JupyterLab, pgAdmin — cada herramienta accesible vía NodePort.

## Próximos pasos

- [Arquitectura detallada](architecture.md)
- [DAGs y data lineage](dags.md)
- [Stack de observabilidad](observability.md)
- [Runbook de deployment](runbook.md)
