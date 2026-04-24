# EDA 03 — Validación de `estrato` vs señales on-chain

- Muestra: 998 pools

## Agregación por estrato

| estrato | n | active_days_median | active_days_p90 | lifespan_blocks_median | sync_median | mint_median | burn_median | burn_ratio_median | terminal_burn_pct | transfers_median | concentration_top3_median | unique_senders_median |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| alto | 249 | 101.979 | 355.545 | 659939.0 | 558.0 | 4.0 | 3.0 | 0.5 | 28.98 | 876.0 | 0.438 | 160.5 |
| bajo | 504 | 0.118 | 8.629 | 778.0 | 12.0 | 1.0 | 1.0 | 0.5 | 85.828 | 17.0 | 0.5 | 6.0 |
| medio | 245 | 0.871 | 136.818 | 5641.0 | 41.0 | 1.0 | 1.0 | 0.5 | 67.769 | 61.0 | 0.312 | 10.0 |

## Lectura guiada

Señales que deberían separar estratos si `estrato` proxea riesgo de rug:

- **active_days** ↓ en `alto` → pools de vida corta (rug temprano)
- **terminal_burn_pct** ↑ en `alto` → último evento = BURN (drain de LP)
- **burn_ratio** ↑ en `alto` → más burns que mints (retiro masivo)
- **concentration_top3** ↑ en `alto` → pocos wallets controlan la salida
- **unique_senders** ↓ en `alto` → poca distribución orgánica

## Mapeo sugerido a binario

🎯 **Resultado invertido:** `estrato='bajo'` muestra MÁS terminal_burn que `alto`.

- bajo: terminal_burn=85.828%, active_days_median=0.118
- alto: terminal_burn=28.98%, active_days_median=101.979

Interpretación: **`estrato` proxea legitimidad/actividad, no riesgo**.
- `alto` = pools legítimos (mucha actividad, vida larga)
- `bajo` = pools rug pull (vida corta, drain inmediato)

**Mapeo binario propuesto:** `is_rugpull = (estrato == 'bajo')`

Alternativas:
- Conservador: `is_rugpull = (estrato == 'bajo')` → 504 pos / 998 (50.5%)
- Amplio: `is_rugpull = (estrato IN ('bajo','medio'))` → 749 pos / 998 (75%)

## Muestras para validación manual (10 por estrato, orden aleatorio)

### estrato=alto

| pair_address | active_days | sync_count | mint_count | burn_count | terminal_burn_flag | concentration_top3 |
|---|---|---|---|---|---|---|
| 0xb4f1165b5e1bd0944faf28e71480c18a753b5d99 | 5.967 | 405 | 1 | 1 | 1.0 | 0.579 |
| 0x49aa60661199aeaf8b6f5abd51151f918875c3cd | 50.772 | 720 | 6 | 3 | 0.0 | 0.102 |
| 0x18f238a96392a8fabb87065b5129dd00192e6cb1 | 357.579 | 34829 | 1333 | 927 | 1.0 | 0.426 |
| 0xc37c8bb43a335f567b3fec6241d2b206b582e2e0 | 8.065 | 777 | 1 | 1 | 1.0 | 0.283 |
| 0xb2b50df8f1ef5a9b1e5dd4c9dc3966b41314e2a4 | 67.396 | 128 | 10 | 3 | 0.0 | 0.534 |
| 0xe8573ace1f7fc33068153f96e01b620928741d80 | 38.39 | 423 | 1 | 1 | 0.0 | 0.602 |
| 0x946550e8b2bfba6b9731535bea9aa461b9e4a8f2 | 15.385 | 108 | 1 | 1 | 1.0 | 0.624 |
| 0xa6f3ef841d371a82ca757fad08efc0dee2f1f5e2 | 477.028 | 74235 | 400 | 288 | 0.0 | 0.915 |
| 0x9314941c11d6dee1d7bf93113eb74d4718949f3b | 150.061 | 164202 | 251 | 161 | 0.0 | 0.288 |
| 0x3d98317700c84662325f07dd96b6dd6eccb52608 | 409.703 | 102 | 5 | 1 | 0.0 | 0.466 |

### estrato=medio

| pair_address | active_days | sync_count | mint_count | burn_count | terminal_burn_flag | concentration_top3 |
|---|---|---|---|---|---|---|
| 0x0baedd006630ef5a4d04bcafd0debed663def952 | 2.028 | 34 | 1 | 1 | 0.0 | 0.194 |
| 0xe961ebfe3cb4545725ede074694d304ecac51033 | 0.02 | 32 | 1 | 1 | 1.0 | 0.541 |
| 0x99a5523d14eb63be4030d391ebf0ebe14d6c3c92 | 0.069 | 41 | 1 | 1 | 1.0 | 0.261 |
| 0xce15e1edbfb012551b3344e7affe559e44a07715 | 136.738 | 34 | 9 | 8 | 1.0 | 0.557 |
| 0xe4a6a2e7503917127385875fd873c528fc07bbcd | 136.827 | 30 | 1 | 0 | 0.0 | 0.417 |
| 0x63ff582264aa89a1f870564985c0c871979a898e | 293.928 | 32 | 2 | 1 | 0.0 | 0.207 |
| 0xb07e3bfb03a2ef9983ac56e3f4c8ba2a22278640 | 0.174 | 41 | 1 | 1 | 1.0 | 0.233 |
| 0x0e99d1e99a3bceeceb78968d42d482dcd672785e | 1.154 | 32 | 1 | 1 | 1.0 | 0.128 |
| 0x2d22ebfc1728550fc10fa321f9c6502336fae964 | 0.108 | 38 | 3 | 1 | 1.0 | 0.789 |
| 0xd88515dd079ed7f074feb4111cbf6895a354cd9b | 0.01 | 42 | 1 | 1 | 0.0 | 0.364 |

### estrato=bajo

| pair_address | active_days | sync_count | mint_count | burn_count | terminal_burn_flag | concentration_top3 |
|---|---|---|---|---|---|---|
| 0xc9e7687d34745e9df2a2669c9f1d7081080a79b8 | 0.12 | 18 | 1 | 1 | 1.0 | 0.292 |
| 0x4dc11c7a594b90a4253d65ba13594512cb9c59fd | 0.061 | 25 | 1 | 1 | 1.0 | 0.5 |
| 0x6cf479d70b919623614f1ffd2000a82fa60ebb94 | 0.985 | 7 | 1 | 1 | 1.0 | 0.6 |
| 0x95ca25e79d2357f14121d33e5c462b7de6f81038 | 1.004 | 24 | 1 | 1 | 1.0 | 0.154 |
| 0x07ffb375b722029417b3ac47e7bb12171ec3c951 | 0.621 | 6 | 1 | 1 | 1.0 | 0.7 |
| 0x46b7f238e06b9f7a6e886564ab249ab6252d6b3c | 4.899 | 12 | 2 | 2 | 0.0 | 0.611 |
| 0x97d0408d3357bd0874664e5a6425abc4bf62cc28 | 0.222 | 10 | 1 | 1 | 1.0 | 0.615 |
| 0x4c7c1e2b5d05243442a221f60b577c5940959b72 | 0.448 | 12 | 1 | 1 | 1.0 | 0.429 |
| 0x1945d8d529cf4ce64f7098164c33c9e9ec99c218 | 0.259 | 25 | 1 | 1 | 1.0 | 0.259 |
| 0xa9251a56c4ac9b43abd45ab3be8a38810c63f475 | 0.543 | 7 | 1 | 1 | 1.0 | 0.556 |
