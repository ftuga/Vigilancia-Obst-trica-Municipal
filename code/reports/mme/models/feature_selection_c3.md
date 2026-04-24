# Feature Selection C3 — feature_set_v1

> 2026-04-24 · train ≤2020: 11,210 filas

## 1. Features eliminadas por redundancia (20)

| feature | razón |
|---|---|
| `pct_cabecera_pobl` | 100 - pct_rural_pobl (VIF=∞) |
| `pct_contributivo_muni_bdua` | ≈ 100 - pct_subsidiado - pct_excepcion (VIF=271) |
| `pct_excepcion_muni_bdua` | suma BDUA = 100 (VIF=13), poca varianza efectiva |
| `tiene_ips_nivel_3` | = (n_ips_nivel_3 > 0); ρ=+1.0 con su continua |
| `tiene_ips_nivel_2_o_3` | = (n_ips_nivel_2+n_ips_nivel_3 > 0); ρ=+0.95 |
| `tiene_uci_adulto` | = (reps_uci_adulto > 0); ρ=+1.0 |
| `tiene_uci_neonatal` | = (reps_uci_neonatal > 0); ρ≈+1.0 |
| `tiene_camas_parto` | = (reps_camas_parto > 0); ρ=+0.998 |
| `tiene_salas_parto` | = (reps_salas_parto > 0); ρ alto |
| `tiene_salas_cirugia` | = (reps_salas_cirugia > 0); ρ=+0.995 |
| `n_ips_total` | = n_ips_nivel_1 + n_ips_nivel_2 + n_ips_nivel_3 |
| `nbi_total_pct` | combinación lineal de 5 componentes NBI (VIF=71) — reemplazado por PCA |
| `nbi_miseria_pct` | subconjunto NBI total (VIF=71) — reemplazado por PCA |
| `nbi_vivienda_pct` | componente NBI (VIF=26) — reemplazado por PCA |
| `nbi_servicios_pct` | componente NBI (VIF=43) — reemplazado por PCA |
| `nbi_hacinamiento_pct` | componente NBI (VIF=8.7) — reemplazado por PCA |
| `nbi_inasistencia_pct` | componente NBI — reemplazado por PCA |
| `nbi_dependencia_pct` | componente NBI (VIF=6.5) — reemplazado por PCA |
| `nbi_cabecera_pct` | componente NBI (VIF=5.5) — reemplazado por PCA |
| `nbi_centros_rural_disperso_pct` | componente NBI (VIF=12.4) — reemplazado por PCA |

## 2. PCA sobre bloque NBI (9 → 3 componentes)

- Varianza acumulada con k=3: **86.7%** (umbral: 85%)

### Cargas por componente (interpretación)

| feature | nbi_pc1 | nbi_pc2 | nbi_pc3 |
|---|---|---|---|
| `nbi_total_pct` | +0.39 | +0.20 | -0.03 |
| `nbi_miseria_pct` | +0.39 | -0.15 | +0.09 |
| `nbi_vivienda_pct` | +0.30 | +0.15 | +0.72 |
| `nbi_servicios_pct` | +0.34 | +0.12 | -0.52 |
| `nbi_hacinamiento_pct` | +0.31 | -0.43 | +0.04 |
| `nbi_inasistencia_pct` | +0.29 | -0.54 | -0.30 |
| `nbi_dependencia_pct` | +0.32 | -0.08 | +0.05 |
| `nbi_cabecera_pct` | +0.28 | +0.64 | -0.29 |
| `nbi_centros_rural_disperso_pct` | +0.37 | +0.09 | +0.19 |

**Interpretación típica**: PC1 suele ser *índice NBI general* (cargas altas en todos los componentes); PC2 diferencia *cabecera vs rural disperso* (signos opuestos en esas dos variables).

## 3. LASSO Poisson path (alpha óptimo = 0.0023)

Features con |β| > 0 tras LASSO: **14 de 18**

| feature | |β| |
|---|---|
| `n_ips_nivel_1` | 0.0432 |
| `reps_salas_parto` | 0.0423 |
| `omision_censal_censo2018` | 0.0307 |
| `nbi_pc2` | 0.0266 |
| `score_capacidad_obstetrica` | 0.0242 |
| `nbi_pc1` | 0.0203 |
| `pct_rural_pobl` | 0.0194 |
| `pct_subsidiado_muni_bdua` | 0.0166 |
| `reps_uci_adulto` | 0.0164 |
| `n_ips_ese` | 0.0135 |
| `covid_window` | 0.0127 |
| `n_ips_nivel_2` | 0.0107 |
| `reps_salas_cirugia` | 0.0088 |
| `nbi_pc3` | 0.0073 |

## 4. Mutual Information (top-10)

| feature | MI |
|---|---|
| `omision_censal_censo2018` | 1.2635 |
| `pct_subsidiado_muni_bdua` | 1.2635 |
| `nbi_pc3` | 1.2607 |
| `nbi_pc2` | 1.2541 |
| `pct_rural_pobl` | 1.2504 |
| `nbi_pc1` | 1.2408 |
| `reps_salas_parto` | 0.2623 |
| `n_ips_ese` | 0.1703 |
| `n_ips_nivel_1` | 0.1689 |
| `score_capacidad_obstetrica` | 0.1597 |

## 5. Feature set final v1 (14 features)

**Originales:**
- `covid_window`
- `n_ips_ese`
- `n_ips_nivel_1`
- `n_ips_nivel_2`
- `omision_censal_censo2018`
- `pct_rural_pobl`
- `pct_subsidiado_muni_bdua`
- `reps_salas_cirugia`
- `reps_salas_parto`
- `reps_uci_adulto`
- `score_capacidad_obstetrica`

**Componentes PCA (bloque NBI):**
- `nbi_pc1`
- `nbi_pc2`
- `nbi_pc3`

## 6. Uso en `train_c3_v1.py`

El training script carga `feature_set_v1.json` y reconstruye la pipeline PCA aplicando `scaler_mean / scaler_scale / pca_components` al test/val. Así evitamos data leakage entre splits.

## 7. Próximo paso

`train_c3_v1.py`: **NegBin GLM** (justificado por dispersion=710) + **LightGBM con Optuna** (100 trials, TPE sampler, Clayton-Kaldor EB preprocessing).