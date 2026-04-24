#!/usr/bin/env bash
# R-029 · Genera un `.env` listo para levantar proyecto_01 con secrets aleatorios.
#
# Uso:
#   scripts/gen_env.sh              # no sobrescribe si .env ya existe
#   FORCE=true scripts/gen_env.sh   # sobreescribe .env existente
#
# Secretos generados:
#   · POSTGRES_AIRFLOW_PASSWORD   (32 chars)
#   · POSTGRES_MLFLOW_PASSWORD    (32 chars)
#   · MINIO_ROOT_PASSWORD         (32 chars, == AWS_SECRET_ACCESS_KEY)
#   · MINIO_ROOT_USER             (16 chars, == AWS_ACCESS_KEY_ID)
#   · _AIRFLOW_WWW_USER_PASSWORD  (24 chars)
#   · PGADMIN_DEFAULT_PASSWORD    (24 chars)
#   · GRAFANA_ADMIN_PASSWORD      (24 chars)
#   · JUPYTER_TOKEN               (48 chars hex)
#   · AIRFLOW_FERNET_KEY          (Fernet válida, 44 chars base64 urlsafe)
#
# Valores de usuario (defaults fijos, editar a mano si se necesita):
#   · Usuarios de BD, puertos, nombres de bucket/db, etc.
#
# Exit codes: 0 OK · 1 .env ya existe (y FORCE≠true) · 2 falta herramienta
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_PATH="${REPO_ROOT}/proyecto_01/.env"
FORCE="${FORCE:-false}"

red()   { printf "\033[0;31m%s\033[0m\n" "$*"; }
green() { printf "\033[0;32m%s\033[0m\n" "$*"; }
blue()  { printf "\033[0;34m%s\033[0m\n" "$*"; }

# ── Pre-checks
for cmd in openssl python3; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    red "✗ falta '$cmd'. Instalá con: apt install $cmd"
    exit 2
  fi
done

if [[ -f "$ENV_PATH" && "$FORCE" != "true" ]]; then
  red "✗ ${ENV_PATH} ya existe. Para sobrescribir: FORCE=true scripts/gen_env.sh"
  exit 1
fi

# ── Generadores deterministas locales (sin dependencias de red)
rand_alnum() {  # $1 = longitud
  openssl rand -base64 "$(( $1 * 2 ))" | tr -dc 'A-Za-z0-9' | head -c "$1"
}
rand_hex() {    # $1 = longitud
  openssl rand -hex "$(( $1 / 2 ))" | head -c "$1"
}
gen_fernet() {
  python3 - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
}

blue "[1/3] generando secretos…"
POSTGRES_AIRFLOW_USER="airflow_$(rand_alnum 6)"
POSTGRES_AIRFLOW_PASSWORD="$(rand_alnum 32)"
POSTGRES_MLFLOW_USER="mlflow_$(rand_alnum 6)"
POSTGRES_MLFLOW_PASSWORD="$(rand_alnum 32)"
MINIO_ROOT_USER="$(rand_alnum 16)"
MINIO_ROOT_PASSWORD="$(rand_alnum 32)"
AIRFLOW_WWW_USER="admin"
AIRFLOW_WWW_PASSWORD="$(rand_alnum 24)"
PGADMIN_PASSWORD="$(rand_alnum 24)"
GRAFANA_PASSWORD="$(rand_alnum 24)"
JUPYTER_TOKEN="$(rand_hex 48)"

# Fernet requiere `cryptography` — validamos antes de fallar en Airflow
if ! AIRFLOW_FERNET_KEY="$(gen_fernet 2>/dev/null)"; then
  red "✗ no pude generar Fernet. Instalá con: pip install cryptography"
  exit 2
fi

blue "[2/3] escribiendo ${ENV_PATH}…"
cat > "$ENV_PATH" <<EOF
# ============================================================
# proyecto_01 — .env generado por scripts/gen_env.sh
# $(date -u +'%Y-%m-%dT%H:%M:%SZ')
# NO COMMITEAR este archivo. Regenerar con: FORCE=true scripts/gen_env.sh
# ============================================================

# AIRFLOW
AIRFLOW_UID=50000
_AIRFLOW_WWW_USER_USERNAME=${AIRFLOW_WWW_USER}
_AIRFLOW_WWW_USER_PASSWORD=${AIRFLOW_WWW_PASSWORD}
AIRFLOW_FERNET_KEY=${AIRFLOW_FERNET_KEY}

# POSTGRES AIRFLOW
POSTGRES_AIRFLOW_USER=${POSTGRES_AIRFLOW_USER}
POSTGRES_AIRFLOW_PASSWORD=${POSTGRES_AIRFLOW_PASSWORD}
POSTGRES_AIRFLOW_DB=airflow
POSTGRES_AIRFLOW_PORT=5432

# POSTGRES MLFLOW
POSTGRES_MLFLOW_USER=${POSTGRES_MLFLOW_USER}
POSTGRES_MLFLOW_PASSWORD=${POSTGRES_MLFLOW_PASSWORD}
POSTGRES_MLFLOW_DB=mlflow_db
POSTGRES_MLFLOW_PORT=5433

# MINIO (credenciales == AWS_* para el cliente S3 de MLflow)
MINIO_ROOT_USER=${MINIO_ROOT_USER}
MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD}
MINIO_BUCKET=mlflows3
MINIO_PORT=9000
MINIO_CONSOLE_PORT=9001

# MLFLOW
MLFLOW_PORT=5000
MLFLOW_S3_ENDPOINT_URL=http://minio:9000
AWS_ACCESS_KEY_ID=${MINIO_ROOT_USER}
AWS_SECRET_ACCESS_KEY=${MINIO_ROOT_PASSWORD}

# PGADMIN
PGADMIN_DEFAULT_EMAIL=admin@example.com
PGADMIN_DEFAULT_PASSWORD=${PGADMIN_PASSWORD}
PGADMIN_PORT=5050

# JUPYTERLAB (auth vía token — R-008)
JUPYTER_PORT=8888
JUPYTER_TOKEN=${JUPYTER_TOKEN}

# REDIS
REDIS_PORT=6379

# OBSERVABILIDAD
API_DATOS_PORT=8000
API_PREDICT_PORT=8001
PROMETHEUS_PORT=9090
GRAFANA_PORT=3000
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=${GRAFANA_PASSWORD}

# EXPORTERS
CADVISOR_PORT=8082
NODE_EXPORTER_PORT=9100
STATSD_EXPORTER_PORT=9102
PUSHGATEWAY_PORT=9091

# MODELO EN PRODUCCIÓN
MODEL_NAME=rugpull_baseline_binary
MODEL_STAGE=Production
LABEL_MODE=binary

# FRONTEND
FRONTEND_PORT=3001
EOF

chmod 600 "$ENV_PATH"

blue "[3/3] validando con docker compose config…"
if command -v docker >/dev/null 2>&1; then
  if (cd "${REPO_ROOT}/proyecto_01" && docker compose -f compose.yaml config --quiet 2>&1); then
    green "  ✓ compose.yaml valida con el nuevo .env"
  else
    red "  ⚠ compose.yaml no valida — revisar .env manualmente"
  fi
else
  blue "  (docker no disponible — skip validación)"
fi

green "✓ .env generado en ${ENV_PATH} (perms 600)"
echo
echo "Credenciales útiles (guardar en un gestor seguro):"
echo "  · Airflow UI  → user=${AIRFLOW_WWW_USER}  pass=${AIRFLOW_WWW_PASSWORD}"
echo "  · MinIO       → user=${MINIO_ROOT_USER}  pass=${MINIO_ROOT_PASSWORD}"
echo "  · Grafana     → user=admin  pass=${GRAFANA_PASSWORD}"
echo "  · pgAdmin     → user=admin@example.com  pass=${PGADMIN_PASSWORD}"
echo "  · Jupyter     → token=${JUPYTER_TOKEN}"
