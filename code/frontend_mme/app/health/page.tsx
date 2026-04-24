import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { pingHealth, getModelInfo } from "@/app/api-actions";

export const dynamic = "force-dynamic";

export default async function HealthPage() {
  const [h, info] = await Promise.all([pingHealth(), getModelInfo()]);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">Estado del servicio</h1>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle>api_predict_mme</CardTitle>
              <Badge variant={h.healthz && h.readyz ? "bajo" : "alto"}>
                {h.healthz && h.readyz ? "ok" : "caído"}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <Row label="/healthz" ok={h.healthz} />
            <Row label="/readyz" ok={h.readyz} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle>Champion</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {info ? (
              <>
                <Row label="Versión" value={info.version} />
                <Row label="Familia" value={info.family} />
                <Row label="Spearman test" value={info.test_spearman_dpto.toFixed(3)} />
                <Row
                  label="Residuals"
                  value={info.residuals_available ? "disponibles" : "no (CI degenerado)"}
                />
                <Row
                  label="Baseline"
                  value={info.baseline_available ? "disponible" : "no"}
                />
              </>
            ) : (
              <p className="text-muted-foreground">No se pudo consultar /model/info.</p>
            )}
          </CardContent>
        </Card>
      </div>

      {Object.keys(h.details).length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle>Detalles /readyz</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="overflow-auto rounded bg-muted p-3 text-xs">
              {JSON.stringify(h.details, null, 2)}
            </pre>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function Row({ label, ok, value }: { label: string; ok?: boolean; value?: string }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-muted-foreground">{label}</span>
      {ok !== undefined ? (
        <Badge variant={ok ? "bajo" : "alto"}>{ok ? "ok" : "fail"}</Badge>
      ) : (
        <span className="font-medium tabular-nums">{value}</span>
      )}
    </div>
  );
}
