# Vigilancia Obstétrica Municipal

Modelo de vulnerabilidad obstétrica municipal para Colombia. Predice el número esperado de casos de Morbilidad Materna Extrema (MME, evento SIVIGILA 549) por municipio × semestre, con un offset poblacional, para priorización de inversión territorial en salud materna.

Trabajo investigativo basado exclusivamente en datos públicos (SIVIGILA, DANE, MinSalud REPS, BDUA Supersalud).

---

## Resultado principal

Spearman departamental sobre test 2022 = **0.836** (gate Go/No-Go ≥ 0.30).
Backtest rolling 4 ventanas (2019-2022): cv_spearman = 0.073 (≤ 0.15, modelo estable temporalmente).

Detalle: [`code/docs/mme/results.md`](code/docs/mme/results.md).

---

## Estructura del repo

```
Vigilancia-Obst-trica-Municipal/
├── code/                  Paquete MME, APIs, frontend, DAGs
│   ├── src/mme/          Paquete instalable (data, models, eval, drift, tracking)
│   ├── api_predict_mme/  FastAPI con bootstrap CI residual
│   ├── frontend_mme/     Next.js 14 + Tailwind + Recharts
│   ├── proyecto_01/      Airflow + MLflow + MinIO + observabilidad
│   ├── scripts/mme/      Ingesta bronze + builders silver/gold + backtest
│   ├── tests/            pytest suites
│   └── docs/mme/         Documentación académica
├── docs/                  Arquitectura del sistema, runbook, ADRs
├── k8s/                   Manifests Helm + ArgoCD (REQ-003)
└── .github/workflows/     CI/CD a Docker Hub
```

---

## Documentación

| Documento | Contenido |
|---|---|
| [`code/docs/mme/methodology.md`](code/docs/mme/methodology.md) | Decisiones metodológicas del modelo C3 |
| [`code/docs/mme/results.md`](code/docs/mme/results.md) | Resultados experimentales |
| [`code/docs/mme/limitations.md`](code/docs/mme/limitations.md) | Limitaciones conocidas |
| [`code/docs/mme/runbook.md`](code/docs/mme/runbook.md) | Despliegue local del stack en MicroK8s |
| [`code/docs/mme/features-spec-v1.md`](code/docs/mme/features-spec-v1.md) | Catálogo de 14 features finales |
| [`code/docs/mme/ml-problem-definition.md`](code/docs/mme/ml-problem-definition.md) | Formulación del problema y gates |
| [`docs/architecture.md`](docs/architecture.md) | Arquitectura del sistema completo |

---

## Stack

- **Modelado**: LightGBM Poisson + Optuna TPE · GLM NegBin baseline
- **Tracking**: MLflow 3.x con aliases `@champion`
- **Orquestación**: Airflow 2.x CeleryExecutor
- **Serving**: FastAPI + bootstrap CI residual + Prometheus metrics
- **Frontend**: Next.js 14 App Router + shadcn handmade + Recharts
- **Observabilidad**: kube-prometheus-stack + Loki + Tempo
- **GitOps**: ArgoCD App-of-Apps + GitHub Actions a Docker Hub `luisfrontuso10/mme-*`
- **Cluster**: MicroK8s (single-node, parametrizado para multi-host vía `.env`)

---

## Despliegue

```bash
git clone git@github.com:ftuga/Vigilancia-Obst-trica-Municipal.git
cd Vigilancia-Obst-trica-Municipal
# Seguir code/docs/mme/runbook.md
```

Setup completo: ver [`code/docs/mme/runbook.md`](code/docs/mme/runbook.md).

---

## Contexto

- Pivot a foco MME 2026-04-23. Proyecto previo de detección de rug pulls DeFi queda archivado en [`ent_tesis`](https://github.com/ftuga/ent_tesis) (privado).
- Marco normativo: Resolución 3280/2018 MinSalud (Ruta Materno Perinatal), Política PAREMM, SIRENAGEST.
- Criterios clínicos OMS/FLASOG de inclusión MME (enfermedad específica, disfunción orgánica, manejo).

---

## Licencia

MIT.
