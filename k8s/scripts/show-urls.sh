#!/usr/bin/env bash
# Imprime URLs (clickeables en terminales modernas) y credenciales
# de los servicios MME usando NodePorts de .env y la IP del nodo.

set -euo pipefail

ENV_FILE="${1:-k8s/.env}"
KUBECTL="${KUBECTL:-microk8s kubectl}"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: $ENV_FILE no existe." >&2
    exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

if grep -qi microsoft /proc/version 2>/dev/null; then
    HOST_IP=$(ip -4 addr show eth0 2>/dev/null | awk '/inet /{print $2}' | cut -d/ -f1 | head -1)
    HOST_KIND="WSL2 (eth0)"
else
    HOST_IP="${MICROK8S_NODE_IP:-127.0.0.1}"
    HOST_KIND="MICROK8S_NODE_IP"
fi
HOST_IP=${HOST_IP:-127.0.0.1}

argocd_port=$($KUBECTL get svc argo-cd-argocd-server -n argocd \
    -o jsonpath='{.spec.ports[?(@.name=="https")].nodePort}' 2>/dev/null || echo 30443)

secret_value() {
    local ns=$1 name=$2 key=$3
    $KUBECTL get secret "$name" -n "$ns" -o jsonpath="{.data.$key}" 2>/dev/null | base64 -d 2>/dev/null || echo ""
}

bold() { printf '\033[1m%s\033[0m' "$1"; }
dim()  { printf '\033[2m%s\033[0m' "$1"; }

print_service() {
    local name=$1 url=$2 creds=$3
    printf '\n%s\n' "$(bold "$name")"
    printf '  URL:   %s\n' "$url"
    if [[ -n "$creds" ]]; then
        printf '  Auth:  %s\n' "$creds"
    else
        printf '  Auth:  %s\n' "$(dim "(sin auth)")"
    fi
}

printf '\n%s %s %s\n' "$(bold Host:)" "$HOST_IP" "$(dim "($HOST_KIND)")"
printf '%s\n' "$(dim "Tip: Ctrl+click en la URL para abrir en browser. Si reiniciás WSL, re-ejecutá este script.")"

argocd_pass=$(secret_value argocd argocd-initial-admin-secret password)
print_service "ArgoCD" \
    "https://${HOST_IP}:${argocd_port}" \
    "admin / ${argocd_pass:-<no-secret>}"

airflow_user=$(secret_value airflow airflow-runtime admin-user)
airflow_pass=$(secret_value airflow airflow-runtime admin-password)
print_service "Airflow webserver" \
    "http://${HOST_IP}:${AIRFLOW_NODEPORT:-30080}" \
    "${airflow_user:-admin} / ${airflow_pass:-<no-secret>}"

mlflow_user=$(secret_value mlflow mlflow-tracking admin-user)
mlflow_pass=$(secret_value mlflow mlflow-tracking admin-password)
print_service "MLflow tracking" \
    "http://${HOST_IP}:${MLFLOW_NODEPORT:-30500}" \
    "${mlflow_user:-admin} / ${mlflow_pass:-<no-secret>}"

minio_user=$(secret_value data minio-creds rootUser)
minio_pass=$(secret_value data minio-creds rootPassword)
print_service "MinIO Console" \
    "http://${HOST_IP}:${MINIO_CONSOLE_NODEPORT:-30901}" \
    "${minio_user:-minioadmin} / ${minio_pass:-<no-secret>}"

print_service "MinIO API (S3)" \
    "http://${HOST_IP}:${MINIO_API_NODEPORT:-30900}" \
    "${minio_user:-minioadmin} / ${minio_pass:-<no-secret>}"

print_service "api-predict-mme" \
    "http://${HOST_IP}:${API_PREDICT_NODEPORT:-30601}" \
    ""

print_service "frontend-mme" \
    "http://${HOST_IP}:${FRONTEND_NODEPORT:-30602}" \
    ""

print_service "JupyterLab" \
    "http://${HOST_IP}:${JUPYTER_NODEPORT:-30888}" \
    ""

echo
