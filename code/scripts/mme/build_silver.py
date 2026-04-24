"""
Silver MME — bronze limpio + canónico.

Reglas aplicadas (ver docs/research-mme.md §2 para justificación):
  1. Excluir cod_dpto_o = 1 (EXTERIOR — residencia fuera Colombia, 1.59% casos).
  2. Excluir cod_dpto_o = 0 (PROCEDENCIA DESCONOCIDA, 0.00% casos).
  3. Excluir cod_mun_o % 1000 == 0 (MUNICIPIO DESCONOCIDO a nivel dpto, 0.41% casos).
  4. Mapear huérfanos específicos:
     - 27086 BELÉN DE BAJIRÁ → departamento Chocó (27), queda con código original (no está en DIVIPOLA oficial).
     - 94663 MAPIRIPANA (CD) → es centro poblado del municipio de Inírida (94001) en Guainía.
  5. Join con DIVIPOLA municipios → obtener nombre canónico + lat/lon.
  6. Cast de tipos definitivos.

Output:
  data/mme/silver/mme_clean.parquet
  data/mme/silver/_manifest.json
  reports/mme/silver_qa_<fecha>.md
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from _paths import REPO_ROOT, MME_DATA, MME_REPORTS
BRONZE_GLOB = str(MME_DATA / "bronze" / "year=*" / "*.parquet")
DIVIPOLA_PATH = MME_DATA / "bronze" / "divipola" / "municipios.parquet"
SILVER_DIR = MME_DATA / "silver"
REPORTS_DIR = MME_REPORTS


def main() -> int:
    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(":memory:")
    con.execute(f"CREATE VIEW bronze AS SELECT * FROM parquet_scan('{BRONZE_GLOB}', hive_partitioning=1)")
    con.execute(f"CREATE VIEW divipola AS SELECT * FROM parquet_scan('{DIVIPOLA_PATH}')")

    # 1. Reglas de inclusión + remapeo manual para huérfanos específicos
    con.execute("""
        CREATE VIEW mme_prelim AS
        SELECT
            CASE
                WHEN cod_mun_o = 94663 THEN 94001  -- Mapiripana (CD) → Inírida
                ELSE cod_mun_o
            END AS cod_mun_canon,
            *
        FROM bronze
        WHERE cod_dpto_o NOT IN (0, 1)
          AND cod_mun_o % 1000 != 0
    """)

    # 2. Join con DIVIPOLA (left para conservar Belén de Bajirá que no está en DIVIPOLA oficial)
    con.execute("""
        CREATE VIEW mme_joined AS
        SELECT
            m.cod_mun_canon AS cod_mpio,
            m.cod_dpto_o AS cod_dpto,
            COALESCE(d.nom_mpio, m.municipio_ocurrencia) AS nom_mpio,
            COALESCE(d.dpto, m.departamento_ocurrencia) AS nom_dpto,
            COALESCE(d.tipo_municipio, 'HUERFANO_DIVIPOLA') AS tipo_municipio,
            -- DIVIPOLA publica coordenadas con coma decimal (formato latino)
            CAST(REPLACE(d.longitud, ',', '.') AS DOUBLE) AS longitud,
            CAST(REPLACE(d.latitud, ',', '.') AS DOUBLE) AS latitud,
            CAST(m.ano AS INTEGER) AS ano,
            CAST(m.semana AS SMALLINT) AS semana,
            CASE WHEN m.semana <= 26 THEN 1 ELSE 2 END AS semestre,
            CEIL(m.semana / 13.0)::INTEGER AS trimestre,
            CEIL(m.semana / 4.33)::INTEGER AS mes_epi,
            CAST(m.conteo AS INTEGER) AS conteo,
            -- Regímenes temporales (features dummy)
            CASE WHEN m.ano BETWEEN 2020 AND 2022 THEN 1 ELSE 0 END AS covid_window,
            CASE WHEN m.ano >= 2022 THEN 1 ELSE 0 END AS post_c055,
            -- post_paremm (≥2023) queda fuera de la ventana disponible
            'MORBILIDAD MATERNA EXTREMA' AS nombre_evento
        FROM mme_prelim m
        LEFT JOIN divipola d
          ON m.cod_mun_canon = CAST(d.cod_mpio AS BIGINT)
    """)

    # 3. Persistir silver
    out_path = SILVER_DIR / "mme_clean.parquet"
    con.execute(f"COPY mme_joined TO '{out_path}' (FORMAT PARQUET, COMPRESSION ZSTD)")

    # 4. Métricas de calidad silver
    n_rows = con.execute("SELECT COUNT(*) FROM mme_joined").fetchone()[0]
    n_casos = con.execute("SELECT SUM(conteo) FROM mme_joined").fetchone()[0]
    n_munis = con.execute("SELECT COUNT(DISTINCT cod_mpio) FROM mme_joined").fetchone()[0]
    n_dptos = con.execute("SELECT COUNT(DISTINCT cod_dpto) FROM mme_joined").fetchone()[0]
    n_huerfanos = con.execute("SELECT COUNT(*) FROM mme_joined WHERE tipo_municipio = 'HUERFANO_DIVIPOLA'").fetchone()[0]

    # 5. Manifest
    manifest = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_bronze": "data/mme/bronze/year=*/*.parquet",
        "divipola_catalog": "data/mme/bronze/divipola/municipios.parquet",
        "rules_applied": [
            "excluir cod_dpto_o IN (0, 1)  -- EXTERIOR + PROCEDENCIA DESCONOCIDA",
            "excluir cod_mun_o % 1000 == 0  -- MUNICIPIO DESCONOCIDO a nivel dpto",
            "remapear 94663 MAPIRIPANA (CD) → 94001 INIRIDA (padre municipal)",
            "conservar 27086 BELÉN DE BAJIRÁ como huérfano DIVIPOLA (disputa territorial Chocó/Antioquia)",
        ],
        "features_derived": [
            "semestre, trimestre, mes_epi (de semana epidemiológica)",
            "covid_window (2020-2022)",
            "post_c055 (≥2022, Sentencia C-055/2022)",
        ],
        "row_count": n_rows,
        "casos_totales": n_casos,
        "municipios_distintos": n_munis,
        "departamentos_distintos": n_dptos,
        "filas_huerfano_divipola": n_huerfanos,
    }
    (SILVER_DIR / "_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    # 6. Reporte QA silver
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report_path = REPORTS_DIR / f"silver_qa_{today}.md"

    rows_per_year = con.execute("""
        SELECT ano, COUNT(*) AS n_rows, SUM(conteo) AS casos, COUNT(DISTINCT cod_mpio) AS n_munis
        FROM mme_joined GROUP BY ano ORDER BY ano
    """).fetchdf()

    top_dptos = con.execute("""
        SELECT nom_dpto, COUNT(*) AS n_rows, SUM(conteo) AS casos, COUNT(DISTINCT cod_mpio) AS n_munis
        FROM mme_joined GROUP BY nom_dpto ORDER BY casos DESC LIMIT 15
    """).fetchdf()

    lines = [
        f"# QA Silver — MME Colombia",
        f"",
        f"**Generado**: {datetime.now(timezone.utc).isoformat()}",
        f"**Fuente**: `data/mme/silver/mme_clean.parquet`",
        f"",
        f"## 1. Volumen",
        f"- Filas: **{n_rows:,}** (bronze tenía 65.393 → reducción {100 * (65393 - n_rows) / 65393:.2f}%)",
        f"- Casos MME: **{n_casos:,}** (bronze tenía 178.854 → reducción {100 * (178854 - n_casos) / 178854:.2f}%)",
        f"- Municipios distintos: {n_munis:,}",
        f"- Departamentos distintos: {n_dptos}",
        f"- Filas huérfanas DIVIPOLA (Belén de Bajirá): {n_huerfanos}",
        f"",
        f"## 2. Filas por año",
        f"| año | filas | casos | municipios activos |",
        f"|---|---|---|---|",
    ]
    for _, r in rows_per_year.iterrows():
        lines.append(f"| {int(r['ano'])} | {int(r['n_rows']):,} | {int(r['casos']):,} | {int(r['n_munis']):,} |")
    lines.append("")
    lines.append("## 3. Top 15 departamentos")
    lines.append("| departamento | filas | casos | municipios activos |")
    lines.append("|---|---|---|---|")
    for _, r in top_dptos.iterrows():
        lines.append(f"| {r['nom_dpto']} | {int(r['n_rows']):,} | {int(r['casos']):,} | {int(r['n_munis']):,} |")
    lines.append("")
    lines.append("## 4. Schema silver")
    schema = con.execute("DESCRIBE mme_joined").fetchall()
    lines.append("| columna | tipo |")
    lines.append("|---|---|")
    for col in schema:
        lines.append(f"| `{col[0]}` | {col[1]} |")
    lines.append("")
    lines.append("## 5. Pendientes para gold")
    lines.append("- [ ] Construir panel completo municipio × período (con zeros para silentes)")
    lines.append("- [ ] Agregar nacidos vivos DANE (denominadores) — BLOQUEADO: requiere EEVV microdata manual")
    lines.append("- [ ] Agregar features Censo 2018 (NBI, ruralidad, etnia)")
    lines.append("- [ ] Agregar REPS (oferta UCI-O)")
    lines.append("- [ ] Agregar BDUA (cobertura aseguramiento)")

    report_path.write_text("\n".join(lines))
    print(f"[silver] ✓ {out_path}")
    print(f"[silver] rows={n_rows:,}, casos={n_casos:,}, municipios={n_munis:,}, deptos={n_dptos}")
    print(f"[silver] report → {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
