#!/usr/bin/env bash
# Deploy completo del stack MME en MicroK8s desde cero.
# Asume k8s/.env ya configurado (ver k8s/README.md §"Generar credenciales").

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="${ENV_FILE:-$REPO_ROOT/k8s/.env}"
KUBECTL="${KUBECTL:-microk8s kubectl}"
HELM="${HELM:-microk8s helm3}"

bold() { printf '\033[1m%s\033[0m' "$1"; }
green() { printf '\033[32m%s\033[0m' "$1"; }
yellow() { printf '\033[33m%s\033[0m' "$1"; }
red() { printf '\033[31m%s\033[0m' "$1"; }

step() {
    echo
    printf '%s %s\n' "$(bold ">>>")" "$(bold "$1")"
}

ok()    { printf '  %s %s\n' "$(green '✓')" "$1"; }
warn()  { printf '  %s %s\n' "$(yellow '!')" "$1"; }
fail()  { printf '  %s %s\n' "$(red '✗')" "$1"; exit 1; }

# ─────────────────────────────────────────────────────────────────────────────
# Pre-flight
# ─────────────────────────────────────────────────────────────────────────────

preflight() {
    step "Pre-flight"

    command -v git >/dev/null  || fail "git no encontrado"
    command -v microk8s >/dev/null || fail "microk8s no encontrado. Ejecutar k8s/scripts/00-setup-microk8s.sh primero"

    if ! groups "$USER" | grep -q microk8s; then
        fail "Usuario $USER no está en grupo microk8s. Ejecutar: sudo usermod -a -G microk8s $USER && newgrp microk8s"
    fi

    if [[ ! -f "$ENV_FILE" ]]; then
        fail "$ENV_FILE no existe. Copiar k8s/.env.example y completar (ver k8s/README.md §Generar credenciales)"
    fi
    ok "git, microk8s, .env presentes"

    if ! $KUBECTL get nodes >/dev/null 2>&1; then
        fail "Cluster MicroK8s no responde. Probar: microk8s status"
    fi
    ok "Cluster MicroK8s reachable"

    if ! $KUBECTL get ns argocd >/dev/null 2>&1; then
        fail "Addon argocd no habilitado. Ejecutar: microk8s enable argocd"
    fi
    ok "Addon argocd presente"

    if grep -E '^(POSTGRES_AIRFLOW_PASSWORD|MINIO_ROOT_PASSWORD|AIRFLOW_FERNET_KEY)=changeme' "$ENV_FILE" >/dev/null; then
        fail "$ENV_FILE tiene placeholders 'changeme-*'. Generar credenciales reales (k8s/README.md §2.1)"
    fi
    ok ".env con credenciales generadas (sin placeholders)"
}

check_logins_optional() {
    step "Logins externos (informativos, no bloqueantes)"

    if [[ -f "$HOME/.docker/config.json" ]] && grep -q '"auths"' "$HOME/.docker/config.json" 2>/dev/null; then
        ok "Docker Hub logueado (config.json detectado)"
    else
        warn "Docker NO logueado. Las imágenes luisfrontuso10/mme-* son públicas — no es necesario para deploy."
    fi

    if command -v gh >/dev/null && gh auth status >/dev/null 2>&1; then
        ok "GitHub CLI logueado: $(gh auth status 2>&1 | grep -E 'account|Logged in' | head -1 | awk '{print $NF}')"
    else
        warn "GitHub CLI NO logueado. Solo necesario si vas a triggerar workflows: 'gh auth login'"
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# Bootstrap base
# ─────────────────────────────────────────────────────────────────────────────

bootstrap_base() {
    step "Namespaces + Secrets + ConfigMaps"
    $KUBECTL apply -f "$REPO_ROOT/k8s/infra/00-namespaces.yaml"
    bash "$REPO_ROOT/k8s/scripts/01-bootstrap-secrets.sh" "$ENV_FILE" >/dev/null
    bash "$REPO_ROOT/k8s/scripts/02-render-env-configmap.sh" "$ENV_FILE" >/dev/null
    ok "4 namespaces, 7 Secrets, ConfigMap mme-env aplicados"
}

helm_repos() {
    step "Helm repos"
    $HELM repo add bitnami https://charts.bitnami.com/bitnami 2>/dev/null || true
    $HELM repo add minio https://charts.min.io/ 2>/dev/null || true
    $HELM repo add apache-airflow https://airflow.apache.org 2>/dev/null || true
    $HELM repo update >/dev/null
    ok "bitnami, minio, apache-airflow"
}

# ─────────────────────────────────────────────────────────────────────────────
# Helm releases
# ─────────────────────────────────────────────────────────────────────────────

install_or_skip() {
    local release=$1 ns=$2 chart=$3 version=$4 values=$5
    if $HELM list -n "$ns" 2>/dev/null | awk '{print $1}' | grep -qx "$release"; then
        warn "Release $release ya existe en ns $ns — skip"
        return
    fi
    $HELM install "$release" "$chart" -n "$ns" --version "$version" -f "$values" --wait --timeout 10m
    ok "Release $release deployed"
}

deploy_stateful() {
    step "Postgres × 2 + MinIO (charts upstream)"
    install_or_skip postgres-airflow airflow bitnami/postgresql 18.6.2 "$REPO_ROOT/k8s/infra/postgres-airflow-values.yaml"
    install_or_skip postgres-mlflow  mlflow  bitnami/postgresql 18.6.2 "$REPO_ROOT/k8s/infra/postgres-mlflow-values.yaml"
    install_or_skip minio            data    minio/minio        5.4.0  "$REPO_ROOT/k8s/infra/minio-values.yaml"
}

deploy_airflow() {
    step "Airflow (chart oficial 2.x)"
    bash "$REPO_ROOT/k8s/scripts/01-bootstrap-secrets.sh" "$ENV_FILE" >/dev/null
    PG_PASS=$($KUBECTL get secret postgres-airflow-creds -n airflow -o jsonpath='{.data.password}' | base64 -d)
    RD_PASS=$($KUBECTL get secret redis-creds -n airflow -o jsonpath='{.data.password}' | base64 -d)
    FERN=$($KUBECTL get secret airflow-runtime -n airflow -o jsonpath='{.data.fernet-key}' | base64 -d)
    SEC_KEY=$($KUBECTL get secret airflow-runtime -n airflow -o jsonpath='{.data.secret-key}' | base64 -d)

    for s in airflow-metadata-conn:postgresql+psycopg2://airflow:$PG_PASS@postgres-airflow.airflow:5432/airflow \
             airflow-broker-url:redis://:$RD_PASS@airflow-redis.airflow:6379/0 \
             airflow-result-backend:db+postgresql://airflow:$PG_PASS@postgres-airflow.airflow:5432/airflow; do
        name=${s%%:*}; value=${s#*:}
        $KUBECTL create secret generic "$name" -n airflow \
            --from-literal=connection="$value" \
            --dry-run=client -o yaml | $KUBECTL apply -f - >/dev/null
    done
    $KUBECTL create secret generic airflow-fernet -n airflow --from-literal=fernet-key="$FERN" --dry-run=client -o yaml | $KUBECTL apply -f - >/dev/null
    $KUBECTL create secret generic airflow-webserver-secret -n airflow --from-literal=webserver-secret-key="$SEC_KEY" --dry-run=client -o yaml | $KUBECTL apply -f - >/dev/null

    install_or_skip airflow airflow apache-airflow/airflow 1.16.0 "$REPO_ROOT/k8s/infra/airflow-values.yaml"

    ADMIN_USER=$($KUBECTL get secret airflow-runtime -n airflow -o jsonpath='{.data.admin-user}' | base64 -d)
    ADMIN_PASS=$($KUBECTL get secret airflow-runtime -n airflow -o jsonpath='{.data.admin-password}' | base64 -d)
    if ! $KUBECTL exec -n airflow deploy/airflow-webserver -- airflow users list 2>/dev/null | grep -q "$ADMIN_USER"; then
        $KUBECTL exec -n airflow deploy/airflow-webserver -- airflow users create \
            --role Admin --username "$ADMIN_USER" --email "$ADMIN_USER@local" \
            --firstname Admin --lastname User --password "$ADMIN_PASS" >/dev/null 2>&1 || true
        ok "Admin user $ADMIN_USER creado en Airflow"
    fi
}

deploy_mlflow() {
    step "MLflow (chart bitnami)"
    PG_PASS=$($KUBECTL get secret postgres-mlflow-creds -n mlflow -o jsonpath='{.data.password}' | base64 -d)
    if ! $KUBECTL exec postgres-mlflow-0 -n mlflow -- env PGPASSWORD="$PG_PASS" psql -U mlflow -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='mlflow_auth'" 2>/dev/null | grep -q 1; then
        $KUBECTL exec postgres-mlflow-0 -n mlflow -- env PGPASSWORD="$PG_PASS" psql -U mlflow -d postgres -c 'CREATE DATABASE mlflow_auth;' >/dev/null
        ok "DB mlflow_auth creada"
    fi
    install_or_skip mlflow mlflow bitnami/mlflow 5.1.17 "$REPO_ROOT/k8s/infra/mlflow-values.yaml"
}

deploy_observability_dashboards() {
    step "Observability — dashboards y alertas MME"
    bash "$REPO_ROOT/k8s/scripts/03-bootstrap-observability.sh" >/dev/null
    ok "3 dashboards Grafana + 9 alertas Prometheus aplicadas"
}

deploy_argocd_apps() {
    step "ArgoCD app-of-apps + 7 hijas"
    $KUBECTL apply -f "$REPO_ROOT/k8s/argo-cd/app-of-apps.yaml" 2>&1 | grep -v "^Warning:" || true

    local target_port=${ARGOCD_NODEPORT:-30443}
    if [[ "$($KUBECTL get svc argo-cd-argocd-server -n argocd -o jsonpath='{.spec.type}' 2>/dev/null)" != "NodePort" ]]; then
        $KUBECTL patch svc argo-cd-argocd-server -n argocd --type merge \
            -p "{\"spec\":{\"type\":\"NodePort\",\"ports\":[{\"name\":\"https\",\"port\":443,\"targetPort\":8080,\"nodePort\":$target_port,\"protocol\":\"TCP\"}]}}" >/dev/null
        ok "ArgoCD service expuesto como NodePort $target_port"
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

main() {
    cd "$REPO_ROOT"
    preflight
    check_logins_optional
    bootstrap_base
    helm_repos
    deploy_stateful
    deploy_airflow
    deploy_mlflow
    deploy_observability_dashboards
    deploy_argocd_apps

    step "Listo. URLs y credenciales:"
    bash "$REPO_ROOT/k8s/scripts/show-urls.sh" "$ENV_FILE"
}

main "$@"
