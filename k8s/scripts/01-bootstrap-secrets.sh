#!/usr/bin/env bash
# Genera Secrets K8s en cada namespace desde k8s/.env.
# Idempotente (usa apply, no create).

set -euo pipefail

ENV_FILE="${1:-k8s/.env}"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: $ENV_FILE no existe. Copiar k8s/.env.example y completar."
    exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

KUBECTL="${KUBECTL:-microk8s kubectl}"

ensure_namespace() {
    local ns=$1
    $KUBECTL get ns "$ns" >/dev/null 2>&1 || $KUBECTL create ns "$ns"
}

apply_secret_literal() {
    local ns=$1
    local name=$2
    shift 2
    local args=()
    while [[ $# -gt 0 ]]; do
        args+=(--from-literal="$1")
        shift
    done
    $KUBECTL create secret generic "$name" \
        --namespace="$ns" \
        "${args[@]}" \
        --dry-run=client -o yaml | $KUBECTL apply -f -
}

main() {
    for ns in airflow mlflow data apps; do
        ensure_namespace "$ns"
    done

    apply_secret_literal airflow postgres-airflow-creds \
        "username=${POSTGRES_AIRFLOW_USER}" \
        "password=${POSTGRES_AIRFLOW_PASSWORD}" \
        "database=${POSTGRES_AIRFLOW_DB}"

    apply_secret_literal mlflow postgres-mlflow-creds \
        "username=${POSTGRES_MLFLOW_USER}" \
        "password=${POSTGRES_MLFLOW_PASSWORD}" \
        "database=${POSTGRES_MLFLOW_DB}"

    apply_secret_literal data minio-creds \
        "root-user=${MINIO_ROOT_USER}" \
        "root-password=${MINIO_ROOT_PASSWORD}"

    apply_secret_literal airflow airflow-runtime \
        "fernet-key=${AIRFLOW_FERNET_KEY}" \
        "secret-key=${AIRFLOW_SECRET_KEY}" \
        "admin-user=${AIRFLOW_ADMIN_USER}" \
        "admin-password=${AIRFLOW_ADMIN_PASSWORD}"

    apply_secret_literal airflow redis-creds \
        "password=${REDIS_PASSWORD}"

    apply_secret_literal apps mlflow-s3 \
        "AWS_ACCESS_KEY_ID=${MINIO_ROOT_USER}" \
        "AWS_SECRET_ACCESS_KEY=${MINIO_ROOT_PASSWORD}" \
        "MLFLOW_S3_ENDPOINT_URL=${MLFLOW_S3_ENDPOINT_URL}"

    apply_secret_literal mlflow mlflow-s3 \
        "AWS_ACCESS_KEY_ID=${MINIO_ROOT_USER}" \
        "AWS_SECRET_ACCESS_KEY=${MINIO_ROOT_PASSWORD}" \
        "MLFLOW_S3_ENDPOINT_URL=${MLFLOW_S3_ENDPOINT_URL}"

    echo
    echo "Secrets aplicados:"
    for ns in airflow mlflow data apps; do
        $KUBECTL get secrets -n "$ns" --no-headers 2>/dev/null | grep -v default-token || true
    done
}

main "$@"
