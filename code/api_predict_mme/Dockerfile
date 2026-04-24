FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# -------- builder --------
FROM base AS builder

COPY --from=ghcr.io/astral-sh/uv:0.9.30 /uv /usr/local/bin/uv

# Instalamos deps de la API
COPY api_predict_mme/pyproject.toml /tmp/api/
WORKDIR /tmp/api
RUN uv pip install --system --no-cache \
      fastapi \
      'uvicorn[standard]' \
      pydantic \
      pydantic-settings \
      prometheus-fastapi-instrumentator \
      httpx \
      'mlflow>=3.11.1' \
      'lightgbm>=4.6.0' \
      'pandas>=2.2' \
      'numpy>=1.26,<2.3' \
      'pyarrow>=14.0' \
      'duckdb>=1.0' \
      'scipy>=1.11' \
      'statsmodels>=0.14.6' \
      'scikit-learn>=1.8.0' \
      'boto3>=1.34'

# -------- runtime --------
FROM base AS runtime

# libgomp1 para LightGBM (OpenMP); libstdc++6 ya viene en slim
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Paquete mme se monta via PYTHONPATH en el compose (RO); acá solo código de la app.
COPY api_predict_mme/app /app/app

# Usuario non-root
RUN groupadd -g 10001 app && useradd -r -u 10001 -g app app
USER app:app

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "2"]
