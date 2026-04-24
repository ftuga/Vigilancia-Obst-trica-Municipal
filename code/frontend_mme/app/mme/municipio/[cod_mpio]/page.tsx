import Link from "next/link";
import { notFound } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { SerieTemporalChart } from "@/components/SerieTemporalChart";
import { getMuniDetail, getModelInfo } from "@/app/api-actions";
import { isCIAvailable } from "@/lib/utils";
import { nombreDepto } from "@/lib/divipola";
import { EcologicalFallacyDisclaimer } from "../../disclaimer";

export const dynamic = "force-dynamic";

export default async function MunicipioPage({
  params,
}: {
  params: { cod_mpio: string };
}) {
  if (!/^\d{5}$/.test(params.cod_mpio)) {
    notFound();
  }

  const [detail, info] = await Promise.all([
    getMuniDetail(params.cod_mpio),
    getModelInfo(),
  ]);

  if (!detail.latest) {
    return (
      <div className="space-y-6">
        <Link href="/mme" className="text-sm text-muted-foreground hover:underline">
          ← Volver al mapa
        </Link>
        <Card>
          <CardHeader>
            <CardTitle>Municipio {params.cod_mpio} sin datos</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              No se encontraron predicciones para este código DIVIPOLA en el
              panel actual ({info?.dataset_cycle ?? "—"}).
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const dptoNombre = detail.latest.nom_dpto ?? nombreDepto(detail.departamento_cod);
  const muniNombre = detail.latest.nom_mpio ?? params.cod_mpio;
  const aniosConDatos = detail.serie.filter((p) => p.available).length;
  const ciLatestAvail = isCIAvailable(
    detail.latest.ci_low,
    detail.latest.ci_high,
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <Link
            href="/mme"
            className="text-sm text-muted-foreground hover:underline"
          >
            ← Volver al mapa
          </Link>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">
            {muniNombre}
          </h1>
          <p className="text-sm text-muted-foreground">
            {dptoNombre} · DIVIPOLA {params.cod_mpio} · serie {detail.serie[0]?.anio}–
            {detail.serie[detail.serie.length - 1]?.anio} ({aniosConDatos} años con datos)
          </p>
        </div>
        <Badge variant={detail.latest.risk_tier}>
          Riesgo {detail.latest.risk_tier}
        </Badge>
      </div>

      <EcologicalFallacyDisclaimer />

      <div className="grid gap-4 md:grid-cols-3">
        <MetricCard
          label="Casos predichos (último año)"
          value={detail.latest.casos_mme_predichos.toFixed(1)}
          sub={`Año ${detail.latest.anio}`}
        />
        <MetricCard
          label="Razón × 1.000 hab"
          value={detail.latest.razon_mme_por_1000.toFixed(2)}
          sub={
            ciLatestAvail
              ? `IC ${(detail.latest.ci_level * 100).toFixed(0)}%: [${detail.latest.ci_low.toFixed(1)}, ${detail.latest.ci_high.toFixed(1)}]`
              : "IC no disponible (champion sin residuos)"
          }
        />
        <MetricCard
          label="Predicción puntual"
          value={ciLatestAvail ? "con IC bootstrap" : "sin IC"}
          sub={
            ciLatestAvail
              ? `${detail.latest.n_bootstrap} replicates · seed fija`
              : "Próximo retrain incorporará residuals.npy"
          }
        />
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle>Serie temporal — Razón MME predicha</CardTitle>
        </CardHeader>
        <CardContent>
          <SerieTemporalChart serie={detail.serie} metric="razon" />
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle>Detalle por año</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Año</TableHead>
                <TableHead className="text-right">Casos</TableHead>
                <TableHead className="text-right">Razón × 1.000</TableHead>
                <TableHead className="text-right">IC 90%</TableHead>
                <TableHead className="text-right">Riesgo</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {detail.serie.map((p) => (
                <TableRow key={p.anio}>
                  <TableCell className="font-medium">{p.anio}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {p.available ? p.casos_mme_predichos.toFixed(1) : "—"}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {p.available ? p.razon_mme_por_1000.toFixed(2) : "—"}
                  </TableCell>
                  <TableCell className="text-right text-xs text-muted-foreground tabular-nums">
                    {p.available && isCIAvailable(p.ci_low, p.ci_high)
                      ? `[${p.ci_low.toFixed(1)}, ${p.ci_high.toFixed(1)}]`
                      : "—"}
                  </TableCell>
                  <TableCell className="text-right">
                    {p.available ? (
                      <Badge variant={p.risk_tier}>{p.risk_tier}</Badge>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

function MetricCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub: string;
}) {
  return (
    <Card>
      <CardContent className="pt-6">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
        <p className="mt-1 text-xs text-muted-foreground">{sub}</p>
      </CardContent>
    </Card>
  );
}
