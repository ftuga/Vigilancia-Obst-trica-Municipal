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
uvicorn app.main:app --reload --port 8001
```

En docker-compose: `docker compose up -d api_predict_mme`, disponible en http://localhost:8001.
