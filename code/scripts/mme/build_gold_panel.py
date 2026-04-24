"""
Gold MME — panel completo municipio × período (con silentes en 0).

Construye:
  - data/mme/gold/panel_muni_semestre.parquet   — granularidad Target C3 (15.7k filas esperadas)
  - data/mme/gold/panel_muni_semana.parquet     — granularidad Target C1 (410k filas esperadas)

Estrategia:
  - Cross join DIVIPOLA municipios × años 2016-2022 × períodos → marco completo.
  - Left join con silver agregado → conteo (con 0 para silentes).
  - Left join con bronze DANE EEVV (cuando existe) → nv_anual + indicadores estructurales.
  - Incluye coordenadas, tipo municipio, regímenes temporales.

Si bronze EEVV NO está poblado, las columnas de denominador y features estructurales
quedan en NULL (compatibilidad con la versión v1). El gold es siempre reproducible.

Pendiente post-EEVV (Fase MME-A items M-003..M-006):
  - NBI / pct_rural / pct_indigena / pct_afro (Censo 2018)
  - n_ips_nivel3 / tiene_uci_o (REPS MinSalud)
  - pct_subsidiado_muni (BDUA Supersalud — independiente del seg_social madre)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from _paths import REPO_ROOT, MME_DATA
SILVER_PATH = MME_DATA / "silver" / "mme_clean.parquet"
DIVIPOLA_PATH = MME_DATA / "bronze" / "divipola" / "municipios.parquet"
EEVV_GLOB = MME_DATA / "bronze" / "dane" / "eevv" / "year=*/part-*.parquet"
NBI_PATH = MME_DATA / "bronze" / "censo2018" / "nbi_municipios.parquet"
POBL_PATH = MME_DATA / "bronze" / "censo2018" / "poblacion_municipios.parquet"
BDUA_PATH = MME_DATA / "bronze" / "bdua" / "afiliados_muni_regimen.parquet"
REPS_IPS_PATH = MME_DATA / "bronze" / "reps" / "ips_por_muni.parquet"
REPS_CAP_PATH = MME_DATA / "bronze" / "reps" / "capacidad_por_muni.parquet"
MM_GLOB = MME_DATA / "bronze" / "sivigila_mm" / "year=*/part-*.parquet"
GOLD_DIR = MME_DATA / "gold"
YEAR_MIN, YEAR_MAX = 2016, 2022


def eevv_available() -> bool:
    """¿Hay parquet bronze EEVV poblado?"""
    eevv_dir = MME_DATA / "bronze" / "dane" / "eevv"
    if not eevv_dir.exists():
        return False
    parts = list(eevv_dir.glob("year=*/part-*.parquet"))
    return len(parts) > 0


def nbi_available() -> bool:
    """¿Hay parquet bronze Censo 2018 NBI?"""
    return NBI_PATH.exists()


def pobl_available() -> bool:
    """¿Hay parquet bronze Censo 2018 Población ajustada?"""
    return POBL_PATH.exists()


def bdua_available() -> bool:
    """¿Hay parquet bronze BDUA afiliados por muni?"""
    return BDUA_PATH.exists()


def reps_available() -> bool:
    """¿Hay ambos parquet REPS (IPS + capacidad)?"""
    return REPS_IPS_PATH.exists() and REPS_CAP_PATH.exists()


def mm_available() -> bool:
    """¿Hay parquet bronze SIVIGILA MM (evento 550)?"""
    mm_dir = MME_DATA / "bronze" / "sivigila_mm"
    if not mm_dir.exists():
        return False
    parts = list(mm_dir.glob("year=*/part-*.parquet"))
    return len(parts) > 0


def main() -> int:
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    has_eevv = eevv_available()
    has_nbi = nbi_available()
    has_mm = mm_available()
    has_pobl = pobl_available()
    has_bdua = bdua_available()
    has_reps = reps_available()
    print(f"[gold] bronze DANE EEVV disponible: {has_eevv}")
    print(f"[gold] bronze Censo 2018 NBI disponible: {has_nbi}")
    print(f"[gold] bronze Censo 2018 Población disponible: {has_pobl}")
    print(f"[gold] bronze SIVIGILA MM (evento 550) disponible: {has_mm}")
    print(f"[gold] bronze BDUA MinSalud disponible: {has_bdua}")
    print(f"[gold] bronze REPS MinSalud (IPS + capacidad) disponible: {has_reps}")

    con = duckdb.connect(":memory:")
    con.execute(f"CREATE VIEW silver AS SELECT * FROM parquet_scan('{SILVER_PATH}')")
    con.execute(f"CREATE VIEW divipola AS SELECT * FROM parquet_scan('{DIVIPOLA_PATH}')")

    if has_reps:
        con.execute(f"""
            CREATE VIEW reps_ips AS
            SELECT
                CAST(cod_mpio AS BIGINT) AS cod_mpio,
                n_ips_total, n_ips_nivel_1, n_ips_nivel_2, n_ips_nivel_3,
                n_ips_ese, n_ips_publica, n_ips_privada,
                tiene_ips_nivel_3, tiene_ips_nivel_2_o_3
            FROM parquet_scan('{REPS_IPS_PATH}')
        """)
        con.execute(f"""
            CREATE VIEW reps_cap AS
            SELECT
                CAST(cod_mpio AS BIGINT) AS cod_mpio,
                cap_camas_parto, cap_uci_adulto, cap_uci_neonatal,
                cap_salas_parto, cap_salas_cirugia,
                tiene_camas_parto, tiene_uci_adulto, tiene_uci_neonatal,
                tiene_salas_parto, tiene_salas_cirugia,
                score_capacidad_obstetrica
            FROM parquet_scan('{REPS_CAP_PATH}')
        """)
    else:
        con.execute("""
            CREATE VIEW reps_ips AS SELECT
              CAST(NULL AS BIGINT) AS cod_mpio,
              CAST(NULL AS BIGINT) AS n_ips_total,
              CAST(NULL AS BIGINT) AS n_ips_nivel_1,
              CAST(NULL AS BIGINT) AS n_ips_nivel_2,
              CAST(NULL AS BIGINT) AS n_ips_nivel_3,
              CAST(NULL AS BIGINT) AS n_ips_ese,
              CAST(NULL AS BIGINT) AS n_ips_publica,
              CAST(NULL AS BIGINT) AS n_ips_privada,
              CAST(NULL AS BIGINT) AS tiene_ips_nivel_3,
              CAST(NULL AS BIGINT) AS tiene_ips_nivel_2_o_3
            WHERE 1=0
        """)
        con.execute("""
            CREATE VIEW reps_cap AS SELECT
              CAST(NULL AS BIGINT) AS cod_mpio,
              CAST(NULL AS BIGINT) AS cap_camas_parto,
              CAST(NULL AS BIGINT) AS cap_uci_adulto,
              CAST(NULL AS BIGINT) AS cap_uci_neonatal,
              CAST(NULL AS BIGINT) AS cap_salas_parto,
              CAST(NULL AS BIGINT) AS cap_salas_cirugia,
              CAST(NULL AS BIGINT) AS tiene_camas_parto,
              CAST(NULL AS BIGINT) AS tiene_uci_adulto,
              CAST(NULL AS BIGINT) AS tiene_uci_neonatal,
              CAST(NULL AS BIGINT) AS tiene_salas_parto,
              CAST(NULL AS BIGINT) AS tiene_salas_cirugia,
              CAST(NULL AS BIGINT) AS score_capacidad_obstetrica
            WHERE 1=0
        """)

    if has_bdua:
        con.execute(f"""
            CREATE VIEW bdua AS
            SELECT
                CAST(cod_mpio AS BIGINT) AS cod_mpio,
                afiliados_total,
                pct_subsidiado_muni,
                pct_contributivo_muni,
                pct_excepcion_muni
            FROM parquet_scan('{BDUA_PATH}')
        """)
    else:
        con.execute("""
            CREATE VIEW bdua AS
            SELECT
                CAST(NULL AS BIGINT) AS cod_mpio,
                CAST(NULL AS BIGINT) AS afiliados_total,
                CAST(NULL AS DOUBLE) AS pct_subsidiado_muni,
                CAST(NULL AS DOUBLE) AS pct_contributivo_muni,
                CAST(NULL AS DOUBLE) AS pct_excepcion_muni
            WHERE 1=0
        """)

    if has_pobl:
        con.execute(f"""
            CREATE VIEW pobl AS
            SELECT
                CAST(cod_mpio AS BIGINT) AS cod_mpio,
                poblacion_total_2018,
                poblacion_cabecera_2018,
                poblacion_centros_rural_2018,
                pct_rural_pobl,
                pct_cabecera_pobl,
                omision_censal_total
            FROM parquet_scan('{POBL_PATH}')
        """)
    else:
        con.execute("""
            CREATE VIEW pobl AS
            SELECT
                CAST(NULL AS BIGINT)  AS cod_mpio,
                CAST(NULL AS BIGINT)  AS poblacion_total_2018,
                CAST(NULL AS BIGINT)  AS poblacion_cabecera_2018,
                CAST(NULL AS BIGINT)  AS poblacion_centros_rural_2018,
                CAST(NULL AS DOUBLE)  AS pct_rural_pobl,
                CAST(NULL AS DOUBLE)  AS pct_cabecera_pobl,
                CAST(NULL AS DOUBLE)  AS omision_censal_total
            WHERE 1=0
        """)

    if has_nbi:
        con.execute(f"""
            CREATE VIEW nbi AS
            SELECT
                CAST(cod_mpio AS BIGINT) AS cod_mpio,
                nbi_total_pct,
                nbi_miseria_pct,
                nbi_vivienda_pct,
                nbi_servicios_pct,
                nbi_hacinamiento_pct,
                nbi_inasistencia_pct,
                nbi_dependencia_pct,
                nbi_cabecera_pct,
                nbi_centros_rural_disperso_pct
            FROM parquet_scan('{NBI_PATH}')
        """)
    else:
        con.execute("""
            CREATE VIEW nbi AS
            SELECT
                CAST(NULL AS BIGINT) AS cod_mpio,
                CAST(NULL AS DOUBLE) AS nbi_total_pct,
                CAST(NULL AS DOUBLE) AS nbi_miseria_pct,
                CAST(NULL AS DOUBLE) AS nbi_vivienda_pct,
                CAST(NULL AS DOUBLE) AS nbi_servicios_pct,
                CAST(NULL AS DOUBLE) AS nbi_hacinamiento_pct,
                CAST(NULL AS DOUBLE) AS nbi_inasistencia_pct,
                CAST(NULL AS DOUBLE) AS nbi_dependencia_pct,
                CAST(NULL AS DOUBLE) AS nbi_cabecera_pct,
                CAST(NULL AS DOUBLE) AS nbi_centros_rural_disperso_pct
            WHERE 1=0
        """)

    if has_eevv:
        # Hive-aware: leer todos los year=YYYY de un solo glob.
        con.execute(
            f"CREATE VIEW eevv_raw AS SELECT * FROM parquet_scan('{EEVV_GLOB}', "
            "hive_partitioning=true, union_by_name=true)"
        )
        # Garantizar columna 'ano' confiable (el partition column 'year' a veces colisiona).
        con.execute("""
            CREATE VIEW eevv AS
            SELECT
                CAST(COALESCE(ano, year) AS INTEGER) AS ano,
                CAST(cod_mpio AS BIGINT) AS cod_mpio,
                CAST(nv_total AS BIGINT) AS nv_anual,
                COALESCE(edad_madre_lt15, 0)   AS nv_madre_lt15,
                COALESCE(edad_madre_15_19, 0)  AS nv_madre_15_19,
                COALESCE(edad_madre_gte35, 0)  AS nv_madre_gte35,
                COALESCE(cpn_gte4, 0)          AS nv_cpn_gte4,
                COALESCE(cesarea, 0)           AS nv_cesarea,
                COALESCE(rural_disperso, 0)    AS nv_rural_disperso,
                COALESCE(subsidiado, 0)        AS nv_subsidiado,
                COALESCE(indigena_madre, 0)    AS nv_indigena_madre,
                COALESCE(afro_madre, 0)        AS nv_afro_madre,
                COALESCE(bajo_peso, 0)         AS nv_bajo_peso,
                COALESCE(pretermino, 0)        AS nv_pretermino,
                edad_madre_avg,
                cpn_avg
            FROM eevv_raw
        """)
    else:
        # Vista vacía con el mismo schema, para que los joins compilen igual.
        con.execute("""
            CREATE VIEW eevv AS
            SELECT
                CAST(NULL AS INTEGER) AS ano,
                CAST(NULL AS BIGINT)  AS cod_mpio,
                CAST(NULL AS BIGINT)  AS nv_anual,
                CAST(NULL AS BIGINT)  AS nv_madre_lt15,
                CAST(NULL AS BIGINT)  AS nv_madre_15_19,
                CAST(NULL AS BIGINT)  AS nv_madre_gte35,
                CAST(NULL AS BIGINT)  AS nv_cpn_gte4,
                CAST(NULL AS BIGINT)  AS nv_cesarea,
                CAST(NULL AS BIGINT)  AS nv_rural_disperso,
                CAST(NULL AS BIGINT)  AS nv_subsidiado,
                CAST(NULL AS BIGINT)  AS nv_indigena_madre,
                CAST(NULL AS BIGINT)  AS nv_afro_madre,
                CAST(NULL AS BIGINT)  AS nv_bajo_peso,
                CAST(NULL AS BIGINT)  AS nv_pretermino,
                CAST(NULL AS DOUBLE)  AS edad_madre_avg,
                CAST(NULL AS DOUBLE)  AS cpn_avg
            WHERE 1=0
        """)

    # -------- Panel municipio-semestre --------
    con.execute(f"""
        CREATE VIEW panel_sem_frame AS
        SELECT
            CAST(d.cod_mpio AS BIGINT) AS cod_mpio,
            CAST(d.cod_dpto AS BIGINT) AS cod_dpto,
            d.nom_mpio,
            d.dpto AS nom_dpto,
            d.tipo_municipio,
            CAST(REPLACE(d.longitud, ',', '.') AS DOUBLE) AS longitud,
            CAST(REPLACE(d.latitud, ',', '.') AS DOUBLE) AS latitud,
            y.ano,
            s.semestre
        FROM divipola d
        CROSS JOIN range({YEAR_MIN}, {YEAR_MAX} + 1) AS y(ano)
        CROSS JOIN (SELECT 1 AS semestre UNION ALL SELECT 2) AS s
    """)

    con.execute("""
        CREATE VIEW silver_sem AS
        SELECT cod_mpio, ano, semestre, SUM(conteo) AS casos_mme
        FROM silver
        GROUP BY cod_mpio, ano, semestre
    """)

    # MM agregado con las MISMAS reglas de exclusión que silver (ver build_silver.py):
    # exterior (cod_dpto=1), procedencia desconocida (cod_dpto=0), municipio desconocido
    # (cod_mun % 1000 == 0), y remapeo Mapiripana → Inírida.
    if has_mm:
        con.execute(f"""
            CREATE VIEW mm_raw AS
            SELECT * FROM parquet_scan('{MM_GLOB}', hive_partitioning=1)
        """)
        con.execute("""
            CREATE VIEW mm_clean AS
            SELECT
                CASE WHEN cod_mun_o = 94663 THEN 94001 ELSE cod_mun_o END AS cod_mpio,
                ano,
                CASE WHEN semana BETWEEN 1 AND 26 THEN 1 ELSE 2 END AS semestre,
                semana,
                conteo
            FROM mm_raw
            WHERE cod_dpto_o NOT IN (0, 1)
              AND cod_mun_o % 1000 != 0
        """)
        con.execute("""
            CREATE VIEW mm_by_year AS
            SELECT cod_mpio, ano, SUM(conteo) AS casos_mm
            FROM mm_clean GROUP BY cod_mpio, ano
        """)
        con.execute("""
            CREATE VIEW mm_by_sem AS
            SELECT cod_mpio, ano, semestre, SUM(conteo) AS casos_mm
            FROM mm_clean GROUP BY cod_mpio, ano, semestre
        """)
    else:
        for view, keys in [
            ("mm_by_year", "cod_mpio BIGINT, ano INTEGER, casos_mm BIGINT"),
            ("mm_by_sem", "cod_mpio BIGINT, ano INTEGER, semestre SMALLINT, casos_mm BIGINT"),
        ]:
            col_names = [c.split()[0] for c in keys.split(",")]
            nulls = ", ".join(f"CAST(NULL AS {c.strip().split(' ', 1)[1]}) AS {c.strip().split(' ', 1)[0]}" for c in keys.split(","))
            con.execute(f"CREATE VIEW {view} AS SELECT {nulls} WHERE 1=0")

    panel_sem_path = GOLD_DIR / "panel_muni_semestre.parquet"
    # nv_esperados (semestre) = nv_anual / 2  → asume distribución uniforme intra-año.
    # Es una aproximación; en COVID 2020 puede ser ruidosa. Refinar en Fase MME-B.
    con.execute(f"""
        COPY (
            SELECT
                f.cod_mpio, f.cod_dpto, f.nom_mpio, f.nom_dpto, f.tipo_municipio,
                f.longitud, f.latitud,
                CAST(f.ano AS INTEGER) AS ano,
                CAST(f.semestre AS SMALLINT) AS semestre,
                COALESCE(s.casos_mme, 0)::INTEGER AS casos_mme,
                CASE WHEN s.casos_mme IS NULL THEN 1 ELSE 0 END AS is_silent_period,
                CASE WHEN f.ano BETWEEN 2020 AND 2022 THEN 1 ELSE 0 END AS covid_window,
                CASE WHEN f.ano >= 2022 THEN 1 ELSE 0 END AS post_c055,
                e.nv_anual                              AS nv_anual,
                CASE WHEN e.nv_anual IS NOT NULL
                     THEN e.nv_anual / 2.0 END          AS nv_esperados,
                CASE WHEN e.nv_anual IS NOT NULL AND e.nv_anual > 0
                     THEN COALESCE(s.casos_mme, 0) * 1000.0 / (e.nv_anual / 2.0)
                END                                     AS razon_mme_por_1000_nv,
                -- Features estructurales derivadas de EEVV (anuales, repetidos en ambos semestres)
                CASE WHEN e.nv_anual > 0 THEN e.nv_madre_lt15      * 100.0 / e.nv_anual END AS pct_madre_lt15_eevv,
                CASE WHEN e.nv_anual > 0 THEN e.nv_madre_15_19     * 100.0 / e.nv_anual END AS pct_madre_15_19_eevv,
                CASE WHEN e.nv_anual > 0 THEN e.nv_madre_gte35     * 100.0 / e.nv_anual END AS pct_madre_gte35_eevv,
                CASE WHEN e.nv_anual > 0 THEN e.nv_cpn_gte4        * 100.0 / e.nv_anual END AS pct_cpn_gte4_eevv,
                CASE WHEN e.nv_anual > 0 THEN e.nv_cesarea         * 100.0 / e.nv_anual END AS pct_cesarea_eevv,
                CASE WHEN e.nv_anual > 0 THEN e.nv_rural_disperso  * 100.0 / e.nv_anual END AS pct_rural_disperso_eevv,
                CASE WHEN e.nv_anual > 0 THEN e.nv_subsidiado      * 100.0 / e.nv_anual END AS pct_subsidiado_eevv,
                CASE WHEN e.nv_anual > 0 THEN e.nv_indigena_madre  * 100.0 / e.nv_anual END AS pct_indigena_madre_eevv,
                CASE WHEN e.nv_anual > 0 THEN e.nv_afro_madre      * 100.0 / e.nv_anual END AS pct_afro_madre_eevv,
                CASE WHEN e.nv_anual > 0 THEN e.nv_bajo_peso       * 100.0 / e.nv_anual END AS pct_bajo_peso_eevv,
                CASE WHEN e.nv_anual > 0 THEN e.nv_pretermino      * 100.0 / e.nv_anual END AS pct_pretermino_eevv,
                e.edad_madre_avg                        AS edad_madre_avg_eevv,
                e.cpn_avg                               AS cpn_avg_eevv,
                -- NBI Censo 2018 (estructural, invariante en el tiempo — M-003)
                n.nbi_total_pct                         AS nbi_total_pct,
                n.nbi_miseria_pct                       AS nbi_miseria_pct,
                n.nbi_vivienda_pct                      AS nbi_vivienda_pct,
                n.nbi_servicios_pct                     AS nbi_servicios_pct,
                n.nbi_hacinamiento_pct                  AS nbi_hacinamiento_pct,
                n.nbi_inasistencia_pct                  AS nbi_inasistencia_pct,
                n.nbi_dependencia_pct                   AS nbi_dependencia_pct,
                n.nbi_cabecera_pct                      AS nbi_cabecera_pct,
                n.nbi_centros_rural_disperso_pct        AS nbi_centros_rural_disperso_pct,
                -- Mortalidad Materna SIVIGILA evento 550 (M-002a — lead indicator outcome)
                COALESCE(ms.casos_mm, 0)::INTEGER       AS casos_mm_semestre,
                COALESCE(my.casos_mm, 0)::INTEGER       AS casos_mm_anual,
                -- Razón MM/100.000 NV (estándar INS; anualizada, mismo valor en ambos semestres)
                CASE WHEN e.nv_anual IS NOT NULL AND e.nv_anual > 0
                     THEN COALESCE(my.casos_mm, 0) * 100000.0 / e.nv_anual
                END                                     AS razon_mm_por_100000_nv_anual,
                -- Índice de letalidad MM/MME (%), anual. Meta OMS <1%.
                -- Denominador: casos MME del año completo (no semestre), para estabilidad.
                CASE WHEN my.casos_mm IS NOT NULL
                      AND (SELECT SUM(conteo) FROM silver WHERE silver.cod_mpio = f.cod_mpio AND silver.ano = f.ano) > 0
                     THEN my.casos_mm * 100.0 /
                          (SELECT SUM(conteo) FROM silver WHERE silver.cod_mpio = f.cod_mpio AND silver.ano = f.ano)
                END                                     AS indice_letalidad_mm_mme_pct_anual,
                -- Población ajustada CNPV 2018 (M-003b — ruralidad poblacional)
                p.poblacion_total_2018                  AS poblacion_total_2018,
                p.pct_rural_pobl                        AS pct_rural_pobl,
                p.pct_cabecera_pobl                     AS pct_cabecera_pobl,
                p.omision_censal_total                  AS omision_censal_censo2018,
                -- BDUA snapshot 2022-04 (M-006 — cobertura aseguramiento territorial)
                b.afiliados_total                       AS bdua_afiliados_total_2022,
                b.pct_subsidiado_muni                   AS pct_subsidiado_muni_bdua,
                b.pct_contributivo_muni                 AS pct_contributivo_muni_bdua,
                b.pct_excepcion_muni                    AS pct_excepcion_muni_bdua,
                -- REPS MinSalud (M-005 — Demora III: oferta obstétrica territorial)
                COALESCE(ri.n_ips_total, 0)::INTEGER    AS n_ips_total,
                COALESCE(ri.n_ips_nivel_1, 0)::INTEGER  AS n_ips_nivel_1,
                COALESCE(ri.n_ips_nivel_2, 0)::INTEGER  AS n_ips_nivel_2,
                COALESCE(ri.n_ips_nivel_3, 0)::INTEGER  AS n_ips_nivel_3,
                COALESCE(ri.n_ips_ese, 0)::INTEGER      AS n_ips_ese,
                COALESCE(ri.tiene_ips_nivel_3, 0)::INTEGER  AS tiene_ips_nivel_3,
                COALESCE(ri.tiene_ips_nivel_2_o_3, 0)::INTEGER AS tiene_ips_nivel_2_o_3,
                COALESCE(rc.cap_camas_parto, 0)::INTEGER     AS reps_camas_parto,
                COALESCE(rc.cap_uci_adulto, 0)::INTEGER      AS reps_uci_adulto,
                COALESCE(rc.cap_uci_neonatal, 0)::INTEGER    AS reps_uci_neonatal,
                COALESCE(rc.cap_salas_parto, 0)::INTEGER     AS reps_salas_parto,
                COALESCE(rc.cap_salas_cirugia, 0)::INTEGER   AS reps_salas_cirugia,
                COALESCE(rc.tiene_camas_parto, 0)::INTEGER   AS tiene_camas_parto,
                COALESCE(rc.tiene_uci_adulto, 0)::INTEGER    AS tiene_uci_adulto,
                COALESCE(rc.tiene_salas_cirugia, 0)::INTEGER AS tiene_salas_cirugia,
                COALESCE(rc.score_capacidad_obstetrica, 0)::INTEGER AS score_capacidad_obstetrica,
                -- Placeholders para fuentes pendientes (M-003c étnia, banco sangre)
                CAST(NULL AS DOUBLE)  AS pct_indigena_censo,
                CAST(NULL AS DOUBLE)  AS pct_afro_censo,
                CAST(NULL AS INTEGER) AS tiene_banco_sangre_reps
            FROM panel_sem_frame f
            LEFT JOIN silver_sem s
              ON f.cod_mpio = s.cod_mpio AND f.ano = s.ano AND f.semestre = s.semestre
            LEFT JOIN eevv e
              ON f.cod_mpio = e.cod_mpio AND f.ano = e.ano
            LEFT JOIN nbi n
              ON f.cod_mpio = n.cod_mpio
            LEFT JOIN pobl p
              ON f.cod_mpio = p.cod_mpio
            LEFT JOIN bdua b
              ON f.cod_mpio = b.cod_mpio
            LEFT JOIN reps_ips ri
              ON f.cod_mpio = ri.cod_mpio
            LEFT JOIN reps_cap rc
              ON f.cod_mpio = rc.cod_mpio
            LEFT JOIN mm_by_sem ms
              ON f.cod_mpio = ms.cod_mpio AND f.ano = ms.ano AND f.semestre = ms.semestre
            LEFT JOIN mm_by_year my
              ON f.cod_mpio = my.cod_mpio AND f.ano = my.ano
        ) TO '{panel_sem_path}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)

    # -------- Panel municipio-semana --------
    con.execute(f"""
        CREATE VIEW panel_semana_frame AS
        SELECT
            CAST(d.cod_mpio AS BIGINT) AS cod_mpio,
            CAST(d.cod_dpto AS BIGINT) AS cod_dpto,
            d.nom_mpio,
            d.dpto AS nom_dpto,
            CAST(REPLACE(d.longitud, ',', '.') AS DOUBLE) AS longitud,
            CAST(REPLACE(d.latitud, ',', '.') AS DOUBLE) AS latitud,
            y.ano,
            w.semana
        FROM divipola d
        CROSS JOIN range({YEAR_MIN}, {YEAR_MAX} + 1) AS y(ano)
        CROSS JOIN range(1, 53) AS w(semana)
    """)

    con.execute("""
        CREATE VIEW silver_semana AS
        SELECT cod_mpio, ano, semana, SUM(conteo) AS casos_mme
        FROM silver
        GROUP BY cod_mpio, ano, semana
    """)

    panel_semana_path = GOLD_DIR / "panel_muni_semana.parquet"
    # nv_esperados (semana) = nv_anual / 52
    con.execute(f"""
        COPY (
            SELECT
                f.cod_mpio, f.cod_dpto, f.nom_mpio, f.nom_dpto,
                f.longitud, f.latitud,
                CAST(f.ano AS INTEGER) AS ano,
                CAST(f.semana AS SMALLINT) AS semana,
                COALESCE(s.casos_mme, 0)::INTEGER AS casos_mme,
                CASE WHEN s.casos_mme IS NULL THEN 1 ELSE 0 END AS is_silent_period,
                CASE WHEN f.ano BETWEEN 2020 AND 2022 THEN 1 ELSE 0 END AS covid_window,
                CASE WHEN f.ano >= 2022 THEN 1 ELSE 0 END AS post_c055,
                e.nv_anual                              AS nv_anual,
                CASE WHEN e.nv_anual IS NOT NULL
                     THEN e.nv_anual / 52.0 END         AS nv_esperados,
                CASE WHEN e.nv_anual IS NOT NULL AND e.nv_anual > 0
                     THEN COALESCE(s.casos_mme, 0) * 1000.0 / (e.nv_anual / 52.0)
                END                                     AS razon_mme_por_1000_nv
            FROM panel_semana_frame f
            LEFT JOIN silver_semana s
              ON f.cod_mpio = s.cod_mpio AND f.ano = s.ano AND f.semana = s.semana
            LEFT JOIN eevv e
              ON f.cod_mpio = e.cod_mpio AND f.ano = e.ano
        ) TO '{panel_semana_path}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)

    # Métricas
    n_sem = con.execute(f"SELECT COUNT(*) FROM parquet_scan('{panel_sem_path}')").fetchone()[0]
    zeros_sem = con.execute(f"SELECT SUM(is_silent_period) FROM parquet_scan('{panel_sem_path}')").fetchone()[0]
    nv_cov_sem = con.execute(
        f"SELECT 100.0*SUM(CASE WHEN nv_anual IS NOT NULL THEN 1 ELSE 0 END)/COUNT(*) FROM parquet_scan('{panel_sem_path}')"
    ).fetchone()[0]
    nbi_cov_sem = con.execute(
        f"SELECT 100.0*SUM(CASE WHEN nbi_total_pct IS NOT NULL THEN 1 ELSE 0 END)/COUNT(*) FROM parquet_scan('{panel_sem_path}')"
    ).fetchone()[0]
    n_sw = con.execute(f"SELECT COUNT(*) FROM parquet_scan('{panel_semana_path}')").fetchone()[0]
    zeros_sw = con.execute(f"SELECT SUM(is_silent_period) FROM parquet_scan('{panel_semana_path}')").fetchone()[0]

    # Manifest gold
    manifest = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_silver": str(SILVER_PATH),
        "divipola_catalog": str(DIVIPOLA_PATH),
        "eevv_joined": has_eevv,
        "nbi_joined": has_nbi,
        "pobl_joined": has_pobl,
        "bdua_joined": has_bdua,
        "reps_joined": has_reps,
        "mm_joined": has_mm,
        "year_range": [YEAR_MIN, YEAR_MAX],
        "panels": {
            "panel_muni_semestre": {
                "path": str(panel_sem_path),
                "row_count": n_sem,
                "zero_periods": int(zeros_sem),
                "zero_ratio": round(zeros_sem / n_sem, 4),
                "nv_coverage_pct": round(float(nv_cov_sem or 0), 2),
                "nbi_coverage_pct": round(float(nbi_cov_sem or 0), 2),
                "target": "C3 vulnerabilidad obstétrica municipal",
            },
            "panel_muni_semana": {
                "path": str(panel_semana_path),
                "row_count": n_sw,
                "zero_periods": int(zeros_sw),
                "zero_ratio": round(zeros_sw / n_sw, 4),
                "target": "C1 outbreak detection",
            },
        },
        "pending_joins_for_next_iteration": {
            "pct_rural_censo": "DANE Censo 2018 (M-003b, separado de NBI)",
            "pct_indigena / pct_afro": "DANE Censo 2018 grupos étnicos (M-003b)",
            "n_ips_nivel3": "REPS MinSalud (M-005)",
            "tiene_uci_o": "REPS MinSalud (M-005)",
            "pct_subsidiado_muni": "BDUA Supersalud (M-006) — independiente del seg_social madre EEVV",
        },
        "notes": [
            "razon_mme_por_1000_nv calculada como casos_periodo * 1000 / nv_esperados_periodo.",
            "nv_esperados_semestre = nv_anual / 2 (asume distribución uniforme intra-año; revisar para 2020 COVID).",
            "nv_esperados_semana = nv_anual / 52.",
            "Si EEVV no está poblado, nv_anual / nv_esperados / razon quedan NULL.",
            "Las columnas pct_*_eevv son features anuales repetidas en cada período del año (mismo valor para semestre 1 y 2).",
        ],
    }
    (GOLD_DIR / "_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    print(f"[gold] panel_muni_semestre: {n_sem:,} filas ({100*zeros_sem/n_sem:.1f}% silentes, {nv_cov_sem or 0:.1f}% con NV)")
    print(f"[gold] panel_muni_semana:   {n_sw:,} filas ({100*zeros_sw/n_sw:.1f}% silentes)")
    print(f"[gold] ✓ manifest → {(GOLD_DIR / '_manifest.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
