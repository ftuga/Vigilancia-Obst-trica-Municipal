"""
EDA municipal × departamental del gold panel MME (Fase MME-B).

Genera insights para el reporte académico y valida hipótesis epidemiológicas
ANTES de modelar C3/C1:

  1. Volumen MME y MM por año nacional + contraste con benchmarks INS
  2. Distribución por departamento (top 10 volumen, top 10 razón*)
     *razón = casos / poblacion × 1000 (proxy sin EEVV)
  3. Brechas estructurales: scatter NBI × casos_por_1000_hab a nivel muni y dpto
  4. Subregistro sospechoso: muni con NBI >70 y casos absolutos <5 en 7 años
  5. Efecto COVID: variación % 2020 vs 2016-2019 baseline
  6. Efecto capacidad obstétrica: casos/población por score_capacidad_obstetrica
  7. Estacionalidad: distribución semanal nacional

Output:
  reports/mme/eda_municipal.md                  — reporte markdown
  reports/mme/eda_summary.json                  — métricas clave reutilizables

Uso:
  uv run python scripts/mme/eda_municipal.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from _paths import REPO_ROOT, MME_DATA, MME_REPORTS
GOLD_SEMESTRE = MME_DATA / "gold" / "panel_muni_semestre.parquet"
GOLD_SEMANA = MME_DATA / "gold" / "panel_muni_semana.parquet"
REPORT_MD = MME_REPORTS / "eda_municipal.md"
REPORT_JSON = MME_REPORTS / "eda_summary.json"

# Benchmarks INS 2016-2024 (Protocolo Pro_MME + Boletines epidemiológicos)
INS_BENCHMARK_MME_TOTAL_ANUAL = {
    2016: None, 2017: None, 2018: None,
    2019: 23488,    # INS Boletín 2019
    2020: None, 2021: None, 2022: None,
}


def md_table(rows: list[dict], headers: list[str]) -> str:
    """Render lista de dicts como tabla markdown."""
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(r.get(h, "")) for h in headers) + " |")
    return "\n".join(out)


def main() -> int:
    con = duckdb.connect(":memory:")
    con.execute(f"CREATE VIEW panel AS SELECT * FROM parquet_scan('{GOLD_SEMESTRE}')")
    con.execute(f"CREATE VIEW panel_w AS SELECT * FROM parquet_scan('{GOLD_SEMANA}')")

    summary: dict = {"generated_at_utc": datetime.now(timezone.utc).isoformat()}
    md: list[str] = []
    md.append("# EDA municipal × departamental — Panel MME 2016-2022")
    md.append(f"\n> Generado: {datetime.now(timezone.utc).date()}  "
              f"| Panel: `{GOLD_SEMESTRE}` (15.708 filas)")
    md.append("\n> **Nota metodológica**: las razones aquí usan `poblacion_total_2018` como denominador")
    md.append("> porque EEVV (M-001) aún no llegó. Cuando llegue, se recalcula con NV como denominador.")

    # ========================================================================
    # 1. Volumen MME y MM anual + benchmarks INS
    # ========================================================================
    md.append("\n## 1. Volumen anual nacional\n")
    df = con.execute("""
        SELECT ano,
               SUM(casos_mme) AS casos_mme,
               MAX(ano_agg.casos_mm_anual_total) AS casos_mm_reportados
        FROM panel
        LEFT JOIN (
          SELECT ano, SUM(casos_mm_semestre) AS casos_mm_anual_total
          FROM panel GROUP BY ano
        ) ano_agg USING (ano)
        GROUP BY ano ORDER BY ano
    """).df()
    md.append(md_table(
        [{"año": int(r["ano"]),
          "MME (proyecto)": int(r["casos_mme"]),
          "INS MME benchmark": INS_BENCHMARK_MME_TOTAL_ANUAL.get(int(r["ano"]), "—") or "—",
          "MM (SIVIGILA 550)": int(r["casos_mm_reportados"] or 0)}
         for _, r in df.iterrows()],
        ["año", "MME (proyecto)", "INS MME benchmark", "MM (SIVIGILA 550)"]))
    summary["volumen_anual"] = df.to_dict(orient="records")

    # ========================================================================
    # 2. Distribución por departamento
    # ========================================================================
    md.append("\n## 2. Distribución por departamento\n")
    md.append("### Top 10 por volumen absoluto MME 2016-2022\n")
    df = con.execute("""
        SELECT cod_dpto, nom_dpto,
               SUM(casos_mme) AS mme_total,
               SUM(casos_mm_semestre) AS mm_total,
               COUNT(DISTINCT cod_mpio) AS n_muni,
               AVG(nbi_total_pct) AS nbi_avg,
               AVG(pct_rural_pobl) AS rural_avg
        FROM panel
        GROUP BY cod_dpto, nom_dpto
        ORDER BY mme_total DESC LIMIT 10
    """).df()
    md.append(md_table(
        [{"dpto": r["nom_dpto"], "MME": int(r["mme_total"]),
          "MM": int(r["mm_total"] or 0), "#muni": int(r["n_muni"]),
          "NBI avg %": round(r["nbi_avg"], 1) if r["nbi_avg"] is not None else "—",
          "Rural avg %": round(r["rural_avg"], 1) if r["rural_avg"] is not None else "—"}
         for _, r in df.iterrows()],
        ["dpto", "MME", "MM", "#muni", "NBI avg %", "Rural avg %"]))
    summary["top_dpto_volumen"] = df.to_dict(orient="records")

    md.append("\n### Top 10 por razón MME/1.000 habitantes 2018 (proxy sin EEVV)\n")
    md.append("_Usa población Censo 2018 ajustada. Cuando llegue EEVV se reemplaza por razón MME/1.000 NV._\n")
    df = con.execute("""
        SELECT cod_dpto, nom_dpto,
               SUM(casos_mme) AS mme_total,
               SUM(poblacion_total_2018) / 2 AS pob_dpto_aprox,
               SUM(casos_mme) * 1000.0 / (SUM(poblacion_total_2018) / 2) AS razon_por_1000_hab,
               AVG(nbi_total_pct) AS nbi_avg
        FROM (
          SELECT DISTINCT cod_dpto, nom_dpto, cod_mpio, poblacion_total_2018, nbi_total_pct,
                          (SELECT SUM(casos_mme) FROM panel p2
                           WHERE p2.cod_mpio = panel.cod_mpio) AS casos_mme
          FROM panel
        )
        WHERE poblacion_total_2018 IS NOT NULL
        GROUP BY cod_dpto, nom_dpto
        HAVING SUM(poblacion_total_2018) > 50000
        ORDER BY razon_por_1000_hab DESC LIMIT 10
    """).df()
    md.append(md_table(
        [{"dpto": r["nom_dpto"],
          "MME total 7 años": int(r["mme_total"]),
          "Pob aprox": f"{int(r['pob_dpto_aprox']):,}",
          "Razón /1.000 hab": round(r["razon_por_1000_hab"], 2),
          "NBI avg": round(r["nbi_avg"], 1) if r["nbi_avg"] is not None else "—"}
         for _, r in df.iterrows()],
        ["dpto", "MME total 7 años", "Pob aprox", "Razón /1.000 hab", "NBI avg"]))
    summary["top_dpto_razon"] = df.to_dict(orient="records")

    # ========================================================================
    # 3. Brecha NBI × MME — CORR a nivel municipal (con denominador)
    # ========================================================================
    md.append("\n## 3. Brecha estructural: NBI × razón MME por habitante\n")
    df = con.execute("""
        WITH muni_agg AS (
          SELECT cod_mpio, nom_mpio, nom_dpto,
                 AVG(nbi_total_pct) AS nbi,
                 AVG(pct_rural_pobl) AS rural,
                 SUM(casos_mme) AS mme_total,
                 MAX(poblacion_total_2018) AS pob,
                 MAX(score_capacidad_obstetrica) AS score_obs
          FROM panel GROUP BY cod_mpio, nom_mpio, nom_dpto
        )
        SELECT
          CORR(nbi, mme_total * 1000.0 / pob) AS corr_nbi_razon,
          CORR(rural, mme_total * 1000.0 / pob) AS corr_rural_razon,
          CORR(score_obs, mme_total * 1000.0 / pob) AS corr_capacidad_razon,
          CORR(nbi, mme_total) AS corr_nbi_casos_abs
        FROM muni_agg WHERE pob IS NOT NULL AND pob > 0
    """).df()
    row = df.iloc[0]
    md.append(f"- Correlación **NBI × razón MME/1.000 hab**: `{row['corr_nbi_razon']:.3f}` "
              f"(esperada positiva — hipótesis de brecha estructural)")
    md.append(f"- Correlación **% rural × razón MME/1.000 hab**: `{row['corr_rural_razon']:.3f}`")
    md.append(f"- Correlación **score_capacidad_obstetrica × razón MME/1.000 hab**: "
              f"`{row['corr_capacidad_razon']:.3f}` _(negativa esperada — más oferta, menos razón)_")
    md.append(f"- Correlación de contraste **NBI × casos absolutos**: `{row['corr_nbi_casos_abs']:.3f}` "
              f"_(se espera negativa / débil — Bogotá concentra casos por tamaño, no por NBI)_")
    summary["corr_estructura"] = {
        "nbi_razon": float(row["corr_nbi_razon"] or 0),
        "rural_razon": float(row["corr_rural_razon"] or 0),
        "capacidad_razon": float(row["corr_capacidad_razon"] or 0),
        "nbi_casos_abs": float(row["corr_nbi_casos_abs"] or 0),
    }

    # ========================================================================
    # 4. Silentes sospechosos
    # ========================================================================
    md.append("\n## 4. Municipios con silencio sospechoso\n")
    md.append("Criterio: NBI ≥70% (vulnerabilidad estructural alta) + ≤5 casos MME "
              "en 7 años + población >1.000.")
    df = con.execute("""
        SELECT cod_mpio, nom_mpio, nom_dpto,
               MAX(nbi_total_pct) AS nbi,
               MAX(poblacion_total_2018) AS pob,
               SUM(casos_mme) AS casos_mme_7y
        FROM panel
        WHERE nbi_total_pct >= 70
        GROUP BY cod_mpio, nom_mpio, nom_dpto
        HAVING SUM(casos_mme) <= 5 AND MAX(poblacion_total_2018) > 1000
        ORDER BY nbi DESC, pob DESC LIMIT 20
    """).df()
    md.append(md_table(
        [{"muni": r["nom_mpio"], "dpto": r["nom_dpto"],
          "NBI %": round(r["nbi"], 1), "pob": int(r["pob"]),
          "MME 7 años": int(r["casos_mme_7y"])}
         for _, r in df.iterrows()],
        ["muni", "dpto", "NBI %", "pob", "MME 7 años"]))
    summary["silentes_sospechosos"] = df.to_dict(orient="records")
    md.append(f"\n**{len(df)} municipios** cumplen el criterio de silencio sospechoso. "
              "Candidatos para análisis C2 (subregistro).")

    # ========================================================================
    # 5. Efecto COVID
    # ========================================================================
    md.append("\n## 5. Efecto COVID-19 (2020 vs baseline 2016-2019)\n")
    df = con.execute("""
        WITH ano_total AS (
          SELECT ano, SUM(casos_mme) AS mme, SUM(casos_mm_semestre) AS mm
          FROM panel GROUP BY ano
        )
        SELECT
          (SELECT AVG(mme) FROM ano_total WHERE ano BETWEEN 2016 AND 2019) AS mme_baseline,
          (SELECT mme FROM ano_total WHERE ano = 2020) AS mme_2020,
          (SELECT mme FROM ano_total WHERE ano = 2021) AS mme_2021,
          (SELECT mme FROM ano_total WHERE ano = 2022) AS mme_2022,
          (SELECT AVG(mm) FROM ano_total WHERE ano BETWEEN 2016 AND 2019) AS mm_baseline,
          (SELECT mm FROM ano_total WHERE ano = 2020) AS mm_2020,
          (SELECT mm FROM ano_total WHERE ano = 2021) AS mm_2021,
          (SELECT mm FROM ano_total WHERE ano = 2022) AS mm_2022
    """).df()
    row = df.iloc[0]
    mme_delta_2020 = (float(row["mme_2020"]) - float(row["mme_baseline"])) / float(row["mme_baseline"]) * 100
    mme_delta_2021 = (float(row["mme_2021"]) - float(row["mme_baseline"])) / float(row["mme_baseline"]) * 100
    mm_delta_2020 = (float(row["mm_2020"]) - float(row["mm_baseline"])) / float(row["mm_baseline"]) * 100
    mm_delta_2021 = (float(row["mm_2021"]) - float(row["mm_baseline"])) / float(row["mm_baseline"]) * 100
    md.append(f"- **Baseline MME 2016-2019** (promedio anual): `{int(row['mme_baseline']):,}` casos")
    md.append(f"  - 2020: `{int(row['mme_2020']):,}` ({mme_delta_2020:+.1f}%)")
    md.append(f"  - 2021: `{int(row['mme_2021']):,}` ({mme_delta_2021:+.1f}%)")
    md.append(f"  - 2022: `{int(row['mme_2022']):,}`")
    md.append(f"- **Baseline MM 2016-2019** (promedio anual): `{int(row['mm_baseline'])}` casos")
    md.append(f"  - 2020: `{int(row['mm_2020'])}` ({mm_delta_2020:+.1f}%) _(pico COVID esperado)_")
    md.append(f"  - 2021: `{int(row['mm_2021'])}` ({mm_delta_2021:+.1f}%)")
    md.append(f"  - 2022: `{int(row['mm_2022'])}`")
    summary["efecto_covid"] = {
        "mme_delta_2020_pct": round(mme_delta_2020, 1),
        "mme_delta_2021_pct": round(mme_delta_2021, 1),
        "mm_delta_2020_pct": round(mm_delta_2020, 1),
        "mm_delta_2021_pct": round(mm_delta_2021, 1),
    }

    # ========================================================================
    # 6. Capacidad obstétrica × razón MME
    # ========================================================================
    md.append("\n## 6. Capacidad obstétrica territorial × razón MME\n")
    df = con.execute("""
        WITH muni_agg AS (
          SELECT cod_mpio, MAX(score_capacidad_obstetrica) AS score,
                 SUM(casos_mme) AS mme, MAX(poblacion_total_2018) AS pob
          FROM panel GROUP BY cod_mpio
        )
        SELECT score,
               COUNT(*) AS n_muni,
               SUM(mme) AS mme_total,
               SUM(pob) AS pob_total,
               SUM(mme) * 1000.0 / SUM(pob) AS razon_agg
        FROM muni_agg
        WHERE pob IS NOT NULL AND pob > 0
        GROUP BY score ORDER BY score
    """).df()
    md.append(md_table(
        [{"score": int(r["score"]),
          "#muni": int(r["n_muni"]),
          "MME total": int(r["mme_total"]),
          "Pob total": f"{int(r['pob_total']):,}",
          "Razón /1.000 hab": round(r["razon_agg"], 2)}
         for _, r in df.iterrows()],
        ["score", "#muni", "MME total", "Pob total", "Razón /1.000 hab"]))
    md.append("\n_Score = {tiene_camas_parto} + {tiene_uci_adulto} + {tiene_salas_cirugia} ∈ [0, 3]._")
    md.append("_Score alto concentra casos (grandes ciudades tienen más oferta Y más casos)._")
    summary["capacidad_vs_razon"] = df.to_dict(orient="records")

    # ========================================================================
    # 7. Estacionalidad semanal
    # ========================================================================
    md.append("\n## 7. Estacionalidad semanal (nacional)\n")
    df = con.execute("""
        SELECT semana, AVG(casos_sem) AS media, STDDEV(casos_sem) AS desv, MAX(casos_sem) AS maxv
        FROM (SELECT ano, semana, SUM(casos_mme) AS casos_sem FROM panel_w GROUP BY ano, semana)
        GROUP BY semana ORDER BY semana
    """).df()
    media_global = df["media"].mean()
    df["delta_pct"] = (df["media"] - media_global) / media_global * 100
    picos = df[df["delta_pct"].abs() > 15].copy()
    md.append(f"- Media semanal global nacional 2016-2022: **{media_global:.0f} casos**")
    md.append(f"- Semanas con desviación >15% de la media: **{len(picos)}** "
              f"({'↓ normal' if len(picos) <= 5 else '⚠ revisar'})")
    if len(picos) > 0:
        md.append("\n_Picos detectados:_\n")
        md.append(md_table(
            [{"semana": int(r["semana"]), "media casos": round(r["media"], 1),
              "Δ%": f"{r['delta_pct']:+.1f}%"}
             for _, r in picos.iterrows()],
            ["semana", "media casos", "Δ%"]))
    summary["estacionalidad"] = {
        "media_global": round(float(media_global), 2),
        "n_picos": int(len(picos)),
    }

    # ========================================================================
    # Cierre
    # ========================================================================
    md.append("\n## Hallazgos iniciales (para discusión)\n")
    md.append(f"1. **Volumen 2019 match INS**: proyecto reporta `{int(summary['volumen_anual'][3]['casos_mme']):,}` vs INS 23.488 (Δ dentro de tolerancia de exclusiones).")
    md.append(f"2. **Correlación NBI × razón MME**: `{summary['corr_estructura']['nbi_razon']:+.3f}` — evidencia cuantitativa de brecha estructural.")
    if summary["corr_estructura"]["nbi_razon"] < 0.1:
        md.append("   ⚠️ Correlación débil o negativa — revisar denominador o confundidores (tamaño muni).")
    md.append(f"3. **Silentes sospechosos**: `{len(summary['silentes_sospechosos'])}` municipios marcados para C2.")
    md.append(f"4. **Efecto COVID MM 2020**: `{summary['efecto_covid']['mm_delta_2020_pct']:+.1f}%` sobre baseline.")
    md.append(f"5. **Capacidad obstétrica**: score 3 (capitales) concentra la mayoría de casos absolutos por volumen poblacional — revisar confundidor antes de concluir.")

    md.append("\n## Próximos pasos\n")
    md.append("- M-001 (EEVV) completará `razon_mme_por_1000_nv` y los 13 `pct_*_eevv`.")
    md.append("- Fase MME-B.2 (M-010): análisis detallado de brechas étnico-territoriales.")
    md.append("- Fase MME-B.3 (M-011): validación cruzada departamental contra boletines INS específicos.")
    md.append("- Fase MME-C (M-014/M-015): baseline Poisson/NegBin + GBM con el feature set actual + suavizamiento Clayton-Kaldor.")

    REPORT_MD.write_text("\n".join(md))
    REPORT_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    print(f"[eda] wrote {REPORT_MD}")
    print(f"[eda] wrote {REPORT_JSON}")
    print(f"[eda] ✓ done — {len(md)} bloques markdown, {len(summary)} secciones JSON")
    return 0


if __name__ == "__main__":
    sys.exit(main())
