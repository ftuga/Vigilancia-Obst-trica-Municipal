"""
QA bronze MME — calidad de datos del ingreso SIVIGILA.

Valida:
  - Schema y tipos
  - Nulos por columna
  - Rango temporal (años, semanas epidemiológicas)
  - Cobertura geográfica (municipios, departamentos únicos)
  - Duplicados (municipio × semana × año)
  - Outliers de conteo
  - Completitud de años y semanas (gaps temporales)
  - Coherencia: todos los registros son evento 549

Output:
  reports/mme/bronze_qa_<fecha>.md  (reporte legible)
  stdout                             (resumen rápido)

Uso:
  uv run python scripts/mme/qa_bronze.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from _paths import REPO_ROOT, MME_DATA, MME_REPORTS
BRONZE_GLOB = MME_DATA / "bronze" / "year=*" / "*.parquet"
REPORTS_DIR = MME_REPORTS


def _q(con: duckdb.DuckDBPyConnection, sql: str):
    return con.execute(sql).fetchall()


def _qdf(con: duckdb.DuckDBPyConnection, sql: str):
    return con.execute(sql).df()


def main() -> int:
    parquet_glob = str(BRONZE_GLOB).replace("[", "[").replace("]", "]")
    if not list(BRONZE_GLOB.parent.parent.glob("year=*/*.parquet")):
        print(f"⚠ no parquets encontrados en {BRONZE_GLOB}", file=sys.stderr)
        return 2

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report_path = REPORTS_DIR / f"bronze_qa_{today}.md"

    con = duckdb.connect(":memory:")
    con.execute(f"CREATE VIEW bronze AS SELECT * FROM parquet_scan('{parquet_glob}', hive_partitioning=1)")

    total_rows = _q(con, "SELECT COUNT(*) FROM bronze")[0][0]
    cols = _q(con, "DESCRIBE bronze")

    rows_per_year = _qdf(con, "SELECT ano, COUNT(*) AS n FROM bronze GROUP BY ano ORDER BY ano")
    rows_per_dept = _qdf(con, """
        SELECT departamento_ocurrencia, COUNT(*) AS n_rows, SUM(conteo) AS total_casos
        FROM bronze GROUP BY departamento_ocurrencia ORDER BY total_casos DESC
    """)
    n_dept = _q(con, "SELECT COUNT(DISTINCT cod_dpto_o) FROM bronze")[0][0]
    n_muni = _q(con, "SELECT COUNT(DISTINCT cod_mun_o) FROM bronze")[0][0]

    nulls = _qdf(con, """
        SELECT
            COUNT(*) - COUNT(cod_eve) AS null_cod_eve,
            COUNT(*) - COUNT(nombre_evento) AS null_nombre_evento,
            COUNT(*) - COUNT(semana) AS null_semana,
            COUNT(*) - COUNT(ano) AS null_ano,
            COUNT(*) - COUNT(cod_dpto_o) AS null_cod_dpto,
            COUNT(*) - COUNT(cod_mun_o) AS null_cod_mun,
            COUNT(*) - COUNT(departamento_ocurrencia) AS null_dpto,
            COUNT(*) - COUNT(municipio_ocurrencia) AS null_muni,
            COUNT(*) - COUNT(conteo) AS null_conteo
        FROM bronze
    """)

    dup_keys = _q(con, """
        SELECT COUNT(*) FROM (
            SELECT ano, semana, cod_dpto_o, cod_mun_o, COUNT(*) AS c
            FROM bronze
            GROUP BY ano, semana, cod_dpto_o, cod_mun_o
            HAVING c > 1
        )
    """)[0][0]

    conteo_stats = _qdf(con, """
        SELECT
            MIN(conteo) AS min_c, MAX(conteo) AS max_c,
            AVG(conteo)::DOUBLE AS mean_c,
            APPROX_QUANTILE(conteo, 0.5) AS p50,
            APPROX_QUANTILE(conteo, 0.95) AS p95,
            APPROX_QUANTILE(conteo, 0.99) AS p99
        FROM bronze
    """)

    outliers = _qdf(con, """
        SELECT ano, semana, departamento_ocurrencia, municipio_ocurrencia, conteo
        FROM bronze
        WHERE conteo >= 20
        ORDER BY conteo DESC
        LIMIT 20
    """)

    week_range = _qdf(con, "SELECT MIN(semana) AS wmin, MAX(semana) AS wmax FROM bronze")
    year_range = _qdf(con, "SELECT MIN(ano) AS ymin, MAX(ano) AS ymax FROM bronze")

    gaps = _qdf(con, """
        WITH expected AS (
            SELECT y AS ano, w AS semana
            FROM range(
                (SELECT MIN(ano) FROM bronze),
                (SELECT MAX(ano) FROM bronze) + 1
            ) AS t(y)
            CROSS JOIN range(1, 54) AS s(w)
        ),
        observed AS (
            SELECT DISTINCT ano, semana FROM bronze
        )
        SELECT e.ano, e.semana
        FROM expected e
        LEFT JOIN observed o ON e.ano = o.ano AND e.semana = o.semana
        WHERE o.ano IS NULL
        ORDER BY e.ano, e.semana
    """)

    unique_events = _qdf(con, """
        SELECT cod_eve, nombre_evento, COUNT(*) AS n
        FROM bronze GROUP BY cod_eve, nombre_evento
    """)

    # Municipios silentes: que NO aparecen nunca (0 casos en toda la ventana)
    # requiere catálogo externo DIVIPOLA — placeholder para silver
    silent_counties_note = "N/A en bronze (requiere join con DIVIPOLA en silver)"

    # Municipios con pocos registros (posible silente parcial)
    low_activity = _qdf(con, """
        SELECT departamento_ocurrencia, municipio_ocurrencia, cod_mun_o, COUNT(*) AS n_records
        FROM bronze
        GROUP BY departamento_ocurrencia, municipio_ocurrencia, cod_mun_o
        HAVING COUNT(*) <= 3
        ORDER BY n_records ASC, departamento_ocurrencia, municipio_ocurrencia
        LIMIT 30
    """)

    # Build markdown report
    lines: list[str] = []
    lines.append(f"# QA Bronze — MME Colombia")
    lines.append("")
    lines.append(f"**Generado**: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"**Fuente**: `data/mme/bronze/year=*/part-*.parquet`")
    lines.append("")
    lines.append("## 1. Volumen y schema")
    lines.append(f"- **Total filas**: {total_rows:,}")
    lines.append(f"- **Columnas**: {len(cols)}")
    lines.append("")
    lines.append("### Schema")
    lines.append("| columna | tipo |")
    lines.append("|---|---|")
    for col in cols:
        name = col[0]
        dtype = col[1]
        lines.append(f"| `{name}` | {dtype} |")
    lines.append("")
    lines.append("## 2. Coherencia del filtro")
    lines.append(f"- **Eventos distintos en la data** (deberían ser solo 549 MME):")
    lines.append("")
    lines.append("| cod_eve | nombre_evento | n filas |")
    lines.append("|---|---|---|")
    for _, r in unique_events.iterrows():
        lines.append(f"| {r['cod_eve']} | {r['nombre_evento']} | {r['n']:,} |")
    lines.append("")
    lines.append("## 3. Cobertura temporal")
    y = year_range.iloc[0]
    w = week_range.iloc[0]
    lines.append(f"- **Años**: {int(y.ymin)} → {int(y.ymax)}")
    lines.append(f"- **Semanas epidemiológicas**: {int(w.wmin)} → {int(w.wmax)}")
    lines.append("")
    lines.append("### Filas por año")
    lines.append("| año | filas |")
    lines.append("|---|---|")
    for _, r in rows_per_year.iterrows():
        lines.append(f"| {int(r['ano'])} | {int(r['n']):,} |")
    lines.append("")
    lines.append(f"### Gaps temporales (año-semana sin ningún registro)")
    if len(gaps) == 0:
        lines.append("- Sin gaps — todas las combinaciones año×semana tienen al menos 1 fila ✓")
    else:
        lines.append(f"- **{len(gaps)} combinaciones año-semana sin datos** (puede indicar subregistro nacional o semanas previas al año del primer dato)")
        lines.append("")
        lines.append("Primeros 10:")
        for _, r in gaps.head(10).iterrows():
            lines.append(f"  - {int(r['ano'])} semana {int(r['semana'])}")
    lines.append("")
    lines.append("## 4. Cobertura geográfica")
    lines.append(f"- **Departamentos únicos**: {n_dept}")
    lines.append(f"- **Municipios únicos**: {n_muni:,}")
    lines.append(f"- **Municipios silentes**: {silent_counties_note}")
    lines.append("")
    lines.append("### Top 15 departamentos por casos acumulados")
    lines.append("| departamento | n filas | total casos |")
    lines.append("|---|---|---|")
    for _, r in rows_per_dept.head(15).iterrows():
        dpto = r["departamento_ocurrencia"] or "(null)"
        lines.append(f"| {dpto} | {int(r['n_rows']):,} | {int(r['total_casos']):,} |")
    lines.append("")
    lines.append(f"### Municipios con baja actividad (≤3 filas totales)")
    lines.append(f"Total listados: {len(low_activity)}")
    if len(low_activity) > 0:
        lines.append("")
        lines.append("| departamento | municipio | cod_mun | n filas |")
        lines.append("|---|---|---|---|")
        for _, r in low_activity.head(20).iterrows():
            lines.append(
                f"| {r['departamento_ocurrencia']} | {r['municipio_ocurrencia']} | "
                f"{r['cod_mun_o']} | {r['n_records']} |"
            )
    lines.append("")
    lines.append("## 5. Nulos por columna")
    n = nulls.iloc[0]
    lines.append("| columna | nulos |")
    lines.append("|---|---|")
    for col in n.index:
        lines.append(f"| `{col.replace('null_','')}` | {int(n[col]):,} |")
    lines.append("")
    lines.append("## 6. Duplicados en clave lógica (año × semana × municipio)")
    if dup_keys == 0:
        lines.append("- Sin duplicados ✓")
    else:
        lines.append(f"- **{dup_keys:,} claves con múltiples filas** — revisar antes de silver")
    lines.append("")
    lines.append("## 7. Distribución de `conteo`")
    c = conteo_stats.iloc[0]
    lines.append(f"- min={int(c['min_c'])}, max={int(c['max_c'])}, mean={c['mean_c']:.2f}, "
                 f"p50={int(c['p50'])}, p95={int(c['p95'])}, p99={int(c['p99'])}")
    lines.append("")
    lines.append("### Top 20 registros con mayor `conteo` (posibles outliers o centros de referencia)")
    lines.append("| año | semana | departamento | municipio | conteo |")
    lines.append("|---|---|---|---|---|")
    for _, r in outliers.iterrows():
        lines.append(
            f"| {int(r['ano'])} | {int(r['semana'])} | {r['departamento_ocurrencia']} | "
            f"{r['municipio_ocurrencia']} | {int(r['conteo'])} |"
        )
    lines.append("")
    lines.append("## 8. Verificaciones pendientes para silver")
    lines.append("- [ ] Join con catálogo DIVIPOLA DANE (códigos municipio completos de 5 dígitos)")
    lines.append("- [ ] Join con nacidos vivos DANE por municipio×año → razón MME/1000 NV")
    lines.append("- [ ] Identificación de municipios silentes (en DIVIPOLA pero ausentes del bronze)")
    lines.append("- [ ] Ajuste de semana epidemiológica ISO 8601 / CDC")
    lines.append("- [ ] Marcado de régimen temporal: `covid_window`, `post_c055`, `post_paremm`")
    lines.append("")

    report_path.write_text("\n".join(lines))
    print(f"✓ reporte en {report_path}")
    print()
    print(f"total_filas: {total_rows:,}")
    print(f"años: {int(y.ymin)}-{int(y.ymax)}  |  departamentos: {n_dept}  |  municipios: {n_muni:,}")
    print(f"duplicados_clave_lógica: {dup_keys}")
    print(f"gaps_año_semana: {len(gaps)}")
    print(f"eventos_distintos: {len(unique_events)}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
