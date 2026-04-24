# Research Log — MME Colombia

> Documento vivo de investigación del pivote del proyecto `ent-tesis` a Morbilidad Materna Extrema (MME) en Colombia. Todo lo relevante — contexto, datos validados, decisiones, normatividad, advertencias — se acumula acá y luego alimenta el README final del proyecto.
>
> **Alcance**: trabajo investigativo (no tesis formal con defensa). Solo data 100% pública, sin trámites a entidades.

---

## 0. Cronología de decisiones

| Fecha | Decisión |
|---|---|
| 2026-04-23 | Pivote de dominio: rugpull DeFi → salud pública colombiana |
| 2026-04-23 | Tema priorizado: Morbilidad Materna Extrema (MME, evento SIVIGILA 549) |
| 2026-04-23 | Creación del agente `mme-domain-expert` (project-local) con contexto completo |
| 2026-04-23 | Descarte de Target B original (clasif. individual) por falta de microdata pública |
| 2026-04-23 | Descarte de Cáncer/CAC como alternativa (CAC solo publica PDFs, no microdata abierta) |
| 2026-04-23 | **Target principal: C3 — Vulnerabilidad Obstétrica Municipal** |
| 2026-04-23 | **Target complementario: C1 — Outbreak Detection** |
| 2026-04-23 | Ventana temporal objetivo: 2016-2024 (por estabilidad de protocolo 549) |
| 2026-04-23 | **Ingesta bronze ejecutada** — 65.393 filas 2016-2022, 0 nulos, 0 duplicados, 35 deptos, 1.163 municipios |
| 2026-04-23 | **Ventana real confirmada: 2016-2022** — el dataset `4hyg-wa9d` no publica 2023-2024 aún (título es engañoso) |
| 2026-04-23 | Split temporal ajustado: train 2016-2020, val 2021, test 2022 |
| 2026-04-23 | **DIVIPOLA bronze ingerido** — 1.122 municipios + 33 deptos DANE dic/2024 |
| 2026-04-23 | **Reconciliación bronze ↔ DIVIPOLA**: 97.99% casos limpio; 98.6% cobertura municipal (16 silentes) |
| 2026-04-23 | **Silver MME construido** — 64.562 filas, 175.274 casos, 1.107 municipios, 33 deptos |
| 2026-04-23 | **Gold panels construidos**: municipio-semestre (15.708 filas, 27% silentes) + municipio-semana (408.408 filas, 84% silentes) |
| 2026-04-23 | Gap identificado: nacidos vivos DANE requiere descarga manual EEVV microdata — placeholder en gold (columnas NULL listas para join) |

---

## 1. Contexto del problema

### 1.1 Estado del sistema de salud colombiano 2026
- Sistema de salud inicia 2026 desfinanciado; patrimonio en rojo ≈ $15.8 billones.
- Siniestralidad >108%; 45% de afiliados en EPS intervenidas.
- Tiempos de espera promedio: 131 días medicamentos, 92 días especialista.
- 91% de quejas relacionadas con barreras de acceso.

### 1.2 Mortalidad y Morbilidad Materna en Colombia
- **MME 2019**: 23.488 casos / 633.878 nacidos vivos ≈ 3.7% de embarazos.
- **MME 2023**: 38.505 casos, razón 65.5 / 1.000 NV (tendencia ascendente 2012-2023).
- **MM 2024**: reducción 32.7% vs 2023 — nivel más bajo en 20 años (atribuido a PAREMM v5).
- Relación MME/MM >35 (meta OMS).
- **Brechas étnico-territoriales críticas**: RMM 2-6× el promedio nacional en indígenas (Wayúu, Sikuani, Embera). Departamentos críticos: Chocó, La Guajira, Vaupés, Vichada, Guainía.
- **Causas agrupadas 2022-2024**: trastornos hipertensivos ~66.5% (preeclampsia, eclampsia, HELLP), hemorrágicos ~14.9%, sepsis obstétrica ~6.1%.

### 1.3 Marco normativo vigente

| Norma | Año | Relevancia |
|---|---|---|
| Decreto 3518 | 2006 | Crea y regula SIVIGILA |
| Ley 1751 (Estatutaria de Salud) | 2015 | Salud como derecho fundamental |
| Ley 1581 (Habeas Data) | 2012 | Protección de datos personales sensibles |
| Resolución 3280 (RIA Materno Perinatal) | 2018 | Rutas integrales, lineamientos CPN y parto |
| Sentencia C-055 Corte Constitucional | 2022 | Despenaliza aborto hasta 24 semanas — cambia perfil post-aborto |
| PAREMM v5 (MinSalud) | 2023+ | Plan Aceleración Reducción Mortalidad Materna |
| SIRENAGEST (MinSalud) | 2023+ | Sistema Registro Nacional de Gestantes (cobertura 67.9% en 2025) |
| Protocolo MME INS (Pro_MME 2024) | 2024 | Protocolo vigente vigilancia MME (evento 549) |
| Protocolo MM INS (Pro_mortalidad_materna 2024) | 2024 | Protocolo MM (eventos 550/551) |

### 1.4 Definiciones clave
- **MME**: complicación severa ocurrida durante embarazo, parto o dentro de los 42 días siguientes, que pone en riesgo la vida de la mujer pero sobrevive, y cumple al menos un criterio de inclusión del protocolo 549.
- **Criterios de inclusión (3 grupos, basta con cumplir 1)**:
  1. Enfermedad específica (preeclampsia severa, eclampsia, hemorragia obstétrica severa, sepsis, ruptura uterina).
  2. Disfunción orgánica (cardiaca, vascular, renal, hepática, respiratoria, cerebral, hematológica/coagulación, metabólica, uterina).
  3. Manejo instaurado (UCI, transfusión ≥3U, histerectomía de emergencia, cirugía mayor).
- **Modelo de las 3 demoras** (Thaddeus & Maine 1994):
  - I — Decisión de buscar atención (reconocimiento, decisión familiar).
  - II — Acceso al servicio (distancia, transporte, barreras culturales).
  - III — Atención adecuada y oportuna en IPS.

---

## 2. Data evaluada (todas las fuentes consultadas)

### 2.1 Fuentes 100% públicas confirmadas — SE USAN

| ID / Fuente | Descripción | Granularidad | Cobertura | Volumen |
|---|---|---|---|---|
| **`4hyg-wa9d`** (datos.gov.co) | SIVIGILA histórico INS | Municipio × semana × año × evento × conteo | **Nacional 2007-2024** | **82.387 filas MME** (evento 549) |
| `qvnt-2igj` | SIVIGILA 2019 | Idem anual | Nacional 2019 | 8.558 MME |
| `xd2n-cu8j` | SIVIGILA 2018 | Idem | Nacional 2018 | — |
| `84d4-vfax` | SIVIGILA 2017 | Idem | Nacional 2017 | — |
| `fhc4-jjti` | DA-SIVIGILA 2021 INS | Idem | Nacional 2021 | — |
| DANE Estadísticas Vitales | Nacimientos + defunciones (CIE-10) | Municipio × año | Histórico | Cientos de miles/año |
| DANE Censo 2018 + proyecciones | Población, etnia, NBI, ruralidad | Municipio | 2018+ | ~1.100 municipios |
| REPS MinSalud | Prestadores de servicios de salud | IPS × municipio × nivel | Vigente | Miles de IPS |
| BDUA Supersalud | Cobertura aseguramiento | Municipio × régimen | Vigente | Millones |
| IDEAM | Clima | Estación × día | Histórico | — |
| Boletines epidemiológicos INS | Series semanales nacionales | Semanal | 52/año | — |

### 2.2 Fuentes regionales individuales — VALIDACIÓN

| ID | Alcance | Uso |
|---|---|---|
| `yvwj-2ibn` | MME Medellín (individual) | Ground truth parcial para C2 |
| `6gyv-zezr` | MME Cali ene-may 2023 (individual) | Ground truth parcial |
| `svi3-eg79` | MME Pereira 2022-2025 (673 filas, pobre) | Validación anecdótica |

### 2.3 Fuentes evaluadas pero DESCARTADAS

| Fuente | Razón del descarte |
|---|---|
| Microdata SIVIGILA ficha 549 cruda (INS) | Requiere solicitud formal + aval institucional |
| SIRENAGEST (MinSalud) | Requiere solicitud |
| CAC Resolución 994/2022 | Requiere solicitud + aval; portal solo publica PDFs tras registro |
| Infocancer | Dataset desapareció del catálogo Socrata |
| Cáncer en datos abiertos | Solo tasas de mortalidad por departamento 1997-2019 (`64it-izw2`, INC); insuficiente para ML serio |

### 2.4 Limitación crítica del dataset principal
El `4hyg-wa9d` solo tiene `cod_eve, nombre_evento, semana, ano, cod_dpto_o, cod_mun_o, departamento_ocurrencia, municipio_ocurrencia, conteo`. **No incluye** edad, etnia, régimen, causa específica, criterios de inclusión, manejo, ni desenlace. Por eso toda inferencia es **municipal, no individual**.

---

## 3. Targets del proyecto

### 3.1 Target principal — C3: Vulnerabilidad Obstétrica Municipal

| Atributo | Especificación |
|---|---|
| Unidad de análisis | Municipio-año (o municipio-semestre) |
| Variable respuesta | Probabilidad de exceso de razón MME/1.000 NV en próximos 12 meses |
| Técnica base | Gradient Boosting (XGBoost/LightGBM) o Poisson/NegBin con offset log(NV) |
| Explicabilidad | SHAP obligatorio por municipio |
| Aporte metodológico | Operacionalización cuantitativa del modelo de 3 demoras (Thaddeus & Maine 1994) con data pública territorial |
| Usuario institucional | MinSalud PAREMM v5, Direcciones Territoriales de Salud |
| Decisión operacional | Asignación de recursos, apertura UCI-O, rutas de referencia, brigadas extramurales |

### 3.2 Target complementario — C1: Outbreak Detection

| Atributo | Especificación |
|---|---|
| Unidad | Municipio × semana epidemiológica |
| Variable respuesta | Alerta binaria + score de severidad |
| Técnica | EARS C1/C2/C3 (CDC), Farrington, Prophet + residuales >2σ, Isolation Forest |
| Usuario | INS Subdirección Vigilancia + Secretarías Departamentales |
| Decisión | Activar unidad de análisis de caso (<30 días según protocolo INS) + supervisión a UPGD |

### 3.3 Target de análisis secundario (limitaciones) — C2: Subregistro
Clasificación multiclase por municipio-año: `{notificador adecuado / subregistrador / sobrerregistrador / silente}`. No se usa como target principal por riesgo de etiquetas circulares, pero da un capítulo fuerte de discusión.

### 3.4 Ventana temporal: **2016-2022** (real, ajustada)
- **Objetivo inicial**: 2016-2024 (por estabilidad de protocolo 549 desde ~2016).
- **Ventana real disponible**: **2016-2022**. El dataset oficial `4hyg-wa9d` (INS) aún no publica años 2023 ni 2024 — verificado por API Socrata el 2026-04-23. El nombre del dataset dice "2007-2024" pero el contenido se corta en 2022.
- **Split temporal ajustado**:
  - Train: 2016-2020 (5 años, ~42.3k filas)
  - Val: 2021 (~11.0k filas)
  - Test: 2022 (~12.1k filas)
- **Regímenes especiales** (features dummy obligatorios):
  - `covid_window`: 2020-2022 (cubre val y test)
  - `post_c055`: ≥2022 (Sentencia C-055/2022) — solo aplica al test set
  - `post_paremm`: ≥2023 (fuera de la ventana disponible, no aplica)
- **Alternativa si se necesitan 2023-2024**: parsear boletines epidemiológicos INS semanales (PDF) o informes de evento MME anuales — trabajo adicional de scraping.

---

## 4. Features previstas (9 grupos)

1. **Histórico epidemiológico municipal**: conteo MME por año/semana, razón MME/1.000 NV, tendencia móvil, estacionalidad (Fourier de semana epidemiológica).
2. **Denominadores (DANE)**: nacidos vivos por municipio × año, fecundidad global, fecundidad adolescente (<19), fecundidad >35, RMM histórica municipal.
3. **Estructura poblacional (DANE proyecciones 2018+)**: población total, % mujeres edad fértil (15-49), estructura etaria.
4. **Determinantes socioeconómicos (Censo 2018)**: NBI, % rural disperso, analfabetismo, % indígena/afro (proxy étnico).
5. **Oferta de servicios (REPS)**: N° IPS por nivel de complejidad, presencia UCI-O, distancia al nivel III.
6. **Cobertura aseguramiento (BDUA)**: % contributivo, % subsidiado, % no afiliado.
7. **Clima (IDEAM)**: temperatura media, precipitación, humedad (modelado sepsis estacional + arbovirosis concurrentes).
8. **Temporal**: semana epidemiológica, año, indicadores de régimen (`covid_window`, `post_c055`, `post_paremm`).
9. **Intensidad de notificación** (anti-sesgo): UPGD activas / NV esperados — controla subregistro diferencial.

---

## 5. Advertencias metodológicas no negociables

1. **Ecological fallacy** — el modelo predice riesgo municipal, nunca individual. Prohibidas frases tipo "mujer indígena tiene X% más riesgo".
2. **Subregistro diferencial** en indígenas/rurales — el modelo hereda el sesgo. Mitigar con feature de intensidad de notificación y análisis de sensibilidad excluyendo municipios con REPS <X%.
3. **MAUP** (Modifiable Areal Unit Problem) — reportar mínimo 2 escalas (municipio + departamento).
4. **Suavizamiento bayesiano empírico** (Clayton-Kaldor o similar) para estabilizar razones en municipios con <50 NV/año.
5. **Split temporal estricto**: train ≤2022, val 2023, test 2024. Nunca random split.
6. **Ventana 2016-2024** para comparabilidad del protocolo 549.
7. **Dummy C-055/2022** obligatorio — cambia perfil de complicaciones post-aborto desde 2022.
8. **PAREMM v5 (2023+)** como régimen post-intervención — sesga series temporales.
9. **Efecto COVID 2020-2022** como outlier o régimen separado.
10. **Etnia no está en el dataset agregado** — solo proxies (NBI + resguardos indígenas DANE). Declararlo en limitaciones.
11. **Heterogeneidad de causas oculta** — no hay hipertensivos vs hemorragia vs sepsis en los agregados. Limitación dura.

---

## 6. Stack y adaptación al nuevo dominio

| Componente actual | Estado | Cambio requerido |
|---|---|---|
| Airflow DAGs bronze→silver→gold | ✅ Reutilizable | Nuevo loader SIVIGILA (Socrata API) |
| DuckDB staging | ✅ Reutilizable | Nuevo schema MME municipal |
| features_lib | 🟡 Adaptable | Features territoriales/temporales agregadas |
| MLflow registry | ✅ Reutilizable | Nuevo experimento `mme_c3_v1` + `mme_c1_v1` |
| FastAPI + ModelPicker | ✅ Reutilizable | Nuevos endpoints `/mme/vulnerability` y `/mme/outbreak` |
| Grafana drift | ✅ Reutilizable | Nuevos mappers StatsD → Prom |

---

## 7. Gap académico verificado

Consultado con el experto MME (2026-04-23): **no hay publicación colombiana conocida** que combine MME + ML predictivo + data pública nacional agregada. Literatura existente es descriptiva (UNFPA Colombia, Rev. Col. Obst. Ginecol., INS población indígena, MinSalud demoras I-II). Gap concreto detectado en 3 frentes:
- Modelo público de vulnerabilidad municipal con ML interpretable.
- Outbreak detection específico para MME (sí existe para dengue/ETV).
- Operacionalización cuantitativa del modelo de 3 demoras con datos territoriales.

> ⚠ Pendiente: búsqueda estructurada en SciELO + BVS + Redalyc con términos "morbilidad materna extrema" AND ("machine learning" OR "aprendizaje automático" OR "modelo predictivo") para confirmar el gap.

---

## 8. Ética y manejo de datos

- **Ley 1581 de 2012 (Habeas Data Colombia)** — aunque la data es agregada municipal (no identifica individuos), igual declarar tratamiento.
- **Resolución 8430 de 1993** — investigación en salud humana.
- **Sesgo de subregistro** herencia documentada en el modelo.
- **Consideración poblacional**: resultados pueden afectar decisiones sobre poblaciones vulnerables → transparencia total sobre limitaciones.

---

## 9. Próximos pasos operativos

### ✅ Completados (2026-04-23)
1. Autorizados hosts en allowlist: `www.datos.gov.co`, `api.us.socrata.com`, INS, DANE, MinSalud, IDEAM.
2. **Bronze ingerido**: `4hyg-wa9d` filtrado a `cod_eve=549`, años 2016-2022.
   - Script: `scripts/mme/ingest_sivigila_bronze.py`
   - Output: `data/mme/bronze/year=YYYY/part-0000.parquet` (particionado Hive, ZSTD)
   - Manifest: `data/mme/bronze/_manifest.json` (trazabilidad + SHA256)
3. **QA bronze ejecutado**: reporte en `reports/mme/bronze_qa_2026-04-23.md`.
   - 65.393 filas, 0 nulos, 0 duplicados, 35 dptos, 1.163 municipios
   - Único evento en data: 549 MORBILIDAD MATERNA EXTREMA ✓
   - 6 gaps año-semana (todos semana 53 — normal, solo años ISO con 53 semanas)

### ✅ Completado en sesión 2026-04-23 (cierre del día)
4. **DIVIPOLA DANE ingerido** → catálogo canónico 1.122 municipios + 33 deptos con lat/lon.
5. **Reconciliación cruzada** bronze ↔ DIVIPOLA → reglas de limpieza documentadas.
6. **Silver `data/mme/silver/mme_clean.parquet`** — 64.562 filas, 175.274 casos, schema canónico con regímenes temporales (covid_window, post_c055).
7. **Gold `data/mme/gold/panel_muni_semestre.parquet`** — 15.708 filas (panel completo), listo para Target C3.
8. **Gold `data/mme/gold/panel_muni_semana.parquet`** — 408.408 filas, listo para Target C1.
9. Manifests y reportes QA generados (`reports/mme/silver_qa_*.md`).

### 🔜 Próxima sesión
10. **Nacidos vivos DANE EEVV** (columnas placeholder ya en gold: `nv_esperados`, `razon_mme_por_1000_nv`):
    - Opción A: descarga manual desde `microdatos.dane.gov.co` (archivos CSV/SPSS por año).
    - Opción B: scraping de cuadros anuales DANE.
    - Opción C: usar **proyecciones DANE de NV por municipio** publicadas en Excel.
11. **DANE Censo 2018 + proyecciones** → NBI, ruralidad, etnia, población MEF → join en gold.
12. **REPS MinSalud** → oferta IPS, UCI-O por municipio.
13. **BDUA Supersalud** → cobertura aseguramiento.
14. **IDEAM clima** (opcional).
15. **Suavizamiento bayesiano empírico** (Clayton-Kaldor) para razones en municipios pequeños.
16. Entrenamiento baseline C3 (Poisson/NegBin) → logging MLflow.
17. Entrenamiento C3 con Gradient Boosting + SHAP.
18. Módulo C1 outbreak detection sobre panel semana.
19. Dashboards Grafana: vulnerabilidad municipal + alertas outbreak.
20. API endpoints `/mme/vulnerability/{municipio}` y `/mme/outbreak/alerts`.

### Hallazgos operativos del bronze
- El dataset `4hyg-wa9d` se corta en **2022** (no 2024 como indica su nombre).
- Códigos de departamento `EXTERIOR` en la data — residencia en el extranjero, tratar en silver.
- Municipios con 1 fila total en toda la ventana sugieren: (a) municipios silentes en notificación, (b) municipios con casos aislados. El feature "intensidad de notificación" debe capturar esto.
- Tendencia ascendente clara: 7.5k (2016) → 12.1k (2022) en N° de filas por año — consistente con reporte INS de tendencia creciente de la razón MME.

---

## 10. Fuentes oficiales (enlaces de referencia)

### Normatividad
- [Res. 3280/2018 RIA Materno Perinatal](https://www.minsalud.gov.co/sites/rid/lists/bibliotecadigital/ride/de/dij/resolucion-3280-de-2018.pdf)
- [PAREMM v5](https://www.minsalud.gov.co/sites/rid/Lists/BibliotecaDigital/RIDE/VS/PP/plan-reduccion-aceleracion-msps.pdf)
- [Protocolo MME 2024 INS](https://www.ins.gov.co/buscador-eventos/Lineamientos/Pro_MME%202024.pdf)
- [Protocolo MM 2024 INS](https://www.ins.gov.co/buscador-eventos/Lineamientos/Pro_mortalidad%20materna%202024.pdf)

### Datasets
- [SIVIGILA histórico 2007-2024 — 4hyg-wa9d](https://www.datos.gov.co/Salud-y-Protecci-n-Social/Datos-de-Vigilancia-en-Salud-P-blica-de-Colombia/4hyg-wa9d)
- [DANE Estadísticas Vitales microdatos](https://microdatos.dane.gov.co/index.php/catalog/807)
- [INS Datos Abiertos](https://www.ins.gov.co/Transparencia/informacion-de-interes/Paginas/Datos-Abiertos.aspx)

### Literatura descriptiva
- [UNFPA Colombia — documento técnico MME](https://colombia.unfpa.org/sites/default/files/pub-pdf/mortalidadmaternaextrema_web.pdf)
- [INS Reporte Epidemiológico — MME reto vigente](https://epidemiologiains.org/index.php/ren/article/view/59)
- [INS Mortalidad materna población indígena 2018-2022](https://epidemiologiains.org/index.php/ren/article/view/150)
- [MinSalud Determinantes MM/MME Demoras I-II](https://www.minsalud.gov.co/sites/rid/Lists/BibliotecaDigital/RIDE/VS/PP/SM-Determ-MM-y-MME-Demoras-I-y-II.pdf)
- [Informe MME 2023 portalsivigila](https://portalsivigila.ins.gov.co/Operacin%20Estadstica/MME%20INFORME%20DE%20EVENTO%202023.pdf)

### API / técnico
- [Socrata SODA API — getting started](https://dev.socrata.com/consumers/getting-started.html)
- [Socrata endpoints](https://dev.socrata.com/docs/endpoints.html)

---

**Mantener actualizado este documento en cada cambio sustancial.**
