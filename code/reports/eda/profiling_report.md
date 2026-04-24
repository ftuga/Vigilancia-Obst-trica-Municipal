# EDA 01 — Profiling Report

- Fecha: auto
- Duración: 11.1 s
- Data dir: `/home/lfrontuso/documentos/proyectos_tecnologicos/tesis_gabriel/ent_tesis/api_datos/data`

## Datasets

| Dataset | Rows | Size MB | Columns | SHA256 (8) |
|---|---:|---:|---:|---|
| pools | 998 | 0.4 | 16 | `9bdf3791…` |
| metadata | 998 | 0.2 | 5 | `3f186c20…` |
| events | 1,835,994 | 511.5 | 10 | `a007d574…` |
| transfers | 8,717,043 | 2052.1 | 8 | `6c9d16c9…` |

## Target — columna detectada: `estrato`

- `estrato=bajo` → 504 (50.5%)
- `estrato=alto` → 249 (24.95%)
- `estrato=medio` → 245 (24.55%)

## Events — tipos

- `sync` → 1,755,374
- `mint` → 51,078
- `burn` → 29,542

**Rango de bloques (events):** 10,091,132 → 13,220,488 · 988 pairs únicos

## Transfers

- Total: 8,717,043 filas
- Bloques: 10,002,875 → 13,220,488
- Tokens únicos: 988

## Metadata — decimals top

- `decimals=18` → 1954
- `decimals=8` → 13
- `decimals=0` → 8
- `decimals=9` → 6
- `decimals=2` → 4
- `decimals=4` → 3
- `decimals=6` → 2
- `decimals=10` → 1
- `decimals=11` → 1
- `decimals=15` → 1

## Integridad referencial

- Pools sin metadata de token: **0**
- Pairs en events no presentes en pool_list: **0**

## Null / Cardinalidad por dataset

### pools

| col | null% | distinct | card% |
|---|---:|---:|---:|
| `pair_address` | 0.0 | 998 | 100.0 |
| `token0` | 0.0 | 746 | 74.75 |
| `token1` | 0.0 | 254 | 25.45 |
| `creation_time` | 0.0 | 998 | 100.0 |
| `block_number` | 0.0 | 998 | 100.0 |
| `transaction_hash` | 0.0 | 998 | 100.0 |
| `token0_decimals` | 0.0 | 13 | 1.3 |
| `token1_decimals` | 0.0 | 6 | 0.6 |
| `sync_count` | 0.0 | 313 | 31.36 |
| `transfer_count` | 0.0 | 103 | 10.32 |
| `burn_count` | 0.0 | 65 | 6.51 |
| `mint_count` | 0.0 | 80 | 8.02 |
| `pair` | 0.0 | 998 | 100.0 |
| `estrato` | 0.0 | 3 | 0.3 |
| `token_address` | 0.0 | 998 | 100.0 |
| `pool_creator` | 0.0 | 959 | 96.09 |

### metadata

| col | null% | distinct | card% |
|---|---:|---:|---:|
| `token_address` | 0.0 | 998 | 100.0 |
| `token_creator` | 0.0 | 959 | 96.09 |
| `token_creation_tx` | 0.0 | 998 | 100.0 |
| `token_creation_block` | 0.0 | 998 | 100.0 |
| `token_creation_timestamp` | 0.0 | 998 | 100.0 |

### events

| col | null% | distinct | card% |
|---|---:|---:|---:|
| `event_type` | 0.0 | 3 | 0.0 |
| `pair_address` | 0.0 | 988 | 0.05 |
| `sender` | 95.61 | 34 | 0.0 |
| `to_address` | 98.39 | 616 | 0.03 |
| `amount0_or_reserve0_hex` | 0.0 | 1,785,988 | 97.28 |
| `amount1_or_reserve1_hex` | 0.0 | 1,815,786 | 98.9 |
| `block_timestamp` | 0.0 | 1,102,301 | 60.04 |
| `block_number` | 0.0 | 1,102,301 | 60.04 |
| `transaction_hash` | 0.0 | 1,717,129 | 93.53 |
| `log_index` | 0.0 | 979 | 0.05 |

### transfers

_skipped (2GB)_
