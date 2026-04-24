"""
EDA del TARGET C3 — diagnóstico pre-modelado.

Responde 3 preguntas empíricas que deciden la familia de modelos:

  1. ¿Poisson o Negative Binomial?   (dispersion ratio var/mean)
  2. ¿Zero-Inflated Poisson (ZIP)?    (% filas con y=0)
  3. ¿Hay outliers o heavy tail?      (IQR, p99, muni con razón anómala)

Input:  data/mme/gold/panel_muni_semestre.parquet
Output: reports/mme/models/eda_target_c3.md + 3 PNGs

Uso:  uv run python scripts/mme/eda_target_c3.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from _paths import REPO_ROOT, MME_DATA, MME_REPORTS

GOLD_PATH = MME_DATA / "gold" / "panel_muni_semestre.parquet"
OUT_DIR = MME_REPORTS / "models"
REPORT_MD = OUT_DIR / "eda_target_c3.md"
REPORT_JSON = OUT_DIR / "eda_target_c3.json"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(":memory:")
    df = con.execute(f"""
        SELECT casos_mme, poblacion_total_2018,
               CAST(poblacion_total_2018 AS DOUBLE) / 2.0 AS pop_sem,
               casos_mme * 1000.0 / NULLIF(poblacion_total_2018 / 2.0, 0) AS razon,
               ano, semestre, cod_mpio, nom_mpio, nom_dpto
        FROM parquet_scan('{GOLD_PATH}')
        WHERE poblacion_total_2018 IS NOT NULL AND poblacion_total_2018 > 0
    """).df()
    con.close()
    y = df["casos_mme"].astype(float).values
    razon = df["razon"].astype(float).values
    n = len(df)

    # ─── Diagnóstico de dispersión ─────────────────────────
    mean_y, var_y = float(np.mean(y)), float(np.var(y, ddof=1))
    dispersion_ratio = var_y / mean_y if mean_y > 0 else float("nan")
    pct_zeros = float(np.mean(y == 0) * 100)
    poisson_expected_zeros = float(np.exp(-mean_y) * 100)  # si fuera Poisson con λ=mean

    # ─── Percentiles y outliers ────────────────────────────
    p50, p75, p95, p99, p999 = np.percentile(y, [50, 75, 95, 99, 99.9])
    iqr = p75 - p50
    upper_fence = p75 + 1.5 * iqr
    n_outliers = int(np.sum(y > upper_fence))
    max_y = int(y.max())
    r_p50, r_p95, r_p99 = np.percentile(razon, [50, 95, 99])
    n_razon_extreme = int(np.sum(razon > 20))  # >20/1000 hab (muy alta)

    # Top 5 muni con razón más alta (candidatos outlier)
    top_razon = df.nlargest(10, "razon")[
        ["cod_mpio", "nom_mpio", "nom_dpto", "ano", "semestre", "casos_mme",
         "poblacion_total_2018", "razon"]
    ]

    # ─── Plots ─────────────────────────────────────────────
    fig, axes = plt.subplots(1, 3, figsize=(16, 4))
    axes[0].hist(y, bins=60, color="steelblue", edgecolor="white")
    axes[0].set_yscale("log")
    axes[0].set_xlabel("casos_mme por (muni × semestre)")
    axes[0].set_ylabel("frecuencia (log)")
    axes[0].set_title(f"Distribución casos_mme | n={n:,}, mean={mean_y:.2f}, var={var_y:.1f}")
    axes[0].axvline(mean_y, color="red", linestyle="--", label=f"mean={mean_y:.1f}")
    axes[0].legend()

    axes[1].hist(np.log1p(y), bins=60, color="teal", edgecolor="white")
    axes[1].set_xlabel("log1p(casos_mme)")
    axes[1].set_ylabel("frecuencia")
    axes[1].set_title("log1p — claridad de cola y modas")

    # Razón: histograma winsorizado a p99 para legibilidad
    razon_w = np.clip(razon, 0, r_p99)
    axes[2].hist(razon_w, bins=60, color="coral", edgecolor="white")
    axes[2].set_xlabel("razón MME / 1.000 hab (winsorizado a p99)")
    axes[2].set_ylabel("frecuencia")
    axes[2].set_title(f"Razón observada | p50={r_p50:.2f}, p99={r_p99:.2f}")

    plt.tight_layout()
    plot_target = OUT_DIR / "eda_target_distributions.png"
    plt.savefig(plot_target, dpi=110, bbox_inches="tight")
    plt.close()

    # Dispersión por año
    fig, ax = plt.subplots(figsize=(10, 5))
    by_year = df.groupby("ano")["casos_mme"].agg(["mean", "var"])
    by_year["dispersion"] = by_year["var"] / by_year["mean"]
    ax.bar(by_year.index.astype(str), by_year["dispersion"], color="slateblue")
    ax.axhline(1.0, color="red", linestyle="--", label="Poisson (dispersion=1)")
    ax.axhline(1.5, color="orange", linestyle="--", label="umbral NegBin (1.5)")
    ax.set_ylabel("dispersion ratio (var/mean)")
    ax.set_title("Dispersión del target por año (diagnóstico Poisson vs NegBin)")
    ax.legend()
    plot_disp = OUT_DIR / "eda_target_dispersion_by_year.png"
    plt.tight_layout()
    plt.savefig(plot_disp, dpi=110, bbox_inches="tight")
    plt.close()

    # ─── Decisión recomendada ───────────────────────────────
    decision: list[str] = []
    if dispersion_ratio > 1.5:
        decision.append(
            f"✓ **NegBin preferido**: dispersion ratio = {dispersion_ratio:.2f} > 1.5 "
            f"(Poisson asume = 1). Confirma sobredispersión."
        )
    elif dispersion_ratio < 0.9:
        decision.append(
            f"⚠ **Underdispersion**: ratio = {dispersion_ratio:.2f} < 0.9. "
            "Poisson sobre-estimaría varianza. Considerar Binomial."
        )
    else:
        decision.append(
            f"✓ **Poisson válido**: dispersion ratio = {dispersion_ratio:.2f} ∈ [0.9, 1.5]."
        )
    if pct_zeros > 40:
        decision.append(
            f"⚠ **Zero-Inflation posible**: %zeros = {pct_zeros:.1f}% > 40%. "
            "Evaluar ZIP o Hurdle Model."
        )
    elif pct_zeros > 25:
        decision.append(
            f"ℹ **%zeros moderado** = {pct_zeros:.1f}%. "
            "Poisson/NegBin manejan si dispersion lo permite; ZIP opcional."
        )
    else:
        decision.append(f"✓ **%zeros bajo** = {pct_zeros:.1f}% — no se requiere ZIP.")
    if n_razon_extreme > 0:
        decision.append(
            f"⚠ **{n_razon_extreme} filas con razón >20/1.000 hab** (outliers muni pequeños). "
            "Requiere Clayton-Kaldor EB para estabilizar."
        )

    # ─── Reporte MD ─────────────────────────────────────────
    md = [
        "# EDA del Target C3 — Diagnóstico pre-modelado",
        f"\n> Generado: {datetime.now(timezone.utc).date()} · "
        f"Fuente: `{GOLD_PATH.relative_to(REPO_ROOT) if GOLD_PATH.is_relative_to(REPO_ROOT) else GOLD_PATH}`",
        f"\n## 1. Target: `casos_mme` (count, entero ≥0)",
        f"- Observaciones: **{n:,}** filas (muni × semestre)",
        f"- **Media**: {mean_y:.3f}",
        f"- **Varianza**: {var_y:.3f}",
        f"- **Dispersion ratio (var/mean)**: `{dispersion_ratio:.3f}`",
        f"- **% zeros (silentes)**: {pct_zeros:.2f}%",
        f"  - %zeros esperado si Poisson(λ={mean_y:.2f}): **{poisson_expected_zeros:.2f}%**",
        f"- **max**: {max_y} casos",
        f"- **Percentiles**: p50={p50:.0f}, p75={p75:.0f}, p95={p95:.0f}, p99={p99:.0f}, p99.9={p999:.0f}",
        f"- **Outliers IQR** (y > p75 + 1.5·IQR = {upper_fence:.1f}): {n_outliers:,} filas",
        f"\n## 2. Razón MME / 1.000 hab (proxy pre-EEVV)",
        f"- p50 = {r_p50:.3f}",
        f"- p95 = {r_p95:.3f}",
        f"- p99 = {r_p99:.3f}",
        f"- Razón >20/1.000 hab (extremo): **{n_razon_extreme} filas** — candidatos para winsorization o Clayton-Kaldor EB",
        f"\n## 3. Decisión de familia de modelo\n",
        *[f"- {d}" for d in decision],
        f"\n## 4. Top-10 muni con razón observada más alta\n",
        "| cod_mpio | muni | dpto | año | sem | casos | pob | razón |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for _, r in top_razon.iterrows():
        md.append(
            f"| {int(r['cod_mpio'])} | {r['nom_mpio']} | {r['nom_dpto']} | "
            f"{int(r['ano'])} | {int(r['semestre'])} | {int(r['casos_mme'])} | "
            f"{int(r['poblacion_total_2018']):,} | {r['razon']:.2f} |"
        )
    md.append(f"\n## 5. Plots\n")
    md.append(f"- `{plot_target.name}` — distribuciones casos_mme, log1p, razón")
    md.append(f"- `{plot_disp.name}` — dispersion ratio por año (diagnóstico familia)")

    md.append("\n## 6. Conclusión y siguiente paso\n")
    md.append("Basado en el diagnóstico:")
    if dispersion_ratio > 1.5:
        md.append("1. **Familia primaria: NegBin GLM** con offset `log(pob_sem)`.")
    else:
        md.append("1. **Familia primaria: Poisson GLM** con offset `log(pob_sem)`.")
    md.append("2. **Challenger: LightGBM con objective Poisson** (o Tweedie p=1.1 si zeros son relevantes).")
    md.append(
        "3. **Pre-procesamiento obligatorio**: Clayton-Kaldor Empirical Bayes "
        "para muni con NV_sem < 25 (estabilización razón)."
    )
    md.append(
        "4. **Si Spearman dpto < 0.5 en val**: agregar interacciones manuales "
        "(NBI × ausencia_nivel_3, rural × sin_UCI_adulto)."
    )
    md.append("5. **Siguiente paso**: `eda_features_c3.py` — distribuciones + correlación + VIF.")

    REPORT_MD.write_text("\n".join(md))
    REPORT_JSON.write_text(json.dumps({
        "n_obs": n,
        "mean": mean_y,
        "var": var_y,
        "dispersion_ratio": dispersion_ratio,
        "pct_zeros": pct_zeros,
        "poisson_expected_zeros": poisson_expected_zeros,
        "razon_p99": float(r_p99),
        "n_razon_extreme_gt20": n_razon_extreme,
        "n_outliers_iqr": n_outliers,
        "decision": decision,
        "recommendation": {
            "primary_family": "negbin" if dispersion_ratio > 1.5 else "poisson",
            "challenger": "lightgbm_poisson",
            "require_clayton_kaldor": True,
            "require_zip": pct_zeros > 40,
        },
    }, indent=2, ensure_ascii=False))

    print(f"[eda-target] ✓ {REPORT_MD}")
    print(f"[eda-target] ✓ {REPORT_JSON}")
    print()
    print(f"dispersion_ratio = {dispersion_ratio:.3f}")
    print(f"% zeros          = {pct_zeros:.1f}%")
    print(f"razon p99        = {r_p99:.2f}")
    print(f"outliers (IQR)   = {n_outliers:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
