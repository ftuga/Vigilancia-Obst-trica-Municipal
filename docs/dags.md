# DAGs y data lineage

Tres DAGs Airflow orquestan el ciclo completo: reset (manual), ETL medallón (diario), training+promote (diario).

## DAG 0 — `0-mme_reset_environment`

Manual-only. Limpieza idempotente para probar boot from scratch.

```mermaid
graph LR
    Gate{confirm_reset<br/>= YES?}
    Gate -->|sí| PVC[reset_pvc<br/>borrar bronze/silver/gold]
    Gate -->|sí| MN[reset_minio<br/>vaciar buckets mme-*]
    Gate -->|sí| MLF[reset_mlflow_registry<br/>borrar champion + versions]
    PVC --> Sum[summary]
    MN --> Sum
    MLF --> Sum
    Gate -->|no| Skip((skip))
```

**Gate**: requiere Airflow Variable `confirm_reset=YES` para evitar disparos accidentales.

## DAG 1 — `1-mme_etl_medallion`

Diario 02:00 UTC. Ingesta multi-fuente paralela → silver → gold panel municipal-semestre.

```mermaid
graph TB
    subgraph "Bronze · APIs públicas"
        SVMM[fetch_sivigila_mm<br/>evento 550]
        SVME[fetch_sivigila_mme<br/>evento 549]
        DIV[fetch_divipola]
        NBI[ingest_nbi<br/>Censo 2018]
        POB[ingest_poblacion<br/>Proyecciones DANE]
        BDUA[ingest_bdua<br/>Régimen seguridad]
        REPS[ingest_reps<br/>Capacidad obstétrica]
        EEVV[eevv_staging_check<br/>opcional]
    end

    DIV --> REPS

    subgraph "Silver · reglas"
        SLV[build_silver<br/>recon DIVIPOLA + filtros 549]
    end

    SVME --> SLV
    DIV --> SLV

    subgraph "Gold · panel modelado"
        GLD[build_gold_panel<br/>15.708 filas muni-semestre]
        VAL[validate_gold_invariants<br/>asserts cobertura]
    end

    SLV --> GLD
    SVMM --> GLD
    NBI --> GLD
    POB --> GLD
    BDUA --> GLD
    REPS --> GLD
    EEVV --> GLD
    GLD --> VAL

    subgraph "Distribución"
        SYNC[sync_minio<br/>mirror PVC → S3]
    end
    VAL --> SYNC
```

**Salida**: `panel_muni_semestre.parquet` en PVC `mme-data` y MinIO bucket `mme-gold`.

## DAG 2 — `2-mme_train_and_promote`

Diario 04:00 UTC (2 h después de DAG 1). Pipeline de modelado completo.

```mermaid
graph LR
    CD[check_drift<br/>Evidently + PSI/KS]
    GT{gate_train<br/>drift OR no champion}
    FS[feature_selection<br/>PCA + LASSO + MI]
    TR[train_c3<br/>NegBin GLM + LightGBM Optuna]
    VR[validate_report<br/>gates Go/No-Go]
    PR[promote_c3<br/>alias champion en Registry]

    CD --> GT
    GT -->|sí| FS
    GT -->|no| Skip((skip))
    FS --> TR
    TR --> VR
    VR --> PR
```

**Gates Go/No-Go en `validate_report`**:

| Métrica | Umbral |
|---|---|
| `test_spearman_dpto` | ≥ 0.30 |
| `test_precision_at_50` | ≥ 0.08 |
| `r2_log_counts` | > 0 |
| `overfit_gap` (val→test) | ≤ 0.20 |
| `mae_razon` | finito |

**Promoción** vía `mme.tracking.mlflow_ops.promote_champion()`: gate combinado `new ≥ prev × tolerance OR new ≥ absolute_floor`. Tolerance default 0.95, floor 0.65.

## Lineage de datos

```mermaid
flowchart LR
    subgraph "Fuentes externas"
        SVG[datos.gov.co<br/>SIVIGILA]
        DANE[dane.gov.co<br/>Censo + Proyecciones]
        DIVI[INS<br/>DIVIPOLA]
    end

    subgraph "Bronze · raw parquet"
        BRZ[mme-bronze/<br/>year=*/part-*.parquet]
    end

    subgraph "Silver · clean"
        SLV[mme-silver/<br/>mme_clean.parquet]
    end

    subgraph "Gold · panel modelado"
        GLD[mme-gold/<br/>panel_muni_semestre.parquet]
    end

    subgraph "Modelo"
        FS[feature_set_v1.json]
        MOD[mme_vulnerability_baseline<br/>@champion · MLflow]
    end

    subgraph "Serving"
        API[/predict?cod_mpio=05001/]
    end

    SVG --> BRZ
    DANE --> BRZ
    DIVI --> BRZ
    BRZ --> SLV
    SLV --> GLD
    GLD --> FS
    FS --> MOD
    MOD --> API
    GLD --> API
```
