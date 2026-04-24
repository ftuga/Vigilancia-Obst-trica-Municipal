#!/usr/bin/env bash
# Descarga GeoJSON departamental de Colombia para el coroplético.
# Si no hay URL/acceso, genera un placeholder con círculos por departamento
# para que el mapa renderice igual (reemplazar cuando se tenga el oficial).
set -euo pipefail

DEST="$(dirname "$0")/../public/geo/colombia-departamentos.geojson"
mkdir -p "$(dirname "$DEST")"

URL="${GEOJSON_URL:-}"

if [ -n "$URL" ]; then
  echo "Bajando GeoJSON departamental Colombia desde $URL"
  if curl -fsSL "$URL" -o "$DEST"; then
    BYTES=$(wc -c <"$DEST")
    echo "Guardado en $DEST ($BYTES bytes)"
    exit 0
  fi
  echo "Descarga falló — usando placeholder local"
fi

echo "Generando GeoJSON placeholder (33 círculos por departamento)"
python3 "$(dirname "$0")/generate_placeholder_geojson.py"
echo "NOTA: reemplazar con GeoJSON oficial IGAC/DANE cuando esté disponible."
echo "Properties requeridas: DPTO_CCDGO (2 dígitos DIVIPOLA)."
