# EDA del Target C3 — Diagnóstico pre-modelado

> Generado: 2026-04-24 · Fuente: `data/mme/gold/panel_muni_semestre.parquet`

## 1. Target: `casos_mme` (count, entero ≥0)
- Observaciones: **15,694** filas (muni × semestre)
- **Media**: 11.167
- **Varianza**: 7935.486
- **Dispersion ratio (var/mean)**: `710.631`
- **% zeros (silentes)**: 26.91%
  - %zeros esperado si Poisson(λ=11.17): **0.00%**
- **max**: 3079 casos
- **Percentiles**: p50=2, p75=6, p95=29, p99=131, p99.9=942
- **Outliers IQR** (y > p75 + 1.5·IQR = 12.0): 1,962 filas

## 2. Razón MME / 1.000 hab (proxy pre-EEVV)
- p50 = 0.292
- p95 = 1.118
- p99 = 1.656
- Razón >20/1.000 hab (extremo): **0 filas** — candidatos para winsorization o Clayton-Kaldor EB

## 3. Decisión de familia de modelo

- ✓ **NegBin preferido**: dispersion ratio = 710.63 > 1.5 (Poisson asume = 1). Confirma sobredispersión.
- ℹ **%zeros moderado** = 26.9%. Poisson/NegBin manejan si dispersion lo permite; ZIP opcional.

## 4. Top-10 muni con razón observada más alta

| cod_mpio | muni | dpto | año | sem | casos | pob | razón |
|---|---|---|---|---|---|---|---|
| 15723 | SATIVASUR | BOYACÁ | 2017 | 2 | 2 | 1,097 | 3.65 |
| 15723 | SATIVASUR | BOYACÁ | 2016 | 2 | 2 | 1,097 | 3.65 |
| 44430 | MAICAO | LA GUAJIRA | 2022 | 2 | 282 | 170,582 | 3.31 |
| 15215 | CORRALES | BOYACÁ | 2019 | 2 | 4 | 2,498 | 3.20 |
| 27745 | SIPÍ | CHOCÓ | 2018 | 2 | 5 | 3,174 | 3.15 |
| 50686 | SAN JUANITO | META | 2018 | 1 | 2 | 1,307 | 3.06 |
| 52233 | CUMBITARA | NARIÑO | 2021 | 2 | 9 | 5,948 | 3.03 |
| 86219 | COLÓN | PUTUMAYO | 2021 | 2 | 8 | 5,407 | 2.96 |
| 13780 | TALAIGUA NUEVO | BOLÍVAR | 2021 | 1 | 19 | 13,108 | 2.90 |
| 18205 | CURILLO | CAQUETÁ | 2022 | 1 | 11 | 7,593 | 2.90 |

## 5. Plots

- `eda_target_distributions.png` — distribuciones casos_mme, log1p, razón
- `eda_target_dispersion_by_year.png` — dispersion ratio por año (diagnóstico familia)

## 6. Conclusión y siguiente paso

Basado en el diagnóstico:
1. **Familia primaria: NegBin GLM** con offset `log(pob_sem)`.
2. **Challenger: LightGBM con objective Poisson** (o Tweedie p=1.1 si zeros son relevantes).
3. **Pre-procesamiento obligatorio**: Clayton-Kaldor Empirical Bayes para muni con NV_sem < 25 (estabilización razón).
4. **Si Spearman dpto < 0.5 en val**: agregar interacciones manuales (NBI × ausencia_nivel_3, rural × sin_UCI_adulto).
5. **Siguiente paso**: `eda_features_c3.py` — distribuciones + correlación + VIF.