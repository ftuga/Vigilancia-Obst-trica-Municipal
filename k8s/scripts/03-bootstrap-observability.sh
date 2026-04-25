#!/usr/bin/env bash
# Aplica dashboards Grafana + PrometheusRule MME al kube-prom-stack del addon observability.
# Idempotente.

set -euo pipefail

KUBECTL="${KUBECTL:-microk8s kubectl}"
DASH_DIR="${DASH_DIR:-code/proyecto_01/grafana/dashboards}"
RULES_FILE="${RULES_FILE:-k8s/observability/mme-prometheus-rules.yaml}"
NS=observability

apply_dashboard() {
    local file=$1
    local name
    name="grafana-dashboard-$(basename "$file" .json | tr '_' '-')"
    $KUBECTL create configmap "$name" \
        --namespace="$NS" \
        --from-file="$(basename "$file")=$file" \
        --dry-run=client -o yaml | \
        sed "/^metadata:/a\\
  labels:\\
    grafana_dashboard: \"1\"\\
    app.kubernetes.io/part-of: vigilancia-obstetrica-municipal" | \
        $KUBECTL apply -f -
}

main() {
    if [[ ! -d "$DASH_DIR" ]]; then
        echo "ERROR: $DASH_DIR no existe."
        exit 1
    fi

    for f in "$DASH_DIR"/*.json; do
        [[ -f "$f" ]] || continue
        echo "Applying dashboard $f..."
        apply_dashboard "$f"
    done

    if [[ -f "$RULES_FILE" ]]; then
        echo "Applying PrometheusRule from $RULES_FILE..."
        $KUBECTL apply -f "$RULES_FILE"
    fi

    echo
    echo "Dashboards aplicados:"
    $KUBECTL get configmap -n "$NS" -l grafana_dashboard=1 --no-headers
    echo
    echo "PrometheusRules:"
    $KUBECTL get prometheusrule -n "$NS" -l app.kubernetes.io/part-of=vigilancia-obstetrica-municipal --no-headers
}

main "$@"
