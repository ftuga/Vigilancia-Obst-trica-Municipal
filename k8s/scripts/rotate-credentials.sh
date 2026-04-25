#!/usr/bin/env bash
# Reemplaza los placeholders 'changeme-*' en k8s/.env con valores aleatorios.
# Idempotente sobre los placeholders ya rotados (no toca lo que no esté en estado 'changeme').

set -euo pipefail

ENV_FILE="${1:-k8s/.env}"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: $ENV_FILE no existe. Copiar k8s/.env.example a k8s/.env primero." >&2
    exit 1
fi

if ! command -v python3 >/dev/null; then
    echo "ERROR: python3 requerido (apt install python3)" >&2
    exit 1
fi

python3 - "$ENV_FILE" <<'PY'
import secrets
import sys
from pathlib import Path
from cryptography.fernet import Fernet

env_path = Path(sys.argv[1])
src = env_path.read_text()

placeholders = {
    'POSTGRES_AIRFLOW_PASSWORD': 'changeme-airflow',
    'POSTGRES_MLFLOW_PASSWORD':  'changeme-mlflow',
    'MINIO_ROOT_PASSWORD':       'changeme-minio-root',
    'AIRFLOW_FERNET_KEY':        'changeme-fernet-44chars-base64',
    'AIRFLOW_SECRET_KEY':        'changeme-secret-64hex',
    'AIRFLOW_ADMIN_PASSWORD':    'changeme-admin',
    'REDIS_PASSWORD':            'changeme-redis',
}
generators = {
    'POSTGRES_AIRFLOW_PASSWORD': lambda: secrets.token_hex(24),
    'POSTGRES_MLFLOW_PASSWORD':  lambda: secrets.token_hex(24),
    'MINIO_ROOT_PASSWORD':       lambda: secrets.token_hex(24),
    'AIRFLOW_FERNET_KEY':        lambda: Fernet.generate_key().decode(),
    'AIRFLOW_SECRET_KEY':        lambda: secrets.token_hex(32),
    'AIRFLOW_ADMIN_PASSWORD':    lambda: secrets.token_hex(24),
    'REDIS_PASSWORD':            lambda: secrets.token_hex(24),
}

rotated = []
for key, ph in placeholders.items():
    needle = f'{key}={ph}'
    if needle in src:
        src = src.replace(needle, f'{key}={generators[key]()}')
        rotated.append(key)

env_path.write_text(src)
if rotated:
    print(f'Rotated {len(rotated)} placeholders: {", ".join(sorted(rotated))}')
else:
    print('No placeholders found (already rotated).')
PY
