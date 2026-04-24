# EDA Features C3 — distribución, correlación, multicolinealidad

> 2026-04-24 · n=15,694 obs · features candidatas=33

## 1. Bloques conceptuales de features

- **NBI (Censo 2018)** (9 vars): `nbi_total_pct`, `nbi_miseria_pct`, `nbi_vivienda_pct`, `nbi_servicios_pct`, `nbi_hacinamiento_pct`, `nbi_inasistencia_pct`, `nbi_dependencia_pct`, `nbi_cabecera_pct`, `nbi_centros_rural_disperso_pct`
- **Ruralidad+Cobertura censal** (3 vars): `pct_rural_pobl`, `pct_cabecera_pobl`, `omision_censal_censo2018`
- **BDUA régimen** (3 vars): `pct_subsidiado_muni_bdua`, `pct_contributivo_muni_bdua`, `pct_excepcion_muni_bdua`
- **REPS oferta Demora III** (16 vars): `n_ips_total`, `n_ips_nivel_1`, `n_ips_nivel_2`, `n_ips_nivel_3`, `n_ips_ese`, `tiene_ips_nivel_3`, `tiene_ips_nivel_2_o_3`, `reps_camas_parto`, `reps_uci_adulto`, `reps_uci_neonatal`, `reps_salas_parto`, `reps_salas_cirugia`, `tiene_camas_parto`, `tiene_uci_adulto`, `tiene_salas_cirugia`, `score_capacidad_obstetrica`
- **Régimen temporal** (2 vars): `covid_window`, `post_c055`

## 2. Missing data

| feature | % missing |
|---|---|
| `nbi_cabecera_pct` | 1.695% |

## 3. Summary univariado (top-10 skew)

| feature | min | p5 | p50 | p95 | max | std | skew |
|---|---|---|---|---|---|---|---|
| `n_ips_nivel_3` | 0.00 | 0.00 | 0.00 | 0.00 | 9.00 | 0.30 | 24.193 |
| `reps_camas_parto` | 0.00 | 0.00 | 0.00 | 2.00 | 148.00 | 5.20 | 21.801 |
| `reps_salas_cirugia` | 0.00 | 0.00 | 0.00 | 8.00 | 695.00 | 25.17 | 21.517 |
| `reps_uci_neonatal` | 0.00 | 0.00 | 0.00 | 0.00 | 68.00 | 2.92 | 18.539 |
| `n_ips_total` | 0.00 | 0.00 | 1.00 | 27.00 | 1616.00 | 64.89 | 16.409 |
| `reps_salas_parto` | 0.00 | 0.00 | 1.00 | 3.00 | 58.00 | 2.36 | 15.165 |
| `reps_uci_adulto` | 0.00 | 0.00 | 0.00 | 0.00 | 149.00 | 7.98 | 14.207 |
| `pct_excepcion_muni_bdua` | 0.00 | 0.43 | 1.64 | 3.61 | 36.78 | 2.06 | 10.046 |
| `tiene_ips_nivel_3` | 0.00 | 0.00 | 0.00 | 0.00 | 1.00 | 0.13 | 7.285 |
| `n_ips_nivel_1` | 0.00 | 0.00 | 1.00 | 1.00 | 13.00 | 0.72 | 6.74 |

**Interpretación**: features con skew > |2| son candidatas a log/sqrt antes de GLM (no afecta LightGBM).

## 4. Pares altamente correlacionados (|Spearman ρ| ≥ 0.85)

**13 pares detectados** — candidatos a eliminación o PCA:

| feature A | feature B | ρ |
|---|---|---|
| `pct_rural_pobl` | `pct_cabecera_pobl` | -1.000 |
| `n_ips_nivel_3` | `tiene_ips_nivel_3` | +1.000 |
| `reps_uci_adulto` | `tiene_uci_adulto` | +1.000 |
| `reps_camas_parto` | `tiene_camas_parto` | +0.998 |
| `reps_salas_cirugia` | `tiene_salas_cirugia` | +0.995 |
| `pct_subsidiado_muni_bdua` | `pct_contributivo_muni_bdua` | -0.991 |
| `nbi_total_pct` | `nbi_miseria_pct` | +0.969 |
| `n_ips_nivel_2` | `tiene_ips_nivel_2_o_3` | +0.949 |
| `nbi_miseria_pct` | `nbi_centros_rural_disperso_pct` | +0.939 |
| `nbi_total_pct` | `nbi_centros_rural_disperso_pct` | +0.938 |
| `nbi_miseria_pct` | `nbi_servicios_pct` | +0.883 |
| `nbi_total_pct` | `nbi_servicios_pct` | +0.878 |
| `nbi_total_pct` | `nbi_cabecera_pct` | +0.851 |

## 5. VIF — Variance Inflation Factor

VIF mide cuánto se infla la varianza de un coeficiente GLM por multicolinealidad. Umbral común: VIF > 10 = multicolinealidad severa (coeficiente inestable).

**Features con VIF > 10 (12):**
- `pct_rural_pobl` — VIF = ∞
- `pct_cabecera_pobl` — VIF = ∞
- `pct_contributivo_muni_bdua` — VIF = 271.5
- `nbi_total_pct` — VIF = 71.2
- `nbi_miseria_pct` — VIF = 70.8
- `nbi_servicios_pct` — VIF = 43.2
- `nbi_vivienda_pct` — VIF = 26.2
- `reps_salas_cirugia` — VIF = 26.0
- `n_ips_total` — VIF = 13.7
- `pct_subsidiado_muni_bdua` — VIF = 13.2
- `nbi_centros_rural_disperso_pct` — VIF = 12.4
- `n_ips_nivel_3` — VIF = 11.3

**Features con VIF 5-10 (6):**
- `reps_uci_neonatal` — VIF = 9.5
- `reps_salas_parto` — VIF = 9.4
- `nbi_hacinamiento_pct` — VIF = 8.7
- `reps_uci_adulto` — VIF = 7.7
- `nbi_dependencia_pct` — VIF = 6.5
- `nbi_cabecera_pct` — VIF = 5.5

## 6. Recomendaciones accionables para `feature_selection_c3.py`

1. **Bloque NBI** (5/9 con VIF>10) → aplicar PCA. Esperamos 2 componentes principales cubran ≥85% varianza (NBI_total es una combinación lineal de los 5 componentes por diseño).
2. **Bloque REPS** (3 con VIF>10) → `n_ips_total = n_ips_nivel_{1,2,3}` por diseño, redundancia perfecta. Tirar `n_ips_total` y `tiene_ips_nivel_2_o_3` (derivados).
3. **BDUA**: `pct_subsidiado + pct_contributivo + pct_excepcion ≈ 100`. Constraint suma=100 garantiza colinealidad. Mantener solo `pct_subsidiado_muni_bdua` como referencia y derivar `pct_no_subsidiado = 100 - pct_subsidiado`.
4. **Features binarias** (flags `tiene_*`) son proxies de contínuas — evaluar si aportan info sobre la contínua correspondiente o son puro ruido para GLM. LightGBM las usa bien de todas formas.
5. **24 features muy asimétricas** → log1p antes de GLM (reduce influencia de Bogotá/Medellín en β).

## 7. Próximo paso
`feature_selection_c3.py` ejecuta:
1. PCA por bloque (NBI, REPS) → componentes que capturen ≥85% varianza
2. LASSO path (GLM Poisson) sobre feature set reducido
3. Mutual Information con razón observada
4. Intersección de (LASSO retained) ∩ (top MI) → feature set final v1.