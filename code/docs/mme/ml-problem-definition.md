# Definición formal del problema ML — MME Colombia

> Documento fundamental del proyecto. Gate metodológico antes de modelar.
> Versión: 1.0 · 2026-04-23 · Autor: equipo técnico (post consulta `mme-domain-expert`)

---

## 1. Problema de negocio (quién tiene el dolor)

**Usuario primario:** Plan de Aceleración para la Reducción de la Mortalidad Materna (**PAREMM v5**, MinSalud Colombia, 2023→).

**Dolor concreto:**
PAREMM v5 necesita asignar recursos escasos (apertura de UCI Obstétrica, brigadas extramurales indígenas, refuerzo de rutas de referencia RIAS-MPN, fortalecimiento de UPGD) entre **1.122 municipios** con brechas territoriales y étnicas extremas (RMM 2-6× el promedio nacional en territorios Wayúu, Sikuani, Embera; razón MME/1.000 NV nacional 2023 = 65.5, con alta heterogeneidad sub-nacional).

Las decisiones de asignación hoy se toman con:
- Ranking cualitativo por boletines epidemiológicos INS.
- Juicio experto de Direcciones Territoriales de Salud.
- Sin cuantificación reproducible de la vulnerabilidad estructural por municipio.
- Sin distinción explícita entre "municipio de alta vulnerabilidad" vs "municipio subnotificador".

**Usuario secundario:** Instituto Nacional de Salud (INS) Subdirección de Vigilancia en Salud Pública — requiere detección temprana de outbreaks de MME con resolución municipal × semana epidemiológica (protocolo Pro_MME 2024 exige unidad de análisis de caso en <30 días).

---

## 2. Pregunta de investigación

> **¿Es posible construir un Índice de Vulnerabilidad Obstétrica Municipal, explicable e interpretable, que operacionalice cuantitativamente el modelo de las 3 demoras de Thaddeus & Maine (1994) usando exclusivamente datos públicos colombianos, para priorizar la asignación de recursos de PAREMM v5?**

**Preguntas secundarias:**
- ¿La vulnerabilidad territorial predicha se sostiene bajo distintas escalas geográficas (municipio vs departamento) — prueba de robustez MAUP?
- ¿Qué determinantes (Demora I, II, III) tienen mayor peso relativo en la predicción según SHAP?
- ¿Es posible detectar outbreaks semanales de MME con precisión útil (precision@top-k, horizonte 2-6 semanas)?

---

## 3. Problema ML (targets formales)

### Target C3 — Índice de Vulnerabilidad Obstétrica Municipal (PRIMARIO)

**Encuadre formal: regresión count (GLM) en panel municipal — NO serie de tiempo, NO clasificación.**

#### ¿Qué tipo de problema ML es?

| Dimensión | C3 (este target) | Qué NO es |
|---|---|---|
| Encuadre | **Regresión de conteos** con offset poblacional | NO forecasting temporal (no predecimos semestre siguiente) |
| Familia canónica | GLM Poisson / Negative Binomial | NO regresión continua vanilla (pierde naturaleza count) |
| Challenger | Gradient boosting con objective Poisson/Tweedie | NO RF estándar (pierde offset natural) |
| Unidad panel | municipio × semestre (n=1.122 × 2 × 7 ≈ 15.7k filas) | NO ARIMA ni Prophet (granularidad insuficiente y razón es el target, no el count bruto) |
| Temporal features | `covid_window`, `post_c055`, `ano` centrado | NO lags autoregresivos (C3 es estático-con-contexto-temporal) |

**Serie de tiempo sí aparece en C1 outbreak detection (muni × semana con EARS/Farrington/Prophet) — es un problema distinto, con modelo distinto.**

#### Definición canónica del target

```
Unidad:            (muni_i, semestre_t)
y_{i,t}:           casos_mme_{i,t}            (entero ≥0)
offset_{i,t}:      log(NV_esperados_{i,t})    (desde EEVV — fallback log(pob/2))
tasa latente:      λ_{i,t} = E[y_{i,t}] / exp(offset_{i,t})
razón observada:   razon_{i,t} = y_{i,t} × 1.000 / NV_esperados_{i,t}   [MME/1.000 NV]
```

**Un SOLO target.** Todos los modelos se evalúan en el mismo espacio: se predice `y` con su offset, se convierte a razón vía `pred/exp(offset)×1.000`, y las métricas comparan razón predicha vs observada.

**Variable clasificatoria derivada** (opcional, para reporting): `alta_vulnerabilidad_{i,t} = 1 si razon_{i,t} > p80 nacional`. **No es target primario** — se usa solo para métrica `precision@top-k` (decisión operacional PAREMM).

#### Justificación epidemiológica de la familia

- **Estándar INS/OMS**: todos los boletines reportan MME/1.000 NV. Un GLM Poisson con offset `log(NV)` modela exactamente esa razón bajo el supuesto de tasa constante por muni.
- **Sobredispersión esperada**: en counts municipales agregados, var > mean (muni pequeños con varianza alta, muni grandes con varianza relativa baja). Si el diagnóstico confirma dispersion_ratio > 1.5, **NegBin** reemplaza a Poisson (igual interpretabilidad + manejo correcto de varianza).
- **Zero-inflation check**: si % de filas con casos=0 > 40%, evaluar **Zero-Inflated Poisson (ZIP)** como alternativa. Nuestro panel con silentes=27% no sugiere ZIP como primera opción.
- **No-linealidades**: un **LightGBM** con objective Poisson o Tweedie entra como *challenger* del GLM. Captura interacciones (ej. NBI_alto × sin_IPS_nivel3) que el GLM no puede.
- **Clayton-Kaldor Empirical Bayes**: obligatorio pre-modelo para muni con NV<50/año. Distribución Poisson-Gamma: `y_i ~ Pois(n_i·λ_i)`, `λ_i ~ Gamma(α, β)` con `α, β` estimados por método de momentos sobre la muestra completa. **NO shrinkage ad-hoc**.

#### Valor operacional (a quién sirve y cómo se usa)

| Output del modelo | Decisión que soporta | Usuario |
|---|---|---|
| `razon_predicha(muni)` | Ranking territorial de municipios con mayor tasa esperada dado perfil estructural | PAREMM v5 — asignación de recursos |
| `razon_observada − razon_predicha` (residual) | Detección de municipios con exceso o subregistro inesperado | INS Vigilancia + DTS |
| SHAP global | Priorización de políticas (mejor efecto marginal: reducir NBI vs abrir UCI-O) | MinSalud policy |
| SHAP por muni | Diagnóstico cualitativo del perfil de vulnerabilidad municipal | Direcciones Territoriales |

**El modelo NO predice "qué va a pasar el próximo semestre".** Predice **"cuál es la tasa esperada dado el perfil estructural actual"**. La diferencia entre observado y esperado es el valor interpretativo.

#### Método de optimización

- **GLM Poisson/NegBin**: IRLS (Iteratively Reweighted Least Squares) — closed-form para el loss, no hay hyperparams excepto regularización opcional.
- **LightGBM**: gradient boosting, hyperparams tuneados con **Optuna** (TPE sampler, 100 trials, MedianPruner sobre Spearman dpto val 2021). Espacio de búsqueda:
  - `num_leaves ∈ [15, 127]`, `learning_rate ∈ [0.01, 0.1]` (log), `min_data_in_leaf ∈ [10, 100]`
  - `feature_fraction ∈ [0.6, 1.0]`, `bagging_fraction ∈ [0.6, 1.0]`, `bagging_freq ∈ [0, 10]`
  - `lambda_l1 ∈ [1e-8, 10]` (log), `lambda_l2 ∈ [1e-8, 10]` (log), `max_depth ∈ [3, 12]`
  - `min_gain_to_split ∈ [0, 1]`
- **Criterio de selección**: maximizar Spearman dpto val 2021. Empates → menor MAE razón.
- **Feature set**: NO se tiran 35 features al modelo. Antes pasan por (1) análisis VIF + PCA sobre bloques correlacionados (NBI→2 comp, REPS→2 comp), (2) LASSO path, (3) mutual information con y. El set final se justifica en `reports/mme/models/feature_selection_c3.md`.

**Métrica de éxito primaria:**
- **MAE razón** a nivel municipio en el test set (2022).
- **Spearman rank correlation** entre predicción y observado a nivel dpto (robustez MAUP).
- **Precision@top-50** (¿los 50 muni con mayor score predicho coinciden con los 50 de mayor razón real?).

**Métricas secundarias:**
- Brier score / calibración (si se trata como prob).
- PR-AUC para clasificación binaria de `alta_vulnerabilidad`.

**Constraint metodológico duro:**
- Suavizamiento bayesiano empírico Clayton-Kaldor **obligatorio** para municipios con NV < 50/año (razón cruda inestable, domina ranking).
- Split temporal **estricto**: train ≤ 2020, val 2021, test 2022. NUNCA random split.

---

### Target C1 — Detección de outbreaks semanales (COMPLEMENTARIO)

**Tipo:** detección de anomalías univariada con contexto territorial.

**Unidad:** municipio × semana epidemiológica.

**Señal de entrada:**
```
serie casos_mme_{i, semana_epi} 2016-2022 por muni con población > umbral
```

**Output:**
```
alerta_{i, t} = 1 si casos_{i, t} > baseline_esperado_{i, t} + k * σ_{i, t}
score_severidad = (casos - baseline) / σ
```

**Métrica:** precision / recall a horizonte 2/4/6 semanas, backtesting contra casos observados.

**Métodos candidatos:** EARS C1/C2/C3 (CDC), Farrington Flexible, Prophet + residuales >2σ, Isolation Forest multivariado.

---

### C2 — subregistro municipal (LIMITACIÓN, no target)

Clasificación heurística (NO ML) de municipios según patrón de notificación {adecuado, sub, sobre, silente}. Se usa como análisis cualitativo de limitaciones, no como target principal — el riesgo de **etiquetas circulares** (el modelo aprende a detectar lo que ya sabemos) impide operarlo como predicción.

---

## 4. Features (resumen; detalle en `features-spec-v1.md`)

Mapeo a las 3 demoras de Thaddeus & Maine (1994):

| Demora | Concepto | Features disponibles (9 fuentes × ~69 columnas gold) |
|---|---|---|
| **I — decidir buscar atención** | reconocimiento de signos, decisión familiar | `nbi_inasistencia_pct` (proxy educativo), `pct_madre_lt15_eevv` (pendiente EEVV), `edad_madre_avg_eevv` |
| **II — acceso al servicio** | distancia, transporte, barreras económicas/culturales | `pct_rural_pobl`, `nbi_total_pct`, `pct_subsidiado_muni_bdua`, `omision_censal_censo2018`, `pct_indigena_censo` (pendiente M-003c) |
| **III — atención adecuada y oportuna** | calidad clínica, oferta, tiempo de manejo | `tiene_ips_nivel_3`, `n_ips_nivel_3`, `reps_camas_parto`, `reps_uci_adulto`, `score_capacidad_obstetrica`, `n_ips_ese` |

**Régimen temporal:** `covid_window` (2020-2022), `post_c055` (≥2022).

**Flags anti-sesgo:** `is_silent_period`, `omision_censal_censo2018`.

---

## 5. Restricciones y compromisos no negociables

### 5.1 Éticos y legales

- **Ley 1581 de 2012 (Habeas Data Colombia):** todos los datos de MME son **agregados por municipio × tiempo**. Ninguna variable individual. El modelo NO predice riesgo de una mujer específica.
- **Resolución 8430 de 1993:** no aplica investigación en humanos (datos ya anonimizados + agregados por INS).
- **Publicación:** cualquier export pasa por revisión `security-auditor` para verificar que no reidentifique (alta cardinalidad en muni pequeños + variable catastrófica puede reidentificar).

### 5.2 Metodológicos

- **Ecological fallacy:** el modelo es **municipal**. NUNCA interpretar SHAP individual como riesgo personal. Disclaimer obligatorio en cualquier visualización. → regla reforzada por `mme-domain-expert`.
- **MAUP (Modifiable Areal Unit Problem):** reportar resultados a **2 escalas** (muni + dpto). Si ranking top-20 cambia radicalmente entre escalas, el resultado no es robusto.
- **No-stationarity:** protocolo 549 estable desde ~2016, pero régimen PAREMM (≥2023) fuera de ventana. Flag temporal obligatorio como covariate.
- **Suavizamiento bayesiano:** obligatorio. Clayton-Kaldor (o EB Poisson-Gamma) para muni con NV<50/año.

### 5.3 Operacionales

- **Data:** 100% pública, sin trámites. Fuente principal SIVIGILA `4hyg-wa9d`. EEVV por descarga manual (procedimiento documentado en `docs/mme/dane-eevv-procedure.md`).
- **Reproducibilidad:** pipeline completo debe correr end-to-end en el stack `proyecto_01/` (Airflow + MLflow + MinIO + Postgres + Prometheus + Grafana).
- **Ventana temporal real:** **2016-2022** (el dataset SIVIGILA publicado no cubre 2023-2024 aún).

---

## 6. Criterios de aceptación del modelo

Para que un baseline C3 se considere **útil** (no necesariamente SOTA):

| Criterio | Umbral | Racional |
|---|---|---|
| Split temporal respetado | 100% | Regla dura, no negociable |
| Spearman ρ dpto (test 2022) | ≥ 0.65 | Ranking departamental debe ser útil para PAREMM |
| Precision@top-50 muni | ≥ 0.50 | Al menos la mitad del top-50 predicho coincide con realidad |
| Clayton-Kaldor aplicado | sí | Obligatorio en muni < 50 NV/año |
| SHAP global + 5 SHAP municipales ejemplares | entregado | Explicabilidad requerida por PAREMM |
| Disclaimer ecological fallacy | en UI y reporte | No negociable |
| Análisis sensibilidad cobertura REPS | entregado | Experto lo flagged como mandatorio |
| Modelo en MLflow Registry | Production | Requisito MLOps |
| Scoring servido vía API | 200 OK | Requisito MLOps |

**Gate Go/No-Go para publicar:**
- Los 9 criterios cumplidos.
- Revisión `mme-domain-expert` aprueba interpretaciones clínicas.
- Revisión `security-auditor` aprueba que no reidentifica.

---

## 7. Fuera de scope

Esto NO es el problema:

- ❌ Predicción de riesgo obstétrico de una mujer individual (ecological fallacy).
- ❌ Reemplazo del protocolo clínico 549 o del juicio del personal de salud.
- ❌ Diagnóstico automático de subregistro (etiquetas circulares, va como limitación).
- ❌ Modelo causal formal (hacemos asociación + SHAP; causal inference con DAGs queda para trabajo futuro).
- ❌ Evaluación del impacto de PAREMM v5 como intervención (la ventana 2016-2022 no cubre suficiente post-PAREMM).
- ❌ Predicción a nivel nacional agregado (el valor está en la granularidad municipal).
- ❌ Integración con sistemas clínicos operacionales (CAC, SIRENAGEST, historias clínicas) — estas fuentes exigen trámite.

---

## 8. Riesgos que el modelo puede sufrir

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| Subregistro étnico-territorial sesga predicciones (muni indígenas "invisibles") | Alta | Alto | Feature `omision_censal_censo2018` + `score_capacidad_obstetrica`; análisis sensibilidad excluyendo silentes; disclaimer explícito |
| Confounding poblacional (Bogotá concentra casos por tamaño, no por NBI) | Alta | Medio | Offset `log(NV)` en Poisson; razón como target interpretable, no casos absolutos |
| Ventana 2016-2022 no cubre post-PAREMM 2023+ | Cierta | Bajo | Documentar como limitación; no extrapolar más allá |
| Denominador EEVV llega tarde / no llega | Media | Alto | Fallback `log(poblacion_total_2018)` ya implementado; pipeline degrada gracefully |
| REPS no codifica UCI-O separada | Cierta | Medio | Proxy `score_capacidad_obstetrica` documentado; análisis sensibilidad |
| Drift natural post-2022 cuando lleguen datos nuevos | Alta | Medio | Evidently + PSI/KS en DAG drift, retrain trigger automático |

---

## 9. Diferencia con el stack anterior (rugpull)

Aquí documentamos por qué este problema no es como el anterior:

| Dimensión | Rugpull DeFi (legacy) | MME Colombia (actual) |
|---|---|---|
| Dominio | Financiero on-chain | Salud pública territorial |
| Escala | ~1.000 pools × 17 meses | 1.122 muni × 7 años |
| Target | Binario (`is_rugpull`) | Count con offset (razón MME/1000 NV) |
| Unidad decisión | Pool individual | Municipio agregado |
| Ético | Irrelevante (tokens públicos) | Habeas Data + ecological fallacy |
| Usuario | Traders / LP providers | Gobierno (PAREMM / INS) |
| Data | 100% on-chain fresh | 100% oficial pública CO |
| Modelo exitoso | f1 1.00 (overfit evidente) | Spearman ≥0.65 es útil (real-world) |
| Interpretabilidad | Opcional | **Obligatoria** (SHAP + disclaimer) |
| Reentrenamiento | Por ciclo de 12 batches | Anual cuando INS publica |

El **stack MLOps** (Airflow, MLflow, MinIO, Postgres, Prometheus, Grafana) se reusa intacto. **Lo que cambia son los DAGs, el feature spec, el modelo, la API de serving y el frontend.**

---

## Versionado

| Versión | Fecha | Cambio |
|---|---|---|
| v1.0 | 2026-04-23 | Primera versión post-consulta `mme-domain-expert` + EDA M-009 con hallazgos validados contra INS. |
