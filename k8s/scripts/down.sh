#!/usr/bin/env bash
# Desmonta el stack MME. 2 modos:
#   --apps         Solo apps + airflow + mlflow. Conserva postgres × 2 + minio + PVCs.
#   --all          Todo (apps + stateful + PVCs). Conserva el cluster MicroK8s.
#   --purge        --all + microk8s reset (DESTRUYE el cluster entero).
#
# Default: --apps. Confirma antes de actuar.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
KUBECTL="${KUBECTL:-microk8s kubectl}"
HELM="${HELM:-microk8s helm3}"

MODE="apps"
case "${1:-}" in
    --apps|"") MODE="apps" ;;
    --all)     MODE="all" ;;
    --purge)   MODE="purge" ;;
    *) echo "Uso: $0 [--apps | --all | --purge]"; exit 1 ;;
esac

bold() { printf '\033[1m%s\033[0m' "$1"; }
red()  { printf '\033[31m%s\033[0m' "$1"; }
yellow() { printf '\033[33m%s\033[0m' "$1"; }

confirm() {
    local prompt=$1
    read -r -p "$prompt [escribir 'yes' para continuar] " ans
    [[ "$ans" == "yes" ]] || { echo "Abortado."; exit 0; }
}

step() { echo; printf '%s %s\n' "$(bold ">>>")" "$(bold "$1")"; }

helm_uninstall() {
    local rel=$1 ns=$2
    if $HELM list -n "$ns" 2>/dev/null | awk '{print $1}' | grep -qx "$rel"; then
        $HELM uninstall "$rel" -n "$ns" 2>&1 | tail -1
    fi
}

# ─────────────────────────────────────────────────────────────────────────────

case "$MODE" in
apps)
    echo "$(yellow 'Modo APPS:') desmonta ArgoCD apps + Airflow + MLflow."
    echo "Conserva: postgres-airflow, postgres-mlflow, MinIO, PVCs, Secrets, ConfigMaps."
    confirm "$(bold 'Confirmar desmontaje en modo APPS')"

    step "Borrar Applications ArgoCD (deja recursos hijos hasta tier stateful)"
    $KUBECTL delete -f "$REPO_ROOT/k8s/argo-cd/app-of-apps.yaml" --ignore-not-found 2>&1 | tail -3
    $KUBECTL delete application -n argocd --all --ignore-not-found 2>&1 | tail -3

    step "Helm uninstall apps"
    helm_uninstall airflow airflow
    helm_uninstall mlflow  mlflow

    step "Borrar workloads custom de ns apps"
    $KUBECTL delete all -n apps -l app.kubernetes.io/part-of=vigilancia-obstetrica-municipal --ignore-not-found 2>&1 | tail -3

    echo; echo "$(bold 'OK.') Para volver a levantarlo: bash k8s/scripts/deploy.sh"
    ;;

all)
    echo "$(red 'Modo ALL:') desmonta TODO el stack MME (apps + stateful + PVCs)."
    echo "Conserva: cluster MicroK8s y addons (argocd, observability, etc)."
    echo "Datos en postgres × 2 y MinIO se PIERDEN."
    confirm "$(bold 'Confirmar desmontaje TOTAL del stack')"

    "$0" --apps <<<"yes" 2>/dev/null || true

    step "Helm uninstall stateful"
    helm_uninstall postgres-airflow airflow
    helm_uninstall postgres-mlflow  mlflow
    helm_uninstall minio            data

    step "Borrar PVCs"
    for ns in airflow mlflow data; do
        $KUBECTL delete pvc -n "$ns" --all --ignore-not-found --timeout=120s 2>&1 | tail -3
    done

    step "Borrar Secrets, ConfigMaps y namespaces MME"
    for ns in airflow mlflow data apps; do
        $KUBECTL delete ns "$ns" --ignore-not-found --timeout=120s 2>&1 | tail -3
    done

    step "Borrar dashboards y alertas MME en ns observability"
    $KUBECTL delete configmap -n observability -l app.kubernetes.io/part-of=vigilancia-obstetrica-municipal --ignore-not-found 2>&1 | tail -3
    $KUBECTL delete prometheusrule -n observability -l app.kubernetes.io/part-of=vigilancia-obstetrica-municipal --ignore-not-found 2>&1 | tail -3

    echo; echo "$(bold 'OK.') Cluster intacto. Para volver a levantarlo: bash k8s/scripts/deploy.sh"
    ;;

purge)
    echo "$(red 'Modo PURGE:') --all + microk8s reset."
    echo "Destruye el cluster entero. Hay que correr deploy.sh + 00-setup-microk8s.sh + addons después."
    confirm "$(red 'Confirmar PURGE total del cluster MicroK8s')"

    "$0" --all <<<"yes" 2>/dev/null || true

    step "microk8s reset"
    sudo microk8s reset --destroy-storage 2>&1 | tail -5

    echo; echo "$(bold 'OK.') Cluster destruido. Para reinstalar: bash k8s/scripts/00-setup-microk8s.sh"
    ;;
esac
