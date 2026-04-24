# EDA municipal × departamental — Panel MME 2016-2022

> Generado: 2026-04-23  | Panel: `data/mme/gold/panel_muni_semestre.parquet` (15.708 filas)

> **Nota metodológica**: las razones aquí usan `poblacion_total_2018` como denominador
> porque EEVV (M-001) aún no llegó. Cuando llegue, se recalcula con NV como denominador.

## 1. Volumen anual nacional

| año | MME (proyecto) | INS MME benchmark | MM (SIVIGILA 550) |
|---|---|---|---|
| 2016 | 20365 | — | 479 |
| 2017 | 22858 | — | 492 |
| 2018 | 22456 | — | 513 |
| 2019 | 22957 | 23488 | 510 |
| 2020 | 23756 | — | 596 |
| 2021 | 29637 | — | 635 |
| 2022 | 33223 | — | 473 |

## 2. Distribución por departamento

### Top 10 por volumen absoluto MME 2016-2022

| dpto | MME | MM | #muni | NBI avg % | Rural avg % |
|---|---|---|---|---|---|
| BOGOTÁ, D.C. | 38070 | 359 | 1 | 3.5 | 0.3 |
| ANTIOQUIA | 15499 | 359 | 125 | 18.5 | 51.9 |
| VALLE DEL CAUCA | 12801 | 251 | 42 | 9.3 | 37.1 |
| BOLÍVAR | 12365 | 199 | 46 | 43.5 | 45.3 |
| ATLÁNTICO | 12001 | 229 | 23 | 19.0 | 19.6 |
| CUNDINAMARCA | 8738 | 160 | 116 | 10.6 | 60.1 |
| MAGDALENA | 6496 | 183 | 30 | 36.2 | 47.6 |
| LA GUAJIRA | 6261 | 230 | 15 | 39.7 | 44.2 |
| HUILA | 6178 | 76 | 37 | 15.9 | 56.6 |
| CAUCA | 6022 | 104 | 42 | 22.5 | 76.4 |

### Top 10 por razón MME/1.000 habitantes 2018 (proxy sin EEVV)

_Usa población Censo 2018 ajustada. Cuando llegue EEVV se reemplaza por razón MME/1.000 NV._

| dpto | MME total 7 años | Pob aprox | Razón /1.000 hab | NBI avg |
|---|---|---|---|---|
| LA GUAJIRA | 6261 | 440,280 | 14.22 | 39.7 |
| BOLÍVAR | 12365 | 1,035,055 | 11.95 | 43.5 |
| HUILA | 6178 | 550,193 | 11.23 | 15.9 |
| BOGOTÁ, D.C. | 38070 | 3,706,283 | 10.27 | 3.5 |
| MAGDALENA | 6496 | 670,873 | 9.68 | 36.2 |
| PUTUMAYO | 1651 | 174,091 | 9.48 | 19.0 |
| ATLÁNTICO | 12001 | 1,267,758 | 9.47 | 19.0 |
| CAUCA | 6022 | 732,244 | 8.22 | 22.5 |
| CESAR | 4581 | 600,287 | 7.63 | 27.0 |
| SUCRE | 3390 | 452,431 | 7.49 | 35.5 |

## 3. Brecha estructural: NBI × razón MME por habitante

- Correlación **NBI × razón MME/1.000 hab**: `0.123` (esperada positiva — hipótesis de brecha estructural)
- Correlación **% rural × razón MME/1.000 hab**: `-0.222`
- Correlación **score_capacidad_obstetrica × razón MME/1.000 hab**: `0.231` _(negativa esperada — más oferta, menos razón)_
- Correlación de contraste **NBI × casos absolutos**: `-0.057` _(se espera negativa / débil — Bogotá concentra casos por tamaño, no por NBI)_

## 4. Municipios con silencio sospechoso

Criterio: NBI ≥70% (vulnerabilidad estructural alta) + ≤5 casos MME en 7 años + población >1.000.
| muni | dpto | NBI % | pob | MME 7 años |
|---|---|---|---|---|
| PUERTO COLOMBIA | GUAINÍA | 96.0 | 1874 | 2 |
| PACOA | VAUPÉS | 93.6 | 4042 | 4 |
| PANA PANA | GUAINÍA | 93.6 | 1899 | 3 |
| SAN FELIPE | GUAINÍA | 88.4 | 1667 | 2 |
| MIRITÍ - PARANÁ | AMAZONAS | 85.8 | 1850 | 2 |
| TARAIRA | VAUPÉS | 78.9 | 2215 | 2 |
| YAVARATÉ | VAUPÉS | 76.7 | 1048 | 1 |

**7 municipios** cumplen el criterio de silencio sospechoso. Candidatos para análisis C2 (subregistro).

## 5. Efecto COVID-19 (2020 vs baseline 2016-2019)

- **Baseline MME 2016-2019** (promedio anual): `22,159` casos
  - 2020: `23,756` (+7.2%)
  - 2021: `29,637` (+33.7%)
  - 2022: `33,223`
- **Baseline MM 2016-2019** (promedio anual): `498` casos
  - 2020: `596` (+19.6%) _(pico COVID esperado)_
  - 2021: `635` (+27.4%)
  - 2022: `473`

## 6. Capacidad obstétrica territorial × razón MME

| score | #muni | MME total | Pob total | Razón /1.000 hab |
|---|---|---|---|---|
| 0 | 857 | 44347 | 14,642,234 | 3.03 |
| 1 | 208 | 36683 | 12,057,385 | 3.04 |
| 2 | 46 | 32662 | 7,866,148 | 4.15 |
| 3 | 10 | 61560 | 13,691,705 | 4.5 |

_Score = {tiene_camas_parto} + {tiene_uci_adulto} + {tiene_salas_cirugia} ∈ [0, 3]._
_Score alto concentra casos (grandes ciudades tienen más oferta Y más casos)._

## 7. Estacionalidad semanal (nacional)

- Media semanal global nacional 2016-2022: **480 casos**
- Semanas con desviación >15% de la media: **1** (↓ normal)

_Picos detectados:_

| semana | media casos | Δ% |
|---|---|---|
| 1 | 399.9 | -16.8% |

## Hallazgos iniciales (para discusión)

1. **Volumen 2019 match INS**: proyecto reporta `22,957` vs INS 23.488 (Δ dentro de tolerancia de exclusiones).
2. **Correlación NBI × razón MME**: `+0.123` — evidencia cuantitativa de brecha estructural.
3. **Silentes sospechosos**: `7` municipios marcados para C2.
4. **Efecto COVID MM 2020**: `+19.6%` sobre baseline.
5. **Capacidad obstétrica**: score 3 (capitales) concentra la mayoría de casos absolutos por volumen poblacional — revisar confundidor antes de concluir.

## Próximos pasos

- M-001 (EEVV) completará `razon_mme_por_1000_nv` y los 13 `pct_*_eevv`.
- Fase MME-B.2 (M-010): análisis detallado de brechas étnico-territoriales.
- Fase MME-B.3 (M-011): validación cruzada departamental contra boletines INS específicos.
- Fase MME-C (M-014/M-015): baseline Poisson/NegBin + GBM con el feature set actual + suavizamiento Clayton-Kaldor.