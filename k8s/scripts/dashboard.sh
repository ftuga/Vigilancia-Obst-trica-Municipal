#!/usr/bin/env bash
# Imprime la URL clickeable del Kubernetes Dashboard y el token de login.
# Habilita el addon y crea el NodePort si todavía no existen.
#
# Uso:
#   bash k8s/scripts/dashboard.sh
#
# Variables opcionales:
#   DASHBOARD_NODEPORT (default: 30444)
#   KUBECTL            (default: "microk8s kubectl")

set -euo pipefail

KUBECTL="${KUBECTL:-microk8s kubectl}"
DASHBOARD_NODEPORT="${DASHBOARD_NODEPORT:-30444}"
NS="kube-system"
SVC="kubernetes-dashboard"
# El secret default `microk8s-dashboard-token` apunta al SA `default` (sin
# permisos) y devuelve 401 en la UI. Creamos un SA dedicado con cluster-admin
# y un Secret persistente — esos son los credenciales que el dashboard acepta.
SA="dashboard-admin"
SECRET="${SA}-token"

bold() { printf '\033[1m%s\033[0m' "$1"; }
dim()  { printf '\033[2m%s\033[0m' "$1"; }
warn() { printf '\033[33m%s\033[0m\n' "$1" >&2; }

# 1. Habilitar addon si está disabled (idempotente).
if ! microk8s status --format short 2>/dev/null | grep -qE "^core/dashboard: enabled$"; then
    warn "Habilitando addon dashboard…"
    microk8s enable dashboard >/dev/null
fi

# 2. Esperar pod ready (timeout 60s).
for _ in $(seq 1 30); do
    ready=$($KUBECTL get pod -n "$NS" -l k8s-app=kubernetes-dashboard \
        -o jsonpath='{.items[0].status.containerStatuses[0].ready}' 2>/dev/null || true)
    [[ "$ready" == "true" ]] && break
    sleep 2
done
if [[ "${ready:-false}" != "true" ]]; then
    warn "El pod del dashboard no quedó Ready en 60s. Ver: kubectl get pod -n $NS -l k8s-app=kubernetes-dashboard"
    exit 1
fi

# 3. Asegurar que el Service sea NodePort en el puerto deseado.
current_type=$($KUBECTL get svc -n "$NS" "$SVC" -o jsonpath='{.spec.type}' 2>/dev/null || echo "")
current_np=$($KUBECTL get svc -n "$NS" "$SVC" \
    -o jsonpath='{.spec.ports[0].nodePort}' 2>/dev/null || echo "")
if [[ "$current_type" != "NodePort" ]] || [[ "$current_np" != "$DASHBOARD_NODEPORT" ]]; then
    $KUBECTL patch svc -n "$NS" "$SVC" -p \
        "{\"spec\":{\"type\":\"NodePort\",\"ports\":[{\"port\":443,\"targetPort\":8443,\"nodePort\":$DASHBOARD_NODEPORT}]}}" \
        >/dev/null
fi

# 4. Detección de HOST_IP (WSL2 vs nativo) — mismo método que show-urls.sh.
if grep -qi microsoft /proc/version 2>/dev/null; then
    HOST_IP=$(ip -4 addr show eth0 2>/dev/null | awk '/inet /{print $2}' | cut -d/ -f1 | head -1)
    HOST_KIND="WSL2 (eth0)"
else
    HOST_IP="${MICROK8S_NODE_IP:-127.0.0.1}"
    HOST_KIND="MICROK8S_NODE_IP"
fi
HOST_IP=${HOST_IP:-127.0.0.1}

# 5. ServiceAccount con cluster-admin (idempotente).
$KUBECTL get sa -n "$NS" "$SA" >/dev/null 2>&1 || \
    $KUBECTL create sa "$SA" -n "$NS" >/dev/null
$KUBECTL get clusterrolebinding "$SA" >/dev/null 2>&1 || \
    $KUBECTL create clusterrolebinding "$SA" \
        --clusterrole=cluster-admin --serviceaccount="$NS:$SA" >/dev/null

# 6. Secret persistente de tipo service-account-token.
#    El dashboard v2.7.0 valida el token contra el Secret asociado al SA;
#    el JWT efímero de `kubectl create token` puede dar 401.
$KUBECTL get secret -n "$NS" "$SECRET" >/dev/null 2>&1 || cat <<EOF | $KUBECTL apply -f - >/dev/null
apiVersion: v1
kind: Secret
metadata:
  name: $SECRET
  namespace: $NS
  annotations:
    kubernetes.io/service-account.name: $SA
type: kubernetes.io/service-account-token
EOF

# 7. Esperar a que el controller-manager popule el token (típicamente <2s).
TOKEN=""
for _ in $(seq 1 10); do
    TOKEN=$($KUBECTL get secret -n "$NS" "$SECRET" \
        -o jsonpath='{.data.token}' 2>/dev/null | base64 -d 2>/dev/null || true)
    [[ -n "$TOKEN" ]] && break
    sleep 1
done
if [[ -z "$TOKEN" ]]; then
    warn "No se pudo obtener el token desde $SECRET. Probar: $KUBECTL describe secret -n $NS $SECRET"
    exit 1
fi

URL="https://${HOST_IP}:${DASHBOARD_NODEPORT}"
TOKEN_LEN=${#TOKEN}

# Intentar copiar al clipboard. En WSL → clip.exe; en Linux nativo → wl-copy/xclip si están.
CLIPBOARD_MSG=""
if command -v clip.exe >/dev/null 2>&1; then
    printf '%s' "$TOKEN" | clip.exe 2>/dev/null && CLIPBOARD_MSG="Token copiado al portapapeles de Windows."
elif command -v wl-copy >/dev/null 2>&1; then
    printf '%s' "$TOKEN" | wl-copy 2>/dev/null && CLIPBOARD_MSG="Token copiado al portapapeles (Wayland)."
elif command -v xclip >/dev/null 2>&1; then
    printf '%s' "$TOKEN" | xclip -selection clipboard 2>/dev/null && CLIPBOARD_MSG="Token copiado al portapapeles (X11)."
fi

printf '\n%s %s %s\n' "$(bold "Host:")" "$HOST_IP" "$(dim "($HOST_KIND)")"
printf '%s\n'   "$(dim "Cert self-signed: el browser pedirá Avanzado → Continuar.")"
printf '\n%s\n' "$(bold "Kubernetes Dashboard")"
printf '  URL:   %s\n' "$URL"
printf '  Auth:  Token (longitud: %d caracteres)\n' "$TOKEN_LEN"
if [[ -n "$CLIPBOARD_MSG" ]]; then
    printf '  %s\n' "$(bold "$CLIPBOARD_MSG") Pega con Ctrl+V."
else
    printf '\n%s\n' "$(bold "Token (triple-click para seleccionar la línea, luego copiar):")"
    printf '%s\n' "$TOKEN"
fi
printf '\n%s\n' "$(dim "Si sale 401 al pegar: refrescá login (Ctrl+Shift+R) o abrí en incógnito.")"
printf '%s\n\n' "$(dim "Confirmá que pegaste $TOKEN_LEN caracteres exactos (sin espacios).")"
