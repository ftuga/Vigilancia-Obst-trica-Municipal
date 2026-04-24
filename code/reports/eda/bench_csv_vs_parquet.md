# R-005 · Benchmark CSV vs Parquet

Query window: bloques 11.5M–11.7M (~1 mes ~= 200K bloques).
Threads=4 · DuckDB in-memory · repeats=2 · Parquet snappy.

## Tamaños

| Archivo | CSV (MB) | Parquet (MB) | Ratio |
|---|---:|---:|---:|
| events | 511.5 | 189.9 | 37.1% |
| transfers | 2052.1 | 691.6 | 33.7% |

## Tiempos (segundos, promedio)

| Query | CSV | Parquet | Speedup |
|---|---:|---:|---:|
| Q1 block_range events | 0.33 | 0.01 | 25.8× |
| Q2 events por ventana | 0.33 | 0.00 | 79.7× |
| Q3 transfers por ventana | 1.01 | 0.02 | 48.8× |

## Decisión sugerida

✅ **Migrar** — speedup promedio 51.4×. Justifica el cambio de pipeline.