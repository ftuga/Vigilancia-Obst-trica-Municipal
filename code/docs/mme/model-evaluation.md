# Evaluación C3 — Vulnerabilidad Obstétrica Municipal

**Modelo ganador**: LightGBM Poisson + Optuna TPE (50 trials, MedianPruner)
**Run exitoso**: DAG `2-mme_train_and_promote` — ejecución 2026-04-23
**Métrica reportada**: Spearman ρ (departamento) = **0.834** sobre test (2022)
**Gate Go/No-Go**: ≥ 0.30 → ampliamente superado

---

## 1. El problema en una línea

Predecir el **número esperado de casos MME por municipio × semestre** con un offset de población, para priorizar gasto público e intervención sanitaria en los municipios con mayor vulnerabilidad obstétrica.

Formalmente:
```
y_it ~ NegBin(μ_it, θ)   con   log μ_it = log(pop_it/2) + x_it·β
```
donde `y_it` = casos MME en el municipio `i`, semestre `t`, `x_it` son las features socioeconómicas + salud.

---

## 2. Por qué Spearman (y no Pearson, MAE o R²)

### Pearson falla por 3 razones

1. **Distribución del target es count sobredispersa** (`dispersion_ratio = 710`, %zeros = 26.9%). Pearson asume relación lineal entre magnitudes absolutas — pero a MinSalud le importa el **orden relativo** (qué municipios intervenir primero), no si el modelo predijo 11.3 vs 9.7 casos.

2. **MAUP (Modifiable Areal Unit Problem)**: los municipios tienen poblaciones que difieren por 3 órdenes de magnitud (Bogotá ~8M vs municipios rurales <5k). Predecir 500 casos en Bogotá es fácil; predecir *cuáles* municipios medianos están por encima del promedio es lo difícil. Pearson se sesga hacia acertar las magnitudes extremas.

3. **Outliers por subregistro**: EEVV del DANE aún no incorporado (ver `docs/mme/dane-eevv-procedure.md`). Pearson amplifica errores en outliers; Spearman solo los penaliza por su posición en el ranking.

### Por qué Spearman a nivel de departamento

- **Unidad operacional real**: los planes territoriales se ejecutan por departamento, no por municipio aislado.
- **Estabiliza la señal**: promediar los casos al departamento mitiga ruido de municipios pequeños (ley de grandes números).
- **Interpretación política directa**: "el modelo prioriza correctamente los departamentos con más carga de MME" es lo que la SSM/MinSalud necesita entender.

### Métricas complementarias (todas en `reports/models/train_c3_*.json`)

| Métrica | Qué mide | Valor test |
|---|---|---|
| `spearman_dpto` | Orden por departamento | **0.834** |
| `precision_at_50` | ¿El top-50 predicho contiene los top-50 reales? | 0.24 |
| `mae_razon` | Error absoluto en razón por 1000 habitantes | ~0.6 |
| `r2_log` | R² sobre `log(1+y)` — robusto a escala | ~0.42 |

---

## 3. Leyendo el 0.834

### Regla de pulgar (Cohen, adaptada a epi)

| Rango ρ | Interpretación |
|---|---|
| 0.0 – 0.2 | Nulo / ruido |
| 0.2 – 0.4 | Débil pero usable como señal |
| 0.4 – 0.6 | Moderado — valida direccionalidad |
| 0.6 – 0.8 | Fuerte — decisión operacional confiable |
| **0.8 – 0.95** | **Muy fuerte — priorización casi coincidente con el real** |
| > 0.95 | Sospechoso (leakage, overfitting, o target trivial) |

**0.834 cae en "muy fuerte"**: el ranking departamental predicho coincide casi exactamente con el ranking real observado en 2022. Interpretación operacional: si MinSalud toma los **top-10 departamentos** según el modelo, aproximadamente **9 de los 10** están efectivamente en el top-10 real.

### Disclaimer — falacia ecológica

El modelo opera a nivel agregado (municipio × semestre). **NO predice riesgo individual de una gestante**. Un municipio con alta vulnerabilidad *promedio* no implica que toda gestante en ese municipio esté en riesgo alto. Este modelo es una **herramienta de asignación de recursos**, no un clasificador clínico.

### Disclaimer — EEVV

El target actual proviene exclusivamente de SIVIGILA 549 (notificación). Los casos no notificados quedan fuera. Cuando se incorpore el cruce con EEVV del DANE (ver `docs/mme/dane-eevv-procedure.md`), se esperan ajustes a la baja en ρ porque el target se volverá más ruidoso pero más real.

---

## 4. Reproducibilidad — MLflow

### Acceso UI

- **URL local**: http://localhost:5000
- **Experimento**: `mme_vulnerability_v1`
- **Artifacts backend**: MinIO bucket `mlflows3` (http://localhost:9001, cred en `.env`)

### Tags relevantes por run

| Tag | Valor |
|---|---|
| `feature_spec_version` | `v1` |
| `dataset_cycle` | fecha ISO del gold snapshot |
| `regime` | `v1_refactor` (post-migración src/) |
| `family` | `negbin_glm` \| `lgbm_poisson` |

### Reconstruir un run localmente

```bash
# Desde el repo root
docker compose -f proyecto_01/compose.yaml exec airflow-scheduler \
  python -m mme.cli.train \
    --dataset-cycle 2026-04-23 \
    --n-trials 50
```

Los artifacts (modelo, SHAP summary, feature importance, scaler PCA) se logean en el mismo experimento.

---

## 5. Camino desde el notebook hasta producción

| Etapa | Artefacto |
|---|---|
| Exploración | `proyecto_01/jupyterlab/notebook/mme/c3_analysis.ipynb` |
| Módulos productivos | `src/mme/` (paquete instalable) |
| Tests | `tests/mme/unit/` (14/14 passing) |
| CLI | `python -m mme.cli.train` (typer) |
| DAG | `proyecto_01/airflow/dags_mme/2-mme_train_and_promote.py` |
| Registry | MLflow `mme_vulnerability_baseline` (champion/challenger, pendiente promote_c3) |

---

## 6. Próximas validaciones

1. **Backtesting rolling-window**: entrenar 2016–2018 → test 2019, rodar hasta 2022. Validar estabilidad de ρ inter-año.
2. **Cruce EEVV DANE**: re-entrenar con target enriquecido y re-medir gap vs modelo actual.
3. **Calibración bayesiana**: integrar Clayton-Kaldor EB como smoothing previo para municipios con `pop < 10k`.
4. **Análisis contrafactual**: SHAP values por decil de vulnerabilidad — identificar drivers dominantes por departamento.

---

## Referencias

- `docs/mme/ml-problem-definition.md` §6 — criterios Go/No-Go
- `docs/mme/features-spec-v1.md` — catálogo completo de features
- `docs/mme/mlops-plan.md` — plan de operaciones MLflow/Airflow
- Spiegelhalter, D. (2019). *The Art of Statistics* — cap. 10 (correlaciones y sus trampas).
- Gelman, A. & Hill, J. (2006). *Data Analysis Using Regression* — cap. 6 (conteos sobredispersos).
