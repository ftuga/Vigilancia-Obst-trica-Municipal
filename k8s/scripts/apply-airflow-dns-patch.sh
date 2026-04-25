#!/usr/bin/env bash
# Aplica dnsConfig ndots:1 a los pods de Airflow.
#
# El chart apache/airflow 1.16.0 NO soporta dnsConfig en values.yaml.
# Por defecto los pods heredan el search domain del host WSL (sersocial.org)
# con ndots:5, lo que hace que dominios como www.datos.gov.co resuelvan a
# wildcards internos con cert self-signed (rompe ingesta APIs públicas).
#
# Este patch fuerza ndots:1 vía kubectl strategic merge.
# Re-ejecutar después de cada Argo sync que rote los deployments.
#
# Uso: bash k8s/scripts/apply-airflow-dns-patch.sh
set -euo pipefail

KUBECTL="${KUBECTL:-microk8s kubectl}"
NS=airflow
PATCH='{"spec":{"template":{"spec":{"dnsConfig":{"options":[{"name":"ndots","value":"1"}]}}}}}'

echo "Patching airflow-worker..."
$KUBECTL patch deployment airflow-worker -n "$NS" --type=strategic --patch "$PATCH"

echo "Patching airflow-scheduler..."
$KUBECTL patch deployment airflow-scheduler -n "$NS" --type=strategic --patch "$PATCH"

echo "Patching airflow-triggerer..."
$KUBECTL patch statefulset airflow-triggerer -n "$NS" --type=strategic --patch "$PATCH"

echo
echo "Esperando rollout..."
$KUBECTL rollout status deployment/airflow-worker -n "$NS" --timeout=120s
$KUBECTL rollout status deployment/airflow-scheduler -n "$NS" --timeout=120s

echo
echo "Verificando DNS desde un worker:"
WORKER=$($KUBECTL get pods -n "$NS" -l component=worker -o jsonpath='{.items[0].metadata.name}')
$KUBECTL exec -n "$NS" "$WORKER" -c worker -- getent hosts www.datos.gov.co | head -3
echo "Done."
