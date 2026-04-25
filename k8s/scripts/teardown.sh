#!/usr/bin/env bash
# Borra todos los workloads MME del cluster sin destruir MicroK8s.
# Para reset total: 'microk8s reset' (operación destructiva, fuera de este script).

set -euo pipefail

KUBECTL="${KUBECTL:-microk8s kubectl}"

confirm() {
    read -r -p "Borrar todos los workloads MME (apps, airflow, mlflow, data)? [yes/NO] " ans
    [[ "$ans" == "yes" ]] || { echo "Abortado."; exit 0; }
}

main() {
    confirm

    $KUBECTL delete application -n argocd --all --ignore-not-found || true
    $KUBECTL delete -f k8s/argo-cd/app-of-apps.yaml --ignore-not-found || true

    for ns in airflow mlflow data apps; do
        echo "Borrando namespace $ns..."
        $KUBECTL delete ns "$ns" --ignore-not-found --timeout=120s
    done

    echo
    echo "Workloads borrados. Para wipe completo del cluster: microk8s reset"
}

main "$@"
