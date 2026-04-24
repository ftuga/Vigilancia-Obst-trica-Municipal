import Link from "next/link";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ModelInfoCard } from "@/components/ModelInfoCard";
import { RankingTable } from "@/components/RankingTable";
import {
  DepartamentosBarChart,
  type DeptoBar,
} from "@/components/DepartamentosBarChart";
import { getModelInfo, getRanking, type RankingItem } from "@/app/api-actions";
import { EcologicalFallacyDisclaimer } from "./disclaimer";

export const dynamic = "force-dynamic";

/**
 * Agrega ranking muni-level a estadísticas departamentales.
 * Devuelve razón y casos promedio por depto + cuántos muni de la muestra
 * pertenecen a cada uno (heurístico: depende del tamaño del top-N traído).
 */
function aggregateByDepto(items: RankingItem[]): DeptoBar[] {
  const buckets: Record<string, { razon: number[]; casos: number[] }> = {};
  for (const it of items) {
    const cod = it.departamento_cod.padStart(2, "0");
    buckets[cod] ??= { razon: [], casos: [] };
    buckets[cod].razon.push(it.razon_mme_por_1000);
    buckets[cod].casos.push(it.casos_mme_predichos);
  }
  return Object.entries(buckets).map(([cod, vals]) => ({
    cod,
    razon_mme_por_1000:
      vals.razon.reduce((a, b) => a + b, 0) / vals.razon.length,
    casos_avg:
      vals.casos.reduce((a, b) => a + b, 0) / vals.casos.length,
    n_muni: vals.razon.length,
  }));
}

export default async function MmePage() {
  const [info, ranking] = await Promise.all([
    getModelInfo(),
    // Top 200 muni para tener cobertura departamental amplia
    getRanking(undefined, 200),
  ]);

  const deptoStats = aggregateByDepto(ranking);
  const topMuni = ranking.slice(0, 10);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Vulnerabilidad obstétrica municipal
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Predicción C3 · razón MME por 1.000 habitantes · IC 90% bootstrap
          residual · {ranking.length} municipios en muestra
        </p>
      </div>

      <EcologicalFallacyDisclaimer />

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle>Departamentos por razón MME predicha</CardTitle>
            <CardDescription>
              Promedio de los municipios del top {ranking.length} en cada
              departamento. Color: <span className="text-risk-alto">alto</span>{" "}
              ≥1.5 ·{" "}
              <span className="text-risk-medio">medio</span> ≥0.8 ·{" "}
              <span className="text-risk-bajo">bajo</span> &lt;0.8.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {deptoStats.length === 0 ? (
              <p className="py-12 text-center text-sm text-muted-foreground">
                Sin datos. Verificar que api_predict_mme esté disponible.
              </p>
            ) : (
              <DepartamentosBarChart data={deptoStats} />
            )}
          </CardContent>
        </Card>
        <ModelInfoCard info={info} />
      </div>

      <div className="space-y-2">
        <RankingTable
          items={topMuni}
          caption="Top 10 municipios por razón MME predicha (clic para detalle)"
        />
        <div className="flex justify-end">
          <Link
            href="/mme/explorar"
            className="text-sm text-muted-foreground hover:text-foreground hover:underline"
          >
            Explorar todos los {ranking.length}+ municipios →
          </Link>
        </div>
      </div>
    </div>
  );
}
