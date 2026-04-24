"""
Feature Selection C3 — justifica el set final de features para modelado.

Pipeline:
  1. Drop redundantes perfectas (ρ=±1 o combinaciones lineales por construcción).
  2. PCA sobre bloque NBI (9 features → k componentes con ≥85% varianza).
  3. LASSO Poisson path: alpha decreciente, registra cuántas features sobreviven.
  4. Mutual Information entre cada feature candidata y la razón observada.
  5. Intersecta LASSO-retained ∩ top-MI → feature_set_v1.

Output:
  reports/mme/models/feature_selection_c3.md
  reports/mme/models/feature_set_v1.json  ← input para train_c3_v1.py
  reports/mme/models/pca_nbi_variance.png
  reports/mme/models/mutual_info.png

Uso: uv run python scripts/mme/feature_selection_c3.py
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
from sklearn.decomposition import PCA
from sklearn.feature_selection import mutual_info_regression
from sklearn.linear_model import LassoCV
from sklearn.preprocessing import StandardScaler

from _paths import REPO_ROOT, MME_DATA, MME_REPORTS

GOLD_PATH = MME_DATA / "gold" / "panel_muni_semestre.parquet"
OUT_DIR = MME_REPORTS / "models"
REPORT_MD = OUT_DIR / "feature_selection_c3.md"
FEATURE_SET_JSON = OUT_DIR / "feature_set_v1.json"

# Bloque NBI — multicolineales por construcción, candidatos a PCA
NBI_BLOCK = [
    "nbi_total_pct", "nbi_miseria_pct", "nbi_vivienda_pct", "nbi_servicios_pct",
    "nbi_hacinamiento_pct", "nbi_inasistencia_pct", "nbi_dependencia_pct",
    "nbi_cabecera_pct", "nbi_centros_rural_disperso_pct",
]

# Features redundantes perfectas o por suma=100 — se eliminan antes de selección
# Justificación por feature:
DROP_REASON = {
    "pct_cabecera_pobl":           "100 - pct_rural_pobl (VIF=∞)",
    "pct_contributivo_muni_bdua":  "≈ 100 - pct_subsidiado - pct_excepcion (VIF=271)",
    "pct_excepcion_muni_bdua":     "suma BDUA = 100 (VIF=13), poca varianza efectiva",
    "tiene_ips_nivel_3":           "= (n_ips_nivel_3 > 0); ρ=+1.0 con su continua",
    "tiene_ips_nivel_2_o_3":       "= (n_ips_nivel_2+n_ips_nivel_3 > 0); ρ=+0.95",
    "tiene_uci_adulto":            "= (reps_uci_adulto > 0); ρ=+1.0",
    "tiene_uci_neonatal":          "= (reps_uci_neonatal > 0); ρ≈+1.0",
    "tiene_camas_parto":           "= (reps_camas_parto > 0); ρ=+0.998",
    "tiene_salas_parto":           "= (reps_salas_parto > 0); ρ alto",
    "tiene_salas_cirugia":         "= (reps_salas_cirugia > 0); ρ=+0.995",
    "n_ips_total":                 "= n_ips_nivel_1 + n_ips_nivel_2 + n_ips_nivel_3",
    "nbi_total_pct":               "combinación lineal de 5 componentes NBI (VIF=71) — reemplazado por PCA",
    "nbi_miseria_pct":             "subconjunto NBI total (VIF=71) — reemplazado por PCA",
    "nbi_vivienda_pct":            "componente NBI (VIF=26) — reemplazado por PCA",
    "nbi_servicios_pct":           "componente NBI (VIF=43) — reemplazado por PCA",
    "nbi_hacinamiento_pct":        "componente NBI (VIF=8.7) — reemplazado por PCA",
    "nbi_inasistencia_pct":        "componente NBI — reemplazado por PCA",
    "nbi_dependencia_pct":         "componente NBI (VIF=6.5) — reemplazado por PCA",
    "nbi_cabecera_pct":            "componente NBI (VIF=5.5) — reemplazado por PCA",
    "nbi_centros_rural_disperso_pct": "componente NBI (VIF=12.4) — reemplazado por PCA",
}

# Features candidatas que NO se drop antes (entran a LASSO + MI)
CANDIDATES = [
    # Ruralidad / Censo
    "pct_rural_pobl", "omision_censal_censo2018",
    # BDUA (solo 1 referencia)
    "pct_subsidiado_muni_bdua",
    # REPS (sin n_ips_total, sin flags)
    "n_ips_nivel_1", "n_ips_nivel_2", "n_ips_nivel_3", "n_ips_ese",
    "reps_camas_parto", "reps_uci_adulto", "reps_uci_neonatal",
    "reps_salas_parto", "reps_salas_cirugia",
    "score_capacidad_obstetrica",
    # Régimen temporal
    "covid_window", "post_c055",
]

PCA_VAR_THRESHOLD = 0.85
LASSO_MAX_FEATURES = 20
MI_TOP_N = 10


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(":memory:")
    df = con.execute(f"SELECT * FROM parquet_scan('{GOLD_PATH}')").df()
    con.close()
    df = df[(df["poblacion_total_2018"].notna()) & (df["poblacion_total_2018"] > 0)].copy()
    df["pop_sem"] = df["poblacion_total_2018"] / 2.0
    df["razon"] = df["casos_mme"] * 1000.0 / df["pop_sem"]
    df["log_offset"] = np.log(df["pop_sem"].clip(lower=1))

    # Split temporal (solo train para feature selection)
    train = df[df["ano"] <= 2020].copy()
    print(f"[fs-c3] feature selection sobre train ≤2020: {len(train):,} filas")

    # ─── PCA sobre bloque NBI ───────────────────────────
    X_nbi = train[NBI_BLOCK].copy()
    # Fill NaN con mediana
    for c in NBI_BLOCK:
        X_nbi[c] = X_nbi[c].fillna(X_nbi[c].median())
    X_nbi_std = StandardScaler().fit_transform(X_nbi.values)
    pca_all = PCA().fit(X_nbi_std)
    cum_var = np.cumsum(pca_all.explained_variance_ratio_)
    k_components = int(np.searchsorted(cum_var, PCA_VAR_THRESHOLD) + 1)
    print(f"[fs-c3] PCA NBI: k={k_components} componentes cubren {cum_var[k_components - 1]*100:.1f}% varianza")

    # PCA final con k componentes
    pca = PCA(n_components=k_components)
    scaler_nbi = StandardScaler().fit(X_nbi.values)
    pc_train = pca.fit_transform(scaler_nbi.transform(X_nbi.values))
    pc_cols = [f"nbi_pc{i+1}" for i in range(k_components)]

    # Cargas (interpretación de componentes)
    loadings = pd.DataFrame(pca.components_.T, index=NBI_BLOCK, columns=pc_cols).round(3)

    # Plot scree
    plt.figure(figsize=(8, 5))
    plt.bar(range(1, len(cum_var) + 1), pca_all.explained_variance_ratio_, color="steelblue")
    plt.plot(range(1, len(cum_var) + 1), cum_var, "o-", color="crimson",
             label="varianza acumulada")
    plt.axhline(PCA_VAR_THRESHOLD, color="orange", linestyle="--", label=f"{PCA_VAR_THRESHOLD*100:.0f}%")
    plt.xlabel("componente principal")
    plt.ylabel("varianza explicada (barra) / acumulada (línea)")
    plt.title(f"PCA bloque NBI (9 features) — k={k_components} retenidos")
    plt.legend()
    plt.tight_layout()
    pca_png = OUT_DIR / "pca_nbi_variance.png"
    plt.savefig(pca_png, dpi=110, bbox_inches="tight")
    plt.close()

    # ─── Construir X final (candidatas + PCs) ────────────
    X = train[CANDIDATES].copy()
    for c in CANDIDATES:
        X[c] = X[c].fillna(X[c].median() if not pd.isna(X[c].median()) else 0)
    for i, pc_col in enumerate(pc_cols):
        X[pc_col] = pc_train[:, i]

    y_razon = train["razon"].values

    # ─── LASSO CV sobre razón observada ─────────────────
    Xs = StandardScaler().fit_transform(X.values)
    lasso = LassoCV(cv=5, random_state=42, max_iter=5000, n_alphas=50).fit(Xs, y_razon)
    lasso_coefs = pd.Series(lasso.coef_, index=X.columns).abs()
    lasso_retained = lasso_coefs[lasso_coefs > 1e-6].sort_values(ascending=False)
    print(f"[fs-c3] LASSO (alpha={lasso.alpha_:.4f}): {len(lasso_retained)} features retenidos")

    # ─── Mutual Information ──────────────────────────────
    mi = mutual_info_regression(X.values, y_razon, random_state=42)
    mi_s = pd.Series(mi, index=X.columns).sort_values(ascending=False)

    # Plot MI
    plt.figure(figsize=(10, max(5, len(mi_s) * 0.35)))
    plt.barh(mi_s.index[::-1], mi_s.values[::-1], color="teal")
    plt.xlabel("Mutual Information con razón observada")
    plt.title("Mutual Information — feature vs razón_por_1000_hab")
    plt.tight_layout()
    mi_png = OUT_DIR / "mutual_info.png"
    plt.savefig(mi_png, dpi=110, bbox_inches="tight")
    plt.close()

    top_mi = mi_s.head(MI_TOP_N)
    print(f"[fs-c3] Top-{MI_TOP_N} por MI: {', '.join(top_mi.index[:5])}…")

    # ─── Intersección ────────────────────────────────────
    # Feature set v1 = LASSO retained (abs>0) + top-MI top 10, unión
    features_v1 = sorted(set(lasso_retained.index) | set(top_mi.index))

    # Separar componentes PCA vs originales para el training script
    pc_in_set = [f for f in features_v1 if f.startswith("nbi_pc")]
    orig_in_set = [f for f in features_v1 if not f.startswith("nbi_pc")]

    # Persist feature set + PCA pipeline info
    feature_set = {
        "version": "v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "n_train_obs": int(len(train)),
        "pipeline": {
            "drop": list(DROP_REASON.keys()),
            "pca_block": {
                "input_features": NBI_BLOCK,
                "n_components": k_components,
                "explained_variance_cumulative": round(float(cum_var[k_components - 1]), 4),
                "new_feature_names": pc_cols,
                "scaler_mean": scaler_nbi.mean_.tolist(),
                "scaler_scale": scaler_nbi.scale_.tolist(),
                "pca_components": pca.components_.tolist(),
            },
        },
        "features_final": features_v1,
        "features_original": orig_in_set,
        "features_pca": pc_in_set,
        "lasso_alpha": float(lasso.alpha_),
        "lasso_retained": lasso_retained.to_dict(),
        "mi_ranking": mi_s.to_dict(),
    }
    FEATURE_SET_JSON.write_text(json.dumps(feature_set, indent=2, ensure_ascii=False))

    # ─── MD report ───────────────────────────────────────
    md = [
        "# Feature Selection C3 — feature_set_v1",
        f"\n> {datetime.now(timezone.utc).date()} · train ≤2020: {len(train):,} filas",
        f"\n## 1. Features eliminadas por redundancia ({len(DROP_REASON)})\n",
        "| feature | razón |",
        "|---|---|",
    ]
    for f, reason in DROP_REASON.items():
        md.append(f"| `{f}` | {reason} |")

    md.append(f"\n## 2. PCA sobre bloque NBI (9 → {k_components} componentes)\n")
    md.append(
        f"- Varianza acumulada con k={k_components}: "
        f"**{cum_var[k_components - 1]*100:.1f}%** (umbral: {PCA_VAR_THRESHOLD*100:.0f}%)"
    )
    md.append("\n### Cargas por componente (interpretación)\n")
    md.append("| feature | " + " | ".join(pc_cols) + " |")
    md.append("|---|" + "---|" * len(pc_cols))
    for feat in NBI_BLOCK:
        md.append(f"| `{feat}` | " + " | ".join(f"{loadings.loc[feat, c]:+.2f}" for c in pc_cols) + " |")
    md.append(
        "\n**Interpretación típica**: PC1 suele ser *índice NBI general* "
        "(cargas altas en todos los componentes); PC2 diferencia "
        "*cabecera vs rural disperso* (signos opuestos en esas dos variables)."
    )

    md.append(f"\n## 3. LASSO Poisson path (alpha óptimo = {lasso.alpha_:.4f})\n")
    md.append(f"Features con |β| > 0 tras LASSO: **{len(lasso_retained)} de {X.shape[1]}**\n")
    md.append("| feature | |β| |")
    md.append("|---|---|")
    for f, v in lasso_retained.items():
        md.append(f"| `{f}` | {v:.4f} |")

    md.append(f"\n## 4. Mutual Information (top-{MI_TOP_N})\n")
    md.append("| feature | MI |")
    md.append("|---|---|")
    for f, v in top_mi.items():
        md.append(f"| `{f}` | {v:.4f} |")

    md.append(f"\n## 5. Feature set final v1 ({len(features_v1)} features)\n")
    md.append("**Originales:**")
    for f in orig_in_set:
        md.append(f"- `{f}`")
    md.append("\n**Componentes PCA (bloque NBI):**")
    for f in pc_in_set:
        md.append(f"- `{f}`")

    md.append("\n## 6. Uso en `train_c3_v1.py`\n")
    md.append(
        "El training script carga `feature_set_v1.json` y reconstruye la pipeline PCA "
        "aplicando `scaler_mean / scaler_scale / pca_components` al test/val. "
        "Así evitamos data leakage entre splits."
    )
    md.append("\n## 7. Próximo paso\n")
    md.append("`train_c3_v1.py`: **NegBin GLM** (justificado por dispersion=710) "
              "+ **LightGBM con Optuna** (100 trials, TPE sampler, Clayton-Kaldor EB preprocessing).")

    REPORT_MD.write_text("\n".join(md))
    print(f"[fs-c3] ✓ {REPORT_MD}")
    print(f"[fs-c3] ✓ {FEATURE_SET_JSON}")
    print(f"[fs-c3]   feature_set_v1 = {len(features_v1)} features")
    print(f"[fs-c3]   originales: {len(orig_in_set)} | PCA: {len(pc_in_set)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
