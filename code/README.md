# `code/` — Paquete `mme` y herramientas de desarrollo

README local del directorio `code/`. Aquí vive el **paquete instalable `mme`**, los **scripts de ingesta**, los **tests** y la **documentación metodológica**.

> Para deploy, infraestructura (microk8s + ArgoCD), DAGs de Airflow, observabilidad (Prometheus/Grafana/Loki/Tempo/Pushgateway/Locust) y URLs de UIs → ver el [README raíz del repo](../README.md).

## Estado actual (2026-04-26)

- Modelo C3 **LightGBM Poisson** — Spearman departamental sobre test 2022 = **0.836** (gate Go/No-Go ≥ 0.30). Ver [`docs/mme/model-evaluation.md`](docs/mme/model-evaluation.md).
- Pipeline **bronze → silver → gold** (DuckDB + parquet) ejecutado por DAGs de Airflow (definidos en `k8s/`).
- Promoción de modelos por **MLflow Registry** con alias `@champion`.
- Drift con **Evidently + PSI/KS**.
- Serving: **FastAPI** (`api_predict_mme/`) + frontend Next.js (`frontend_mme/`).

## Layout

```
code/
├── src/mme/                  # Paquete instalable
│   ├── cli/                  # Entry points typer (mme-ingest-*, mme-build-*, mme-train-*)
│   ├── config.py             # pydantic-settings (env -> Settings)
│   ├── data/                 # I/O bronze/silver/gold (DuckDB + parquet)
│   ├── features/             # Feature engineering C3
│   ├── models/               # LightGBM Poisson, baselines
│   ├── eval/                 # Métricas (Spearman dpto, Precision@k)
│   ├── tracking/             # MLflow logging + aliases
│   ├── drift/                # Evidently + PSI/KS
│   ├── orchestration/        # Helpers para DAGs
│   └── paths.py              # Resolución de rutas medallón
├── api_predict_mme/          # FastAPI serving (paquete propio, ver su README)
├── frontend_mme/             # Next.js dashboard (sesión aparte)
├── scripts/mme/              # Scripts de ingesta y EDA (ejecutados por DAGs o manual)
├── tests/                    # pytest (unit + integration)
├── docs/mme/                 # Documentación metodológica (ver abajo)
├── reports/                  # Outputs de runs, EDA, drift
├── proyecto_01/              # [DEPRECATED] Stack Docker Compose original. Reemplazado por k8s/. Conservado como referencia.
├── pyproject.toml            # Deps, ruff, mypy, pytest, coverage gate 75%
├── .pre-commit-config.yaml   # ruff + mypy + check-secrets
└── uv.lock
```

## Setup local de desarrollo

```bash
cd code/
uv sync --all-extras              # instala mme + dev deps (mlflow, lightgbm, optuna, pytest, ruff, mypy)
uv run pre-commit install         # hooks: ruff, mypy, secrets scan
```

Variables de entorno: copiar `proyecto_01/.env.example` → `.env` solo si vas a correr el stack viejo de Compose. Para apuntar a un MLflow ya desplegado en k8s, exportar:

```bash
export MLFLOW_TRACKING_URI=http://<NODE_IP>:30500
export AWS_ACCESS_KEY_ID=...      # MinIO
export AWS_SECRET_ACCESS_KEY=...
export MLFLOW_S3_ENDPOINT_URL=http://<NODE_IP>:30900
```

## CLI del paquete `mme`

Tras `uv sync` quedan disponibles los entry points definidos en `pyproject.toml`:

```bash
# Ingesta bronze
uv run mme-ingest-sivigila         # SIVIGILA 549 (eventos)
uv run mme-ingest-sivigila-mm      # Morbilidad Materna Extrema
uv run mme-ingest-divipola         # códigos municipales
uv run mme-ingest-censo-nbi        # NBI Censo 2018
uv run mme-ingest-censo-poblacion  # Población Censo 2018
uv run mme-ingest-bdua             # afiliados BDUA
uv run mme-ingest-reps             # prestadores REPS
uv run mme-ingest-dane-eevv        # estadísticas vitales DANE

# Medallón
uv run mme-build-silver
uv run mme-build-gold

# Entrenamiento + EDA
uv run mme-eda-target
uv run mme-eda-features
uv run mme-feature-selection
uv run mme-train-c3
```

En producción estos comandos los dispara Airflow (DAGs `1-mme_etl_medallion` y `2-mme_train_and_promote`).

## Tests

```bash
uv run pytest                                 # todos los tests
uv run pytest -m "not integration"            # solo unit (rápido, sin stack)
uv run pytest -m integration                  # requiere MinIO + MLflow corriendo
uv run pytest --cov=mme --cov-report=term     # con coverage (gate 75%)
```

Estructura:
- `tests/mme/unit/` — funciones puras (features, eval, drift)
- `tests/mme/test_silver_invariants.py` — invariantes del medallón silver
- `tests/mme/test_gold_schema.py` — contrato de columnas/tipos del gold panel

## Calidad de código

```bash
uv run ruff check .                # lint (E, F, W, I, N, UP, B, SIM, PTH, RET, PL, TRY, PERF, D)
uv run ruff format .               # formato
uv run mypy src/mme                # type checking strict
```

Gates configurados en `pyproject.toml`:
- `coverage.fail_under = 75`
- `mypy.strict = true`
- pre-commit corre ruff + mypy en cada commit

## Documentación clave

| Doc | Contenido |
|---|---|
| [`docs/mme/ml-problem-definition.md`](docs/mme/ml-problem-definition.md) | Unidad de análisis, target, gates Go/No-Go |
| [`docs/mme/features-spec-v1.md`](docs/mme/features-spec-v1.md) | Especificación de features C3 (origen, transformación, leakage check) |
| [`docs/mme/model-evaluation.md`](docs/mme/model-evaluation.md) | Por qué Spearman 0.836, métricas secundarias, reproducción |
| [`docs/mme/dane-eevv-procedure.md`](docs/mme/dane-eevv-procedure.md) | Procedimiento de ingesta DANE estadísticas vitales |
| [`docs/mme/mlops-plan.md`](docs/mme/mlops-plan.md) | Plan MLOps end-to-end (registry, drift, promoción) |
| [`docs/mme/NEXT-STEPS.md`](docs/mme/NEXT-STEPS.md) | Roadmap P1-P6 |
| [`docs/adr/`](docs/adr) | Architecture Decision Records |
| [`docs/research-mme.md`](docs/research-mme.md) | Notas de investigación / referencias |

## Notas

- `proyecto_01/` queda como referencia histórica del stack Docker Compose original. La fuente de verdad operativa es `k8s/` (root del repo).
- Los datos del medallón (`data/mme/`) están en `.gitignore`. Para reproducir localmente, correr la cadena de `mme-ingest-*` → `mme-build-silver` → `mme-build-gold`.
- `mlruns_rugpull_archive/` y rutas similares están excluidas de ruff/mypy (legacy archivado).
