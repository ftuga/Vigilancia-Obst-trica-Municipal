#!/usr/bin/env bash
# Imprime las URLs de los servicios usando los NodePorts de .env y la IP actual del nodo.
# En WSL2 detecta la IP de eth0; en Linux nativo cae a 127.0.0.1.

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

if grep -qi microsoft /proc/version 2>/dev/null; then
    HOST_IP=$(ip -4 addr show eth0 2>/dev/null | awk '/inet /{print $2}' | cut -d/ -f1 | head -1)
    HOST_KIND="WSL2 (eth0)"
else
    HOST_IP="${MICROK8S_NODE_IP:-127.0.0.1}"
    HOST_KIND="MICROK8S_NODE_IP"
fi
HOST_IP=${HOST_IP:-127.0.0.1}

argocd_port=$(microk8s kubectl get svc argo-cd-argocd-server -n argocd \
    -o jsonpath='{.spec.ports[?(@.name=="https")].nodePort}' 2>/dev/null || echo 30443)

printf '\n%-22s %s\n' "Host:" "$HOST_IP ($HOST_KIND)"
echo "URLs accesibles desde el browser de tu sistema operativo:"
echo
printf '%-20s %s\n' "Servicio" "URL"
printf '%-20s %s\n' "--------" "---"
printf '%-20s http://%s:%s\n'  "Airflow webserver"   "$HOST_IP" "${AIRFLOW_NODEPORT:-30080}"
printf '%-20s http://%s:%s\n'  "MLflow tracking"     "$HOST_IP" "${MLFLOW_NODEPORT:-30500}"
printf '%-20s http://%s:%s\n'  "api-predict-mme"     "$HOST_IP" "${API_PREDICT_NODEPORT:-30601}"
printf '%-20s http://%s:%s\n'  "frontend-mme"        "$HOST_IP" "${FRONTEND_NODEPORT:-30602}"
printf '%-20s http://%s:%s\n'  "MinIO API"           "$HOST_IP" "${MINIO_API_NODEPORT:-30900}"
printf '%-20s http://%s:%s\n'  "MinIO Console"       "$HOST_IP" "${MINIO_CONSOLE_NODEPORT:-30901}"
printf '%-20s http://%s:%s\n'  "JupyterLab"          "$HOST_IP" "${JUPYTER_NODEPORT:-30888}"
printf '%-20s https://%s:%s\n' "ArgoCD UI"           "$HOST_IP" "$argocd_port"
echo
echo "Nota WSL2: si reiniciás WSL la IP cambia. Re-ejecutá este script para actualizar."
