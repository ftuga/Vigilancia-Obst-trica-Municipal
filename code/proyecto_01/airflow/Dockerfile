FROM apache/airflow:2.10.5-python3.11

ENV AIRFLOW_HOME=/opt/airflow

USER root
# libgomp1 es runtime de OpenMP, requerido por lightgbm y xgboost
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
USER airflow

RUN pip install "uv>=0.1.33"

COPY requirements.txt /requirements.txt
RUN uv pip install --no-cache -r /requirements.txt