# api_predict_mme

FastAPI de serving del modelo C3 MME con descubrimiento dinámico del champion.

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/predict/municipio` | Predice casos MME + 90% CI bootstrap para un `cod_mpio` |
| POST | `/predict/batch` | Batch de varios muni (para dashboards) |
| GET | `/predict/ranking?departamento=X&top_n=10` | Top-N muni por razón MME predicha |
| GET | `/model/info` | Metadata del champion |
| POST | `/model/reload` | Re-descubre champion + residuals + baseline |
| GET | `/healthz` | Liveness |
| GET | `/readyz` | Readiness (modelo cargado + panel disponible) |
| GET | `/metrics` | Prometheus |

## Decisiones de diseño

- **Champion discovery**: alias `@champion` sobre `mme_vulnerability_baseline` (MLflow 3.x; stages deprecated).
- **Bootstrap CI**: residuos train+val del champion (`diagnostics/residuals.npy`) → samples con reemplazo → percentiles [5, 95] = 90% CI. Parametrizable vía `CI_ALPHA` (0.10 default).
- **Cache**: panel gold cacheado en memoria con TTL (default 1 h). `/model/reload` invalida.
- **Hot-swap**: `threading.Lock` en `ModelStore` permite refresh seguro sin bajar el servicio.

## Layout

```
api_predict_mme/
├── pyproject.toml
├── Dockerfile
├── app/
│   ├── main.py                    # FastAPI + Prometheus middleware
│   ├── config.py                  # Settings (MLflow URI, alias, TTL, CI_ALPHA)
│   ├── schemas.py                 # Pydantic DTOs
│   ├── services/
│   │   ├── model_store.py         # Descubrimiento + carga champion (booster + residuals + baseline)
│   │   ├── panel_loader.py        # Load gold + apply_pca + cache TTL
│   │   └── bootstrap.py           # compute_ci(y_point, residuals)
│   └── routes/
│       ├── predict.py · ranking.py · model.py · health.py
└── tests/
    ├── unit/                       # bootstrap, model_store con MLflow mock
    └── integration/                # FastAPI TestClient
```

## Setup local

```bash
cd api_predict_mme
uv sync
export MLFLOW_TRACKING_URI=http://<NODE_IP>:30500
export MLFLOW_TRACKING_USERNAME=admin
export MLFLOW_TRACKING_PASSWORD=...
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export MLFLOW_S3_ENDPOINT_URL=http://<NODE_IP>:30900
uvicorn app.main:app --reload --port 8001
```

## En el cluster (k8s)

Servicio expuesto como NodePort `30601` por la app `api-predict-mme` (namespace `apps`). Manifests en `k8s/apps/api-predict-mme/`. Tags de imagen los bumpea el workflow `bump-image-tags.yml` tras cada build exitoso → ArgoCD sincroniza.

```bash
microk8s kubectl get pods -n apps -l app.kubernetes.io/name=api-predict-mme
curl http://<NODE_IP>:30601/readyz
```
