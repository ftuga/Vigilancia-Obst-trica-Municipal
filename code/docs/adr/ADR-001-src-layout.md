# ADR-001 — src/ layout + paquete instalable

**Fecha**: 2026-04-23
**Estado**: Aceptado

## Contexto

Los scripts iniciales de MME vivían en `scripts/mme/` como archivos planos sin estructura de paquete. `train_c3_v1.py` creció a 640 líneas con imports dentro de funciones, duplicación de lógica, mixing de concerns (data loading + training + MLflow + SHAP + reporting), y sin tests unitarios. El usuario señaló explícitamente estos antipatrones como "vibe code / spaghetti code" que no escala.

## Decisión

Migrar a **`src/` layout con paquete instalable** (`pip install -e .`):

```
src/mme/               # paquete (módulos reutilizables + testeables)
├── paths.py
├── config.py           # pydantic BaseSettings
├── data/
├── features/
├── models/             # 1 familia = 1 archivo
├── eval/
├── tracking/
├── orchestration/      # pipelines thin
└── cli/                # typer CLIs thin

scripts/mme/            # scripts legacy, en migración (NO agregar código nuevo)
tests/mme/unit/         # tests por módulo
tests/mme/integration/  # E2E con stack
pyproject.toml          # [project.scripts] entry points + ruff + mypy + pytest
```

## Alternativas consideradas

1. **Flat layout** (`mme/` en root sin `src/`). Más simple pero mezcla paquete con configs/docs y típicamente causa confusión sobre qué se instala.
2. **Monorepo con múltiples paquetes** (`src/mme_data/`, `src/mme_ml/`). Overkill para este tamaño.
3. **Mantener scripts/ sin refactor**. Descartado — usuario vetó.

## Consecuencias

**Positivas**:
- Imports limpios: `from mme.data.panel import load_panel` en cualquier script/DAG/test.
- Tests unitarios reales (sin `sys.path` hacks).
- CLIs autogenerados via `[project.scripts]` + typer (tipados, help automático).
- `mypy --strict` aplicable al código productivo (`src/`).
- Coverage gate 75% accionable.

**Negativas**:
- Scripts legacy en `scripts/mme/` duplican lógica temporalmente hasta migrar.
- Los DAGs deben actualizar para llamar CLI entry points (`mme-train-c3` en lugar de `python scripts/mme/train_c3_v1.py`).

## Migración

- Fase 1 (completa 2026-04-23): estructura + core modules (data, features, eval, models básicos) + tests unitarios 14/14 ✓.
- Fase 2 (pendiente): XGBoost + tracking/mlflow_ops + actualizar DAG 2 a entry points.
- Fase 3 (pendiente): migrar scripts de ingesta al paquete.
- Fase 4 (pendiente): deprecar `scripts/mme/*_v1.py` legacy.

## Referencias

- Helix skill: `~/.claude/skills/python-production/SKILL.md`
- `docs/mme/coding-standards.md`
- "Architecture Patterns with Python" (cosmicpython.com) — ch. 1-3 packaging
- PEP 621 packaging metadata
