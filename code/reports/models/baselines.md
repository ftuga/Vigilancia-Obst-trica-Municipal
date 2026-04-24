# R-021 · Baselines · Rugpull detection

- feature_spec_version: `v1`
- dataset_version: `701c28cabde76e23`
- split: últimos 5 meses como test
- mlflow: `file:///home/lfrontuso/documentos/proyectos_tecnologicos/tesis_gabriel/ent_tesis/mlruns` · experiment: `rugpull_baselines_v1`

## Binary (is_rugpull)

| familia | accuracy | f1_macro | f1_positive | roc_auc |
|---|---:|---:|---:|---:|
| logreg | 0.867 | 0.867 | 0.866 | 0.935 |
| random_forest | 1.000 | 1.000 | 1.000 | 1.000 |
| xgboost | 1.000 | 1.000 | 1.000 | 1.000 |
| lightgbm | 1.000 | 1.000 | 1.000 | 1.000 |

## Multiclass (estrato ∈ {bajo, medio, alto})

| familia | accuracy | f1_macro | roc_auc_ovr | f1_bajo | f1_medio | f1_alto |
|---|---:|---:|---:|---:|---:|---:|
| logreg | 0.733 | 0.713 | 0.902 | 0.835 | 0.632 | 0.671 |
| random_forest | 0.995 | 0.993 | 1.000 | 1.000 | 0.990 | 0.988 |
| xgboost | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| lightgbm | 0.997 | 0.996 | 1.000 | 1.000 | 0.995 | 0.994 |

## Ventana de test

Últimos 5 meses del corpus.

## Sanity checks

- No hay fuga: `estrato` y `is_rugpull` NO están en `FEATURE_COLUMNS`.
- Correlación |ρ| máx individual con label: `concentration_gini`=0.58, `concentration_top3`=0.43.
- Los 1.000 en tree models vienen de interacciones: `bajo` = pools muertos <1d con concentración extrema y burn terminal; `alto` = pools activos 100+d y concentración distribuida. Separabilidad real en este corpus.
- LogReg 0.867 en binary y 0.733 en multiclass evidencia que la frontera no es lineal.
- **Feature constante detectada:** `first_event_mint_flag` = 0 en los 998. Candidato a remover o revisar generación en v2.
- **Pendiente robustecer:** forward-walking CV batch-a-batch (R-023 drift) + hold-out de un mes completo nunca visto.
