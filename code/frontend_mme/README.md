# frontend_mme

Next.js 14 (App Router) que sirve el dashboard MME consumiendo `api_predict_mme`.

## Layout

```
frontend_mme/
├── app/
│   ├── layout.tsx          # header + footer con tokens
│   ├── page.tsx            # Home: resumen + link a /mme y /health
│   ├── api-actions.ts      # server actions (URL API server-only)
│   ├── mme/
│   │   ├── page.tsx        # Mapa + ranking + disclaimer falacia ecológica
│   │   └── disclaimer.tsx
│   └── health/page.tsx     # /healthz y /readyz del backend
├── components/
│   ├── ui/{card,badge,table}.tsx   # shadcn handmade
│   ├── MapaColombia.tsx            # react-simple-maps coroplético
│   ├── RankingTable.tsx
│   └── ModelInfoCard.tsx
├── public/geo/colombia-departamentos.geojson
├── scripts/
│   ├── fetch-geojson.sh             # baja oficial o cae al placeholder
│   └── generate_placeholder_geojson.py  # genera 33 círculos por depto
└── Dockerfile (multi-stage standalone, non-root, :3001)
```

## GeoJSON

El archivo `public/geo/colombia-departamentos.geojson` es un **placeholder**
(33 círculos aproximados). Para producción usar uno oficial de IGAC/DANE con
la property `DPTO_CCDGO` (2 dígitos DIVIPOLA).

Para regenerar el placeholder:

```bash
bash scripts/fetch-geojson.sh
```

O para usar uno oficial:

```bash
GEOJSON_URL="https://…/colombia-departamentos.geojson" bash scripts/fetch-geojson.sh
```

## Desarrollo local

```bash
npm install
export API_PREDICT_MME_URL=http://<NODE_IP>:30601    # API en el cluster
npm run dev   # http://localhost:3001
```

Si la API corre local en `http://localhost:8001`, esa también vale como `API_PREDICT_MME_URL`.

## En el cluster (k8s)

Servicio expuesto como NodePort `30602` + Ingress `mme.localhost` por la app `frontend-mme` (namespace `apps`). Manifests en `k8s/apps/frontend-mme/`. Server Actions resuelven `api-predict-mme.apps:8000` por DNS interno — el browser nunca toca la API directamente.

```bash
microk8s kubectl get pods -n apps -l app.kubernetes.io/name=frontend-mme
# UI: http://<NODE_IP>:30602
```

## Notas de seguridad

- `API_PREDICT_MME_URL` es **solo server-side**: el browser nunca ve la URL
  del backend. Todas las llamadas pasan por server actions.
- El disclaimer de falacia ecológica está fijo en `/mme` — no remover.
