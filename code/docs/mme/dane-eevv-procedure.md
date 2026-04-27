# DANE EEVV Nacimientos — Procedimiento de descarga manual

> Última actualización: 2026-04-23
> Bloqueante de Fase MME-A (M-001) — sin esto no hay denominador para `razon_mme_por_1000_nv`.

## Por qué es manual

DANE NO publica una API estable de microdata para Estadísticas Vitales. El único canal abierto es `microdatos.dane.gov.co`, que requiere navegador. Las versiones agregadas en `datos.gov.co` (Socrata) solo cubren municipios o IPS individuales (Bucaramanga, Cartagena, Buga, Acacías…), no Colombia.

## Qué descargar

Una vez por año cubierto. Para esta investigación: **2016 a 2022** (7 archivos).

| Año | Lo que se baja | Tamaño aprox. |
|---|---|---|
| 2016 | "Nacimientos 2016" CSV/Excel | ~150 MB |
| 2017 | "Nacimientos 2017" | ~150 MB |
| 2018 | "Nacimientos 2018" | ~150 MB |
| 2019 | "Nacimientos 2019" | ~150 MB |
| 2020 | "Nacimientos 2020" | ~120 MB (caída COVID) |
| 2021 | "Nacimientos 2021" | ~130 MB |
| 2022 | "Nacimientos 2022" | ~140 MB |

Cada año tiene aproximadamente **600.000 registros individuales** de nacidos vivos.

## Pasos

1. Ir a **https://microdatos.dane.gov.co/index.php/catalog/MICRODATOS**.
2. En el buscador del catálogo, escribir **"Nacimientos"**.
3. Seleccionar la entrada de cada año (la cobertura del catálogo cambia con el tiempo; si un año no aparece, puede estar en "Estadísticas Vitales — Nacimientos y Defunciones").
4. En cada ficha → **"Obtener microdatos"** o **"Datos"**.
5. Aceptar las condiciones de uso (DANE pide registro gratuito o aceptación del aviso de uso académico/estadístico).
6. Descargar el archivo CSV o Excel (preferir CSV por velocidad).
7. **Renombrar** el archivo a `nacimientos_<año>.csv` (p.ej. `nacimientos_2016.csv`). Esto permite que el ingestor detecte el año por nombre.
8. Mover los 7 archivos a `data/mme/staging/dane_eevv/`.

## Columnas que el ingestor sabe leer

El script `scripts/mme/ingest_dane_eevv_bronze.py` reconoce alias case-insensitive y sin acentos. Los nombres habituales DANE están cubiertos:

| Concepto | Aliases reconocidos |
|---|---|
| Año | `ano`, `año`, `anio`, `ano_nac`, `year` |
| Cod. departamento | `coddpto`, `cod_dpto`, `dpnac`, `dp_res`, `cod_dane_dpto` |
| Cod. municipio | `codmun`, `cod_mun`, `codmpio`, `cod_mpio`, `mpres`, `mpnac`, `cod_dane_mpio` |
| Cod. DIVIPOLA completo (si viene en una sola columna) | `codigo_municipio`, `divipola`, `cod_divipola` |
| Edad madre | `edad_madre`, `edadmadre`, `edadm` |
| N° consultas prenatales | `n_consul`, `nconsul`, `n_consultas`, `ncpn` |
| Tipo parto | `tipo_parto`, `tipoparto`, `t_parto` |
| Peso recién nacido (gramos) | `peso`, `peso_gramos`, `peso_nacer` |
| Tiempo gestación (semanas) | `t_ges`, `tges`, `tiempo_gestacion`, `semgest` |
| Área nacimiento | `areanac`, `area_nac`, `area`, `area_residencia` |
| Régimen seguridad social | `seg_social`, `segsocial`, `regimen` |
| Etnia madre | `idpertet`, `etnia`, `etnia_madre`, `pertenencia_etnica` |

Si tu archivo trae nombres diferentes, agrega el alias en `COLUMN_ALIASES` del script y rerun.

## Cómo procesar después de la descarga

```bash
# Dry-run: chequea cuántos archivos detecta y qué columnas reconoce, sin escribir.
uv run python scripts/mme/ingest_dane_eevv_bronze.py --dry-run

# Real: agrega por (cod_mpio, año) y escribe data/mme/bronze/dane/eevv/year=YYYY/part-*.parquet
uv run python scripts/mme/ingest_dane_eevv_bronze.py
```

Después:

```bash
# Reconstruye el gold con razon_mme_por_1000_nv real (en vez de NULL placeholder).
uv run python scripts/mme/build_gold_panel.py
```

## Validación rápida post-ingesta

Esperado tras 2016-2022 ingeridos:

- Total NV ingeridos ≈ 4.4-4.6 millones (suma 7 años).
- Cobertura municipal ≈ 1.080-1.110 municipios/año (pueden faltar municipios sin notificación EEVV ese año).
- Promedio NV/muni/año ≈ 530-580.
- 5 municipios principales (Bogotá, Medellín, Cali, Barranquilla, Cartagena) deberían concentrar ~30-35% de los NV.

## Política de versionado

- Los CSV/Excel originales **NO** se commitean al git (peso, política DANE de uso académico).
- El parquet bronze **SÍ** se commitea (es agregado, derivado, ligero ≤2 MB total).
- El manifest `data/mme/bronze/dane/eevv/_manifest.json` registra `input_sha256` por archivo para trazabilidad.
- Si DANE re-publica un año con corrección, basta con reemplazar el CSV en staging y rerun — el SHA cambia y queda registrado.

## Probar el pipeline antes de tener data real

`scripts/mme/ingest_dane_eevv_bronze.py` viene con dry-run. Para probar end-to-end con data sintética mínima, generar un CSV con esta cabecera y unas decenas de filas:

```csv
ano,cod_dpto,cod_mpio,edad_madre,n_consul,tipo_parto,peso,t_ges,areanac,seg_social,idpertet
2016,11,1,28,5,1,3200,40,1,1,6
2016,11,1,16,2,2,2300,36,3,2,1
...
```

Salvalo como `data/mme/staging/dane_eevv/sintetico_2016.csv` y corré el ingestor. **No commitees** el CSV sintético.
