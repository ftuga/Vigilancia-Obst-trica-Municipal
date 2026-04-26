#!/usr/bin/env bash
# Renderiza un ConfigMap base con env vars no-secretas, replicado en cada namespace.
# Las variables sensibles (passwords, keys) viven en Secrets, no acá.

set -euo pipefail

ENV_FILE="${1:-k8s/.env}"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: $ENV_FILE no existe."
    exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

KUBECTL="${KUBECTL:-microk8s kubectl}"

CONFIGMAP_NAME=mme-env

PUBLIC_KEYS=(
    MICROK8S_NODE_IP
    MLFLOW_NODEPORT MINIO_API_NODEPORT MINIO_CONSOLE_NODEPORT
    API_PREDICT_NODEPORT FRONTEND_NODEPORT AIRFLOW_NODEPORT JUPYTER_NODEPORT PGADMIN_NODEPORT
    MLFLOW_INTERNAL_URL MINIO_INTERNAL_S3
    POSTGRES_AIRFLOW_HOST POSTGRES_AIRFLOW_PORT POSTGRES_AIRFLOW_DB POSTGRES_AIRFLOW_USER
    POSTGRES_MLFLOW_HOST POSTGRES_MLFLOW_PORT POSTGRES_MLFLOW_DB POSTGRES_MLFLOW_USER
    REDIS_HOST REDIS_PORT
    MLFLOW_EXTERNAL_URL API_PREDICT_EXTERNAL_URL FRONTEND_EXTERNAL_URL
    MLFLOW_S3_BUCKET MLFLOW_TRACKING_URI MLFLOW_EXPERIMENT_NAME MLFLOW_REGISTRY_MODEL_NAME
    MLFLOW_S3_ENDPOINT_URL
    API_MME_CI_ALPHA API_MME_BOOTSTRAP_REPLICATES API_MME_PANEL_CACHE_TTL_SECONDS API_MME_LOG_LEVEL
    API_PREDICT_MME_URL NEXT_PUBLIC_DISCLAIMER_ENABLED
    DOCKERHUB_USER
    IMAGE_TAG_API_PREDICT IMAGE_TAG_FRONTEND IMAGE_TAG_MLFLOW IMAGE_TAG_AIRFLOW IMAGE_TAG_JUPYTER
)

build_args() {
    local args=()
    for k in "${PUBLIC_KEYS[@]}"; do
        local v="${!k:-}"
        args+=(--from-literal="$k=$v")
    done
    printf '%s\n' "${args[@]}"
}

apply_configmap() {
    local ns=$1
    mapfile -t literals < <(build_args)
    $KUBECTL create configmap "$CONFIGMAP_NAME" \
        --namespace="$ns" \
        "${literals[@]}" \
        --dry-run=client -o yaml | $KUBECTL apply -f -
}

main() {
    for ns in airflow mlflow data apps; do
        $KUBECTL get ns "$ns" >/dev/null 2>&1 || $KUBECTL create ns "$ns"
        apply_configmap "$ns"
    done

    echo
    echo "ConfigMap '$CONFIGMAP_NAME' aplicado en: airflow, mlflow, data, apps."
    echo "Verificar con: $KUBECTL get cm $CONFIGMAP_NAME -n <namespace> -o yaml"
}

main "$@"
