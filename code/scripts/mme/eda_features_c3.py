"""
EDA de FEATURES C3 — distribuciones, correlación y multicolinealidad (VIF).

Output:
  reports/mme/models/eda_features_c3.md
  reports/mme/models/eda_features_c3.json
  reports/mme/models/corr_heatmap.png
  reports/mme/models/vif_bar.png

Responde:
  1. ¿Cuántas features tienen missing y cuánto?
  2. ¿Qué features están altamente correlacionadas (redundantes)?
  3. ¿Qué features inflan la varianza del GLM (VIF > 10)?

Decisiones que alimenta:
  - Qué features tirar antes de modelar (redundantes puros)
  - Qué features agrupar en PCA (bloques correlacionados: NBI, REPS)
  - Qué features transformar (skewed → log/sqrt)

Uso:  uv run python scripts/mme/eda_features_c3.py
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
import pandas as pd

from _paths import REPO_ROOT, MME_DATA, MME_REPORTS

GOLD_PATH = MME_DATA / "gold" / "panel_muni_semestre.parquet"
OUT_DIR = MME_REPORTS / "models"
REPORT_MD = OUT_DIR / "eda_features_c3.md"
REPORT_JSON = OUT_DIR / "eda_features_c3.json"

# Features candidatas según feature_spec_v1 (excluye outcomes + IDs)
FEATURES_NBI = [
    "nbi_total_pct", "nbi_miseria_pct", "nbi_vivienda_pct", "nbi_servicios_pct",
    "nbi_hacinamiento_pct", "nbi_inasistencia_pct", "nbi_dependencia_pct",
    "nbi_cabecera_pct", "nbi_centros_rural_disperso_pct",
]
FEATURES_POBL = ["pct_rural_pobl", "pct_cabecera_pobl", "omision_censal_censo2018"]
FEATURES_BDUA = ["pct_subsidiado_muni_bdua", "pct_contributivo_muni_bdua",
                 "pct_excepcion_muni_bdua"]
FEATURES_REPS = [
    "n_ips_total", "n_ips_nivel_1", "n_ips_nivel_2", "n_ips_nivel_3",
    "n_ips_ese", "tiene_ips_nivel_3", "tiene_ips_nivel_2_o_3",
    "reps_camas_parto", "reps_uci_adulto", "reps_uci_neonatal",
    "reps_salas_parto", "reps_salas_cirugia",
    "tiene_camas_parto", "tiene_uci_adulto", "tiene_salas_cirugia",
    "score_capacidad_obstetrica",
]
FEATURES_REGIME = ["covid_window", "post_c055"]
ALL_FEATURES = FEATURES_NBI + FEATURES_POBL + FEATURES_BDUA + FEATURES_REPS + FEATURES_REGIME

BLOCKS = {
    "NBI (Censo 2018)": FEATURES_NBI,
    "Ruralidad+Cobertura censal": FEATURES_POBL,
    "BDUA régimen": FEATURES_BDUA,
    "REPS oferta Demora III": FEATURES_REPS,
    "Régimen temporal": FEATURES_REGIME,
}


def compute_vif(X: pd.DataFrame) -> pd.DataFrame:
    """Calcula VIF sin statsmodels: VIF_k = 1 / (1 - R²_k) donde R²_k es
    el R² de regresar feature k contra el resto (OLS sin intercepto aparte)."""
    from numpy.linalg import LinAlgError
    n_feat = X.shape[1]
    vifs = []
    # Centrar y normalizar
    Xn = (X - X.mean()) / X.std(ddof=0).replace(0, 1)
    for i, col in enumerate(X.columns):
        y = Xn.iloc[:, i].values
        Xo = Xn.drop(columns=[col]).values
        # OLS: beta = (X'X)^-1 X'y
        try:
            XtX = Xo.T @ Xo
            XtY = Xo.T @ y
            beta = np.linalg.solve(XtX, XtY)
            y_pred = Xo @ beta
            ss_res = float(np.sum((y - y_pred) ** 2))
            ss_tot = float(np.sum(y ** 2))  # y está centrada+escalada
            r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
            vif = 1 / (1 - r2) if r2 < 0.999 else float("inf")
        except LinAlgError:
            vif = float("inf")
        vifs.append(vif)
    return pd.DataFrame({"feature": X.columns, "VIF": vifs}).sort_values("VIF", ascending=False)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(":memory:")
    df = con.execute(f"SELECT * FROM parquet_scan('{GOLD_PATH}')").df()
    con.close()

    # Solo observaciones con población válida (necesaria para offset)
    df = df[(df["poblacion_total_2018"].notna()) & (df["poblacion_total_2018"] > 0)].copy()
    n = len(df)

    X = df[ALL_FEATURES].copy()
    # Missing por feature
    missing = (X.isna().sum() / len(X) * 100).round(3).sort_values(ascending=False)
    nonzero_missing = missing[missing > 0]

    # Summary univariado
    summary = X.describe(percentiles=[0.05, 0.5, 0.95]).T
    summary["skew"] = X.skew().round(3)
    summary["n_unique"] = X.nunique()

    # Fill NaN con mediana (para correlation + VIF)
    X_clean = X.copy()
    for c in ALL_FEATURES:
        med = X_clean[c].median()
        X_clean[c] = X_clean[c].fillna(0 if pd.isna(med) else med)

    # Correlación Spearman (robusta a outliers y monotonicidad)
    corr_s = X_clean.corr(method="spearman").round(3)

    # Pares altamente correlacionados (|ρ| ≥ 0.85)
    redund_pairs = []
    cols = corr_s.columns.tolist()
    for i, a in enumerate(cols):
        for j in range(i + 1, len(cols)):
            b = cols[j]
            rho = corr_s.iloc[i, j]
            if pd.notna(rho) and abs(rho) >= 0.85:
                redund_pairs.append({"a": a, "b": b, "rho": float(rho)})
    redund_pairs.sort(key=lambda x: abs(x["rho"]), reverse=True)

    # VIF sobre todas features numéricas continuas (excluye binary flags)
    binary = {c for c in ALL_FEATURES if c.startswith("tiene_")
              or c in {"covid_window", "post_c055"}}
    continuous = [c for c in ALL_FEATURES if c not in binary]
    vif_df = compute_vif(X_clean[continuous])

    # Plots
    # 1) Correlation heatmap
    plt.figure(figsize=(16, 13))
    im = plt.imshow(corr_s.values, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
    plt.colorbar(im, label="Spearman ρ")
    plt.xticks(range(len(cols)), cols, rotation=90, fontsize=8)
    plt.yticks(range(len(cols)), cols, fontsize=8)
    plt.title(f"Matriz correlación Spearman — {len(cols)} features (n={n:,})")
    plt.tight_layout()
    corr_png = OUT_DIR / "corr_heatmap.png"
    plt.savefig(corr_png, dpi=110, bbox_inches="tight")
    plt.close()

    # 2) VIF bar chart
    plt.figure(figsize=(12, max(6, len(vif_df) * 0.35)))
    colors = ["crimson" if v > 10 else ("orange" if v > 5 else "steelblue")
              for v in vif_df["VIF"]]
    plt.barh(vif_df["feature"], vif_df["VIF"].replace([np.inf], 1e6).clip(upper=100),
             color=colors)
    plt.axvline(5, color="orange", linestyle="--", label="VIF=5 (atención)")
    plt.axvline(10, color="crimson", linestyle="--", label="VIF=10 (multicolinealidad severa)")
    plt.xlabel("VIF (clip 100)")
    plt.title("VIF por feature continua — detecta redundancia lineal")
    plt.legend()
    plt.tight_layout()
    vif_png = OUT_DIR / "vif_bar.png"
    plt.savefig(vif_png, dpi=110, bbox_inches="tight")
    plt.close()

    # Clasificación VIF
    vif_severe = vif_df[vif_df["VIF"] > 10]["feature"].tolist()
    vif_moderate = vif_df[(vif_df["VIF"] > 5) & (vif_df["VIF"] <= 10)]["feature"].tolist()

    # ─── MD report ─────────────────────────────────────
    md = [
        "# EDA Features C3 — distribución, correlación, multicolinealidad",
        f"\n> {datetime.now(timezone.utc).date()} · n={n:,} obs · features candidatas={len(ALL_FEATURES)}",
        f"\n## 1. Bloques conceptuales de features\n",
    ]
    for block_name, feats in BLOCKS.items():
        md.append(f"- **{block_name}** ({len(feats)} vars): {', '.join(f'`{f}`' for f in feats)}")

    md.append(f"\n## 2. Missing data\n")
    if len(nonzero_missing) == 0:
        md.append("Ninguna feature con missing >0%. ✓")
    else:
        md.append("| feature | % missing |")
        md.append("|---|---|")
        for f, pct in nonzero_missing.items():
            md.append(f"| `{f}` | {pct}% |")

    md.append(f"\n## 3. Summary univariado (top-10 skew)\n")
    top_skew = summary.reindex(summary["skew"].abs().sort_values(ascending=False).index).head(10)
    md.append("| feature | min | p5 | p50 | p95 | max | std | skew |")
    md.append("|---|---|---|---|---|---|---|---|")
    for name, r in top_skew.iterrows():
        md.append(
            f"| `{name}` | {r['min']:.2f} | {r['5%']:.2f} | {r['50%']:.2f} | "
            f"{r['95%']:.2f} | {r['max']:.2f} | {r['std']:.2f} | {r['skew']} |"
        )
    md.append(
        "\n**Interpretación**: features con skew > |2| son candidatas a log/sqrt antes "
        "de GLM (no afecta LightGBM)."
    )

    md.append(f"\n## 4. Pares altamente correlacionados (|Spearman ρ| ≥ 0.85)\n")
    if len(redund_pairs) == 0:
        md.append("Ningún par cruza el umbral. ✓ Sin redundancia severa.")
    else:
        md.append(f"**{len(redund_pairs)} pares detectados** — candidatos a eliminación o PCA:\n")
        md.append("| feature A | feature B | ρ |")
        md.append("|---|---|---|")
        for pair in redund_pairs[:30]:
            md.append(f"| `{pair['a']}` | `{pair['b']}` | {pair['rho']:+.3f} |")
        if len(redund_pairs) > 30:
            md.append(f"\n_(...{len(redund_pairs) - 30} pares adicionales omitidos)_")

    md.append(f"\n## 5. VIF — Variance Inflation Factor\n")
    md.append(
        "VIF mide cuánto se infla la varianza de un coeficiente GLM por multicolinealidad. "
        "Umbral común: VIF > 10 = multicolinealidad severa (coeficiente inestable)."
    )
    md.append(f"\n**Features con VIF > 10 ({len(vif_severe)}):**")
    for f in vif_severe:
        v = vif_df[vif_df["feature"] == f]["VIF"].iloc[0]
        v_str = "∞" if np.isinf(v) else f"{v:.1f}"
        md.append(f"- `{f}` — VIF = {v_str}")
    md.append(f"\n**Features con VIF 5-10 ({len(vif_moderate)}):**")
    for f in vif_moderate:
        v = vif_df[vif_df["feature"] == f]["VIF"].iloc[0]
        md.append(f"- `{f}` — VIF = {v:.1f}")

    md.append(f"\n## 6. Recomendaciones accionables para `feature_selection_c3.py`\n")
    rec_list = []
    # Heurísticas basadas en los 9 NBI + REPS redundantes
    nbi_in_severe = [f for f in vif_severe if f.startswith("nbi_")]
    reps_in_severe = [f for f in vif_severe if f.startswith(("n_ips", "reps_", "tiene_"))]
    if len(nbi_in_severe) >= 3:
        rec_list.append(
            f"1. **Bloque NBI** ({len(nbi_in_severe)}/9 con VIF>10) → aplicar PCA. "
            "Esperamos 2 componentes principales cubran ≥85% varianza (NBI_total es una combinación "
            "lineal de los 5 componentes por diseño)."
        )
    if len(reps_in_severe) >= 3:
        rec_list.append(
            f"2. **Bloque REPS** ({len(reps_in_severe)} con VIF>10) → "
            "`n_ips_total = n_ips_nivel_{1,2,3}` por diseño, redundancia perfecta. "
            "Tirar `n_ips_total` y `tiene_ips_nivel_2_o_3` (derivados)."
        )
    if any(f.startswith("pct_") and "bdua" in f for f in vif_severe):
        rec_list.append(
            "3. **BDUA**: `pct_subsidiado + pct_contributivo + pct_excepcion ≈ 100`. "
            "Constraint suma=100 garantiza colinealidad. Mantener solo `pct_subsidiado_muni_bdua` "
            "como referencia y derivar `pct_no_subsidiado = 100 - pct_subsidiado`."
        )
    rec_list.append(
        f"4. **Features binarias** (flags `tiene_*`) son proxies de contínuas — "
        "evaluar si aportan info sobre la contínua correspondiente o son puro ruido para GLM. "
        "LightGBM las usa bien de todas formas."
    )
    if n_skewed := (summary["skew"].abs() > 2).sum():
        rec_list.append(
            f"5. **{n_skewed} features muy asimétricas** → log1p antes de GLM "
            "(reduce influencia de Bogotá/Medellín en β)."
        )
    for r in rec_list:
        md.append(r)

    md.append("\n## 7. Próximo paso")
    md.append(
        "`feature_selection_c3.py` ejecuta:"
        "\n1. PCA por bloque (NBI, REPS) → componentes que capturen ≥85% varianza"
        "\n2. LASSO path (GLM Poisson) sobre feature set reducido"
        "\n3. Mutual Information con razón observada"
        "\n4. Intersección de (LASSO retained) ∩ (top MI) → feature set final v1."
    )

    REPORT_MD.write_text("\n".join(md))

    # JSON summary
    REPORT_JSON.write_text(json.dumps({
        "n_obs": n,
        "n_features_candidates": len(ALL_FEATURES),
        "missing_nonzero": nonzero_missing.to_dict(),
        "vif_severe": vif_severe,
        "vif_moderate": vif_moderate,
        "redundant_pairs_count": len(redund_pairs),
        "top_redundant_pairs": redund_pairs[:20],
        "skew_top5": top_skew["skew"].head(5).to_dict(),
    }, indent=2, ensure_ascii=False, default=str))

    print(f"[eda-features] ✓ {REPORT_MD}")
    print(f"[eda-features] ✓ {REPORT_JSON}")
    print(f"[eda-features]   VIF>10: {len(vif_severe)} features")
    print(f"[eda-features]   pares ρ≥0.85: {len(redund_pairs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
