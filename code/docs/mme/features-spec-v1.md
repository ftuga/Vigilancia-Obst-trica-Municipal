# Features Spec v1 — Gold Panel MME

> Generado: 2026-04-23 — Fase MME-A cerrada.
> Contrato de las 69 columnas de `data/mme/gold/panel_muni_semestre.parquet` (y su subset en `panel_muni_semana.parquet`).
> Documento vivo: actualizar al agregar nuevas fuentes. Versionado: gold panel maneja `feature_spec_version` en el manifest.

## Diseño general

- **Panel semestre**: 1.122 municipios × 7 años × 2 semestres = 15.708 filas.
- **Panel semana**: 1.122 × 7 × 52 = 408.408 filas (usado para C1 outbreak).
- **Silentes en 0**: cross join DIVIPOLA × tiempo + LEFT JOIN silver → conteos = 0 con `is_silent_period=1`. Los silentes son información, no missing.
- **Degradación graceful**: si una fuente bronze no está poblada, sus columnas derivadas quedan en NULL. El panel se reconstruye sin romper.

## Cobertura actual (al 2026-04-23)

| Fuente | Bronze poblado | Cobertura panel |
|---|---|---|
| SIVIGILA MME (4hyg-wa9d) | ✓ | 100% filas, 1.107/1.122 muni con casos |
| DIVIPOLA DANE | ✓ | 100% |
| Censo 2018 NBI | ✓ | 99.9% (1.123 muni) |
| Censo 2018 Población ajustada | ✓ | 99.9% (1.122 muni) |
| SIVIGILA MM (evento 550) | ✓ | muni con al menos 1 caso MM |
| BDUA MinSalud | ✓ | 99.9% (1.127 muni) |
| REPS IPS nivel + capacidad | ✓ | 80.7% (905 muni) |
| DANE EEVV Nacimientos | ✗ | 0% — **bloqueante M-001** |
| Censo 2018 Grupos étnicos | ✗ | 0% — M-003c pendiente |

---

## Columnas (69 totales)

### Identificación geográfica (7)

| Col | Tipo | Fuente | Descripción | Invariante |
|---|---|---|---|---|
| `cod_mpio` | int64 | DIVIPOLA | Código DANE 5 dígitos | Primary key junto a año+semestre |
| `cod_dpto` | int64 | DIVIPOLA | Código departamento (2 primeros de cod_mpio) | 1-99 |
| `nom_mpio` | string | DIVIPOLA | Nombre oficial DANE | — |
| `nom_dpto` | string | DIVIPOLA | Nombre oficial departamento | — |
| `tipo_municipio` | string | DIVIPOLA | Municipio / Área no municipalizada | — |
| `longitud` | float64 | DIVIPOLA | Longitud centroide (grados) | [-82, -66] |
| `latitud` | float64 | DIVIPOLA | Latitud centroide (grados) | [-4, 14] |

### Eje temporal (2)

| Col | Tipo | Descripción |
|---|---|---|
| `ano` | int32 | Año epidemiológico (2016-2022) |
| `semestre` | int16 | 1 o 2 (semana ≤26 o >26). Panel semana trae `semana` (1-52) en lugar de `semestre` |

### Régimen temporal (flags para análisis de heterogeneidad) (2)

| Col | Tipo | Valor | Uso |
|---|---|---|---|
| `covid_window` | int32 (0/1) | 1 si año ∈ {2020, 2021, 2022} | Interacciones COVID × features en modelos C3 |
| `post_c055` | int32 (0/1) | 1 si año ≥ 2022 | Sentencia C-055/2022 despenaliza aborto ≤24 sem |

_Nota: `post_paremm` (≥2023) cae FUERA de la ventana disponible; documentar como limitación._

### Outcome primario — MME (3)

| Col | Tipo | Fuente | Descripción | Uso |
|---|---|---|---|---|
| `casos_mme` | int32 | SIVIGILA 549 | Casos reportados en el período (0 para silentes) | Target variable C3 (count), C1 (weekly count) |
| `is_silent_period` | int32 (0/1) | derivado | 1 si casos_mme=0 en ese período | Feature anti-sesgo + análisis subregistro |
| `razon_mme_por_1000_nv` | float64 | SIVIGILA + EEVV | `casos_mme × 1000 / nv_esperados_periodo` | **Target final C3** cuando EEVV llegue. Benchmark INS: nacional 2023 ≈ 65.5 |

### Outcome secundario — MM (4)

| Col | Tipo | Fuente | Descripción | Uso |
|---|---|---|---|---|
| `casos_mm_semestre` | int32 | SIVIGILA 550 | Muertes maternas notificadas en el semestre | Validación cruzada con MME, análisis letalidad |
| `casos_mm_anual` | int32 | SIVIGILA 550 | Casos MM del año completo (repetido en ambos semestres) | Denominador para indicadores anuales |
| `razon_mm_por_100000_nv_anual` | float64 | SIVIGILA + EEVV | `casos_mm_anual × 100.000 / nv_anual` | Indicador estándar RMM (benchmark ODS <70) |
| `indice_letalidad_mm_mme_pct_anual` | float64 | SIVIGILA | `casos_mm_anual × 100 / casos_mme_anual` | Meta OMS <1%. Proxy de calidad de rescate (Demora III) |

### Denominador — EEVV Nacimientos (pendiente M-001) (3)

| Col | Tipo | Fuente | Descripción |
|---|---|---|---|
| `nv_anual` | float64 | DANE EEVV | Nacidos vivos ajustados por muni × año |
| `nv_esperados` | float64 | derivado | `nv_anual / 2` para semestre, `/ 52` para semana |
| `razon_mme_por_1000_nv` | float64 | derivado | Ver sección outcome — aquí denominador |

**Cuando EEVV no está poblado → NULL.** Fallback para modelado: usar `poblacion_total_2018` como offset alternativo (interpretable como incidencia poblacional, no por parto).

### Features EEVV — Indicadores obstétricos anuales (pendiente M-001) (13)

Repetidos en ambos semestres del mismo año (mismo valor s1 y s2). Proxy directo de calidad obstétrica + perfil poblacional materno.

| Col | Tipo | Demora | Interpretación |
|---|---|---|---|
| `pct_madre_lt15_eevv` | float64 | I | % NV de madres <15 años. Indicador de vulnerabilidad social extrema |
| `pct_madre_15_19_eevv` | float64 | I | % NV de madres 15-19 años. Fecundidad adolescente |
| `pct_madre_gte35_eevv` | float64 | — | % NV de madres ≥35 años. Edad materna avanzada |
| `pct_cpn_gte4_eevv` | float64 | I, III | % NV con ≥4 controles prenatales (meta Res. 3280/2018) |
| `pct_cesarea_eevv` | float64 | III | % NV por cesárea. Meta OMS <15%; en Colombia ~45% |
| `pct_rural_disperso_eevv` | float64 | II | % NV en área rural dispersa (según registro EEVV) |
| `pct_subsidiado_eevv` | float64 | II | % NV en régimen subsidiado |
| `pct_indigena_madre_eevv` | float64 | I, II | % NV de madres indígenas |
| `pct_afro_madre_eevv` | float64 | I, II | % NV de madres afro |
| `pct_bajo_peso_eevv` | float64 | III | % NV con peso <2500g |
| `pct_pretermino_eevv` | float64 | III | % NV con gestación <37 sem |
| `edad_madre_avg_eevv` | float64 | I | Edad materna promedio (años) |
| `cpn_avg_eevv` | float64 | I, III | Número promedio de CPN |

### Features Demora I-II — NBI Censo 2018 (9)

Invariantes en el tiempo (Censo 2018 como instantánea estructural).

| Col | Tipo | Fuente | Interpretación |
|---|---|---|---|
| `nbi_total_pct` | float64 | CNPV-2018-NBI.xlsx | NBI poblacional total. Rango nacional: Bogotá 3.47 — Puerto Colombia 95.96. Media 22.92 |
| `nbi_miseria_pct` | float64 | CNPV-2018-NBI | Prop con ≥2 NBI (definición "en miseria") |
| `nbi_vivienda_pct` | float64 | CNPV-2018-NBI | Componente vivienda inadecuada |
| `nbi_servicios_pct` | float64 | CNPV-2018-NBI | Componente servicios básicos |
| `nbi_hacinamiento_pct` | float64 | CNPV-2018-NBI | Hacinamiento crítico |
| `nbi_inasistencia_pct` | float64 | CNPV-2018-NBI | Inasistencia escolar |
| `nbi_dependencia_pct` | float64 | CNPV-2018-NBI | Alta dependencia económica |
| `nbi_cabecera_pct` | float64 | CNPV-2018-NBI | NBI en cabecera urbana del muni |
| `nbi_centros_rural_disperso_pct` | float64 | CNPV-2018-NBI | NBI en centros poblados y rural disperso |

**Invariante cruzado**: NBI_centros_rural > NBI_cabecera esperado en ~87% de municipios (post-fix 2026-04-23; si >30% invertidos, revisar mapeo de columnas del xlsx).

### Features Demora II — Ruralidad y Cobertura (7)

| Col | Tipo | Fuente | Interpretación |
|---|---|---|---|
| `poblacion_total_2018` | int64 | CNPV 2018 ajustada | Población muni ajustada por cobertura censal |
| `pct_rural_pobl` | float64 | CNPV 2018 | `centros_rural / total × 100`. Mean nacional 56.37 |
| `pct_cabecera_pobl` | float64 | CNPV 2018 | `cabecera / total × 100` |
| `omision_censal_censo2018` | float64 | CNPV 2018 | Fracción estimada de omisión censal (0-1). Proxy de fragilidad de registro |
| `bdua_afiliados_total_2022` | int64 | BDUA hn4i-593p | Afiliados totales (snapshot 2022-04) |
| `pct_subsidiado_muni_bdua` | float64 | BDUA | % afiliados régimen subsidiado. Mean 77% |
| `pct_contributivo_muni_bdua` | float64 | BDUA | % afiliados contributivo |
| `pct_excepcion_muni_bdua` | float64 | BDUA | % régimen excepción (magisterio, FFMM) |

_Invariante: `pct_subsidiado + pct_contributivo + pct_excepcion ≈ 100` (puede sumar <100 si hay indígenas sin asignar; aceptable ±2pp)._

### Features Demora III — Oferta obstétrica REPS (16)

Snapshot REPS con fecha de corte variable 2022-2026 (tratado como estructural).

| Col | Tipo | Fuente | Interpretación |
|---|---|---|---|
| `n_ips_total` | int32 | REPS ugc5-acjp | IPS habilitadas totales. Bogotá 1.616, Cali 609, Uribia 8 |
| `n_ips_nivel_1` | int32 | REPS | IPS de nivel I (baja complejidad) |
| `n_ips_nivel_2` | int32 | REPS | IPS de nivel II (mediana complejidad) |
| `n_ips_nivel_3` | int32 | REPS | IPS de nivel III (alta complejidad). Solo 18 muni nacional |
| `n_ips_ese` | int32 | REPS | IPS públicas (Empresa Social del Estado) |
| `tiene_ips_nivel_3` | int32 (0/1) | REPS | Flag binario |
| `tiene_ips_nivel_2_o_3` | int32 (0/1) | REPS | Flag más permisivo (resolución local complicaciones moderadas) |
| `reps_camas_parto` | int32 | REPS s2ru-bqt6 | Camas "Atención del Parto" habilitadas. Nacional 669 |
| `reps_uci_adulto` | int32 | REPS | Camas UCI Adulto. Nacional 921. **Proxy de UCI-O** — REPS no codifica UCI-O separada |
| `reps_uci_neonatal` | int32 | REPS | Camas UCI Neonatal (proxy madurez obstétrica IPS) |
| `reps_salas_parto` | int32 | REPS | Salas de partos habilitadas |
| `reps_salas_cirugia` | int32 | REPS | Salas de cirugía + quirófanos (cesárea urgencia) |
| `tiene_camas_parto` | int32 (0/1) | REPS | Flag |
| `tiene_uci_adulto` | int32 (0/1) | REPS | Flag |
| `tiene_salas_cirugia` | int32 (0/1) | REPS | Flag |
| `score_capacidad_obstetrica` | int32 (0-3) | derivado | Suma de {tiene_camas_parto, tiene_uci_adulto, tiene_salas_cirugia}. **Proxy compuesto Demora III** recomendado por mme-domain-expert |

**Limitaciones documentadas:**
- REPS no tiene UCI-O explícita (expert-flagged). UCI adulto es el mejor proxy disponible sin acceso directo al portal MinSalud.
- Banco de sangre NO está en `s2ru-bqt6` (es servicio habilitado, dataset separado — pendiente M-005b).
- Fecha de corte REPS 2022-2026 → asumimos oferta estructural (cambia poco intra-año).

### Placeholders pendientes (3)

| Col | Tipo | Origen planeado | Estado |
|---|---|---|---|
| `pct_indigena_censo` | float64 | CNPV 2018 grupos étnicos | M-003c — URL DANE sin descubrir |
| `pct_afro_censo` | float64 | CNPV 2018 grupos étnicos | M-003c |
| `tiene_banco_sangre_reps` | int32 (0/1) | REPS servicios habilitados | M-005b |

---

## Reglas de uso en modelado

### Target C3 (Poisson/NegBin + GBM)

**Outcome:** `casos_mme_semestre` (count).

**Offset (principal):** `log(nv_esperados)` — requiere EEVV M-001.
**Offset (fallback actual):** `log(poblacion_total_2018 / 2)` — interpretable como incidencia poblacional, no por parto. Cuando llegue EEVV, reemplazar sin romper.

**Features estructurales (no temporales):** `nbi_total_pct`, `nbi_hacinamiento_pct`, `nbi_inasistencia_pct`, `pct_rural_pobl`, `omision_censal_censo2018`, `pct_subsidiado_muni_bdua`, `score_capacidad_obstetrica`, `n_ips_nivel_3`, `tiene_ips_nivel_3`, `reps_uci_adulto`, `reps_camas_parto`.

**Features EEVV (anuales, cuando disponibles):** 13 `pct_*_eevv` + `edad_madre_avg_eevv` + `cpn_avg_eevv`.

**Features temporales:** `covid_window`, `post_c055`, `ano` (como tendencia).

**Suavizamiento bayesiano:** obligatorio para muni con `nv_anual < 50` (Clayton-Kaldor). Sin suavizar, la razón es inestable y domina el ranking.

**Split temporal:** train ≤2020 / val 2021 / test 2022. **NUNCA random split.**

**Reporte a 2 escalas:** muni + dpto (mitigación MAUP). El ranking debe ser robusto al cambio de unidad.

### Target C1 (Outbreak detection)

**Panel:** `panel_muni_semana.parquet`.
**Outcome:** `casos_mme` semanal.
**Baseline esperado:** histórico móvil por muni + estacionalidad Fourier.
**Features:** solo `covid_window`, `score_capacidad_obstetrica`, `pct_rural_pobl`, `nbi_total_pct` (feature set pequeño; la señal principal es temporal).
**Métodos:** EARS C1/C2/C3, Farrington Flexible, Prophet + residuales >2σ, Isolation Forest.
**Backtesting:** precision/recall a horizonte 2/4/6 semanas.

---

## Control de cambios

| Versión | Fecha | Cambio |
|---|---|---|
| v1.0 | 2026-04-23 | Primera versión. Gold con 69 columnas, 5 fuentes integradas (SIVIGILA+DIVIPOLA+Censo2018+BDUA+REPS+SIVIGILA MM). EEVV pendiente. |

## Bloqueantes para v2 (cuando ameriten reescribir)

1. Llegada de EEVV (M-001) → completa `nv_*`, `razon_mme_por_1000_nv`, y los 13 `pct_*_eevv`.
2. Resolución de étnia CNPV (M-003c) → completa `pct_indigena_censo`, `pct_afro_censo`.
3. Servicios habilitados REPS (M-005b) → completa `tiene_banco_sangre_reps`.
4. Proyecciones DANE 2018+ por edad/sexo (M-004) → habilita denominador alternativo `pob_mujeres_15_49`.
