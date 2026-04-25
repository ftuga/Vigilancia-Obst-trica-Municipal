FROM apache/airflow:2.10.5-python3.11

ENV AIRFLOW_HOME=/opt/airflow

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
USER airflow

RUN pip install "uv>=0.1.33"

COPY proyecto_01/airflow/requirements.txt /requirements.txt
RUN uv pip install --no-cache -r /requirements.txt

COPY pyproject.toml /opt/mme/pyproject.toml
COPY README.md /opt/mme/README.md
COPY src /opt/mme/src
RUN uv pip install --no-cache --no-deps -e /opt/mme

ENV PYTHONPATH=/opt/mme/src
