import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { ModelInfo } from "@/app/api-actions";

export function ModelInfoCard({ info }: { info: ModelInfo | null }) {
  if (!info) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Modelo en producción</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            API no disponible o sin champion cargado.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle>Modelo en producción</CardTitle>
          <Badge variant="outline">v{info.version}</Badge>
        </div>
      </CardHeader>
      <CardContent className="grid gap-3 text-sm">
        <Row label="Familia" value={info.family} />
        <Row label="Spearman test (dpto)" value={info.test_spearman_dpto.toFixed(3)} />
        <Row label="Precision@top-50" value={info.test_precision_at_50.toFixed(3)} />
        <Row label="Ciclo dataset" value={info.dataset_cycle} />
        <Row
          label="Bootstrap CI"
          value={info.residuals_available ? "90% disponible" : "punto (sin residuos)"}
        />
        <p className="pt-2 text-xs text-muted-foreground">
          Run{" "}
          <code className="rounded bg-muted px-1 py-0.5 text-[10px]">
            {info.run_id.slice(0, 8)}
          </code>
        </p>
      </CardContent>
    </Card>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium tabular-nums">{value}</span>
    </div>
  );
}
