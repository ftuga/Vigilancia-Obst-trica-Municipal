# Vigilancia Obstétrica Municipal

Sistema ML end-to-end para predicción de vulnerabilidad obstétrica municipal
en Colombia basado en SIVIGILA 549 (Morbilidad Materna Extrema).

## Estado actual (2026-04-24)

- Modelo C3 **LightGBM Poisson** — test Spearman dpto **0.834** (gate 0.30).
- Pipeline **Airflow bronze→silver→gold** (DuckDB + parquet).
- **MLflow Registry** con alias `@champion` — gate combinado de promoción.
- **Evidently + PSI/KS** para drift detection.
- Observabilidad: Prometheus + Grafana + Pushgateway.

## Layout

```
vigilancia-obstetrica-municipal/
├── src/mme/                  # Paquete instalable (training, evaluation, tracking, drift)
├── api_predict_mme/          # FastAPI serving (próximo sprint)
├── frontend_mme/             # Next.js dashboard (sesión aparte)
├── proyecto_01/              # Docker Compose: Airflow, MLflow, MinIO, Grafana, Jupyter
├── scripts/                  # Scripts de ingesta/utilidades
├── tests/                    # pytest (unit + integration)
├── docs/mme/                 # Documentación metodológica
├── data/mme/                 # Medallón bronze/silver/gold (gitignore)
└── reports/                  # Reportes de runs, EDA, drift
```

## Setup

```bash
uv sync
cd proyecto_01 && cp .env.example .env && docker compose up -d
```

UIs locales:
- Airflow: http://localhost:8080
- MLflow:  http://localhost:5000
- Grafana: http://localhost:3000
- Jupyter: http://localhost:8888
- MinIO:   http://localhost:9001

## Documentación clave

- `docs/mme/ml-problem-definition.md` — unidad de análisis, target, gates
- `docs/mme/model-evaluation.md` — por qué 0.834 y cómo reproducir
- `docs/mme/NEXT-STEPS.md` — roadmap P1-P6
