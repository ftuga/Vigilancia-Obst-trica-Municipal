#!/usr/bin/env bash
# R-024 · Validador de DAGs Airflow del proyecto.
#
# Uso:
#   scripts/validate_dags.sh            # usa el worker en ejecución
#   DOCKER=true scripts/validate_dags.sh   # fuerza docker exec
#
# Chequea:
#   1. airflow dags list-import-errors  → 0 errores
#   2. py_compile sobre cada .py en airflow/dags/ y airflow/dags_rugpull/
#   3. Listado de DAGs registrados (sanity check)
#
# Exit codes:
#   0 OK · 1 import errors · 2 py_compile errors · 3 sin worker disponible
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DAGS_DIR="${REPO_ROOT}/proyecto_01/airflow/dags"
DAGS_RUGPULL_DIR="${REPO_ROOT}/proyecto_01/airflow/dags_rugpull"
WORKER_CONTAINER="${WORKER_CONTAINER:-proyecto_01-airflow-worker-1}"

red()   { printf "\033[0;31m%s\033[0m\n" "$*"; }
green() { printf "\033[0;32m%s\033[0m\n" "$*"; }
blue()  { printf "\033[0;34m%s\033[0m\n" "$*"; }

# ── Paso 1: py_compile local (rápido, sin docker)
blue "[1/3] py_compile sobre DAGs locales…"
PY_FAILS=0
for d in "$DAGS_DIR" "$DAGS_RUGPULL_DIR"; do
  if [[ -d "$d" ]]; then
    while IFS= read -r -d '' f; do
      # compile() en memoria — evita escribir .pyc al __pycache__ (puede ser uid 50000)
      if ! python3 -c "import sys; compile(open(sys.argv[1]).read(), sys.argv[1], 'exec')" "$f" 2>/tmp/dag_syntax_err; then
        red "  ✗ $f"
        sed 's/^/    /' /tmp/dag_syntax_err
        PY_FAILS=$((PY_FAILS + 1))
      fi
    done < <(find "$d" -maxdepth 1 -name "*.py" -print0)
  fi
done
if (( PY_FAILS > 0 )); then
  red "✗ $PY_FAILS archivos con errores de sintaxis"
  exit 2
fi
green "  ✓ sintaxis OK"

# ── Paso 2: airflow dags list-import-errors (requiere worker vivo)
blue "[2/3] airflow dags list-import-errors…"
if ! docker ps --format '{{.Names}}' | grep -q "^${WORKER_CONTAINER}$"; then
  red "  ✗ container '${WORKER_CONTAINER}' no está corriendo"
  echo "    (arrancalo con: cd proyecto_01 && docker compose up -d airflow-worker)"
  exit 3
fi

# stdout solo (evita los RemovedInAirflow3Warning de stderr)
IMPORT_OUT=$(docker exec "$WORKER_CONTAINER" airflow dags list-import-errors 2>/dev/null)
if [[ -z "$IMPORT_OUT" ]] || echo "$IMPORT_OUT" | grep -q "No data found"; then
  green "  ✓ 0 import errors"
else
  red "  ✗ import errors detectados:"
  echo "$IMPORT_OUT" | sed 's/^/    /'
  exit 1
fi

# ── Paso 3: listar DAGs para sanity
blue "[3/3] DAGs registrados:"
docker exec "$WORKER_CONTAINER" airflow dags list 2>/dev/null | \
  grep -v "^---" | grep -v "RemovedIn" | sed 's/^/  /'

green "✓ validación de DAGs OK"
