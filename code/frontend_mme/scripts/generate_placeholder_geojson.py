#!/usr/bin/env python3
"""Genera un GeoJSON placeholder con 33 círculos aproximando cada departamento.

NO es un GeoJSON topográfico real — es un placeholder visual para que el
coroplético renderice. Reemplazar con el oficial del IGAC/DANE cuando esté
disponible (respetar la property ``DPTO_CCDGO``, 2 dígitos DIVIPOLA).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

# Capitales por departamento (cod_dpto DIVIPOLA → (nombre, lat, lon))
DEPTOS = {
    "05": ("Antioquia", 6.25, -75.57),
    "08": ("Atlántico", 10.96, -74.80),
    "11": ("Bogotá D.C.", 4.61, -74.08),
    "13": ("Bolívar", 10.39, -75.51),
    "15": ("Boyacá", 5.54, -73.36),
    "17": ("Caldas", 5.07, -75.52),
    "18": ("Caquetá", 1.62, -75.61),
    "19": ("Cauca", 2.44, -76.61),
    "20": ("Cesar", 10.47, -73.25),
    "23": ("Córdoba", 8.75, -75.88),
    "25": ("Cundinamarca", 5.03, -74.10),
    "27": ("Chocó", 5.69, -76.66),
    "41": ("Huila", 2.93, -75.28),
    "44": ("La Guajira", 11.54, -72.91),
    "47": ("Magdalena", 10.42, -74.19),
    "50": ("Meta", 4.15, -73.63),
    "52": ("Nariño", 1.21, -77.28),
    "54": ("Norte de Santander", 7.89, -72.50),
    "63": ("Quindío", 4.53, -75.68),
    "66": ("Risaralda", 4.81, -75.69),
    "68": ("Santander", 7.12, -73.12),
    "70": ("Sucre", 9.30, -75.40),
    "73": ("Tolima", 4.44, -75.23),
    "76": ("Valle del Cauca", 3.44, -76.52),
    "81": ("Arauca", 7.08, -70.76),
    "85": ("Casanare", 5.33, -72.39),
    "86": ("Putumayo", 0.44, -76.52),
    "88": ("San Andrés", 12.58, -81.70),
    "91": ("Amazonas", -1.44, -71.57),
    "94": ("Guainía", 2.56, -68.53),
    "95": ("Guaviare", 2.04, -72.69),
    "97": ("Vaupés", 0.85, -70.23),
    "99": ("Vichada", 4.42, -69.29),
}

CIRCLE_RADIUS_DEG = 0.6  # ~66 km — aproximación burda
N_POINTS = 32


def circle_polygon(lat: float, lon: float, r: float, n: int) -> list[list[float]]:
    """Polígono aproximando un círculo (en EPSG:4326)."""
    coords = []
    for i in range(n + 1):
        theta = 2 * math.pi * i / n
        coords.append([lon + r * math.cos(theta), lat + r * math.sin(theta)])
    return coords


def main() -> None:
    features = []
    for cod, (nombre, lat, lon) in DEPTOS.items():
        features.append({
            "type": "Feature",
            "properties": {
                "DPTO_CCDGO": cod,
                "DPTO_CNMBR": nombre,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [circle_polygon(lat, lon, CIRCLE_RADIUS_DEG, N_POINTS)],
            },
        })

    data = {"type": "FeatureCollection", "features": features}
    dest = Path(__file__).parent.parent / "public" / "geo" / "colombia-departamentos.geojson"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(data, ensure_ascii=False, indent=0))
    print(f"Placeholder GeoJSON → {dest} ({dest.stat().st_size} bytes, "
          f"{len(features)} deptos)")


if __name__ == "__main__":
    main()
