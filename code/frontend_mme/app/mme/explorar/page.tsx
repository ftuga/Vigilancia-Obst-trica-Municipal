import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { MunicipiosTable } from "@/components/MunicipiosTable";
import { getRanking, getModelInfo } from "@/app/api-actions";
import { EcologicalFallacyDisclaimer } from "../disclaimer";

export const dynamic = "force-dynamic";

// Pedimos un top muy alto para traer todos los muni del panel (~1.122).
const FETCH_LIMIT = 2000;

export default async function ExplorarPage() {
  const [items, info] = await Promise.all([
    getRanking(undefined, FETCH_LIMIT),
    getModelInfo(),
  ]);

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <Link
            href="/mme"
            className="text-sm text-muted-foreground hover:underline"
          >
            ← Volver al mapa
          </Link>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">
            Explorar municipios
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {items.length} municipios predichos · ordená/filtrá por nombre,
            departamento, riesgo o razón. Clic en un nombre para el detalle.
          </p>
        </div>
        {info && (
          <p className="text-xs text-muted-foreground">
            Modelo v{info.version} · Spearman {info.test_spearman_dpto.toFixed(3)}
          </p>
        )}
      </div>

      <EcologicalFallacyDisclaimer />

      <Card>
        <CardHeader className="pb-2">
          <CardTitle>Listado completo</CardTitle>
        </CardHeader>
        <CardContent>
          <MunicipiosTable items={items} />
        </CardContent>
      </Card>
    </div>
  );
}
