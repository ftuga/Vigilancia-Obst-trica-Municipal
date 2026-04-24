import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function EcologicalFallacyDisclaimer() {
  return (
    <Card className="border-amber-200 bg-amber-50/50">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-semibold text-amber-900">
          Advertencia metodológica: falacia ecológica
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0 text-xs leading-relaxed text-amber-900/90">
        <p>
          El modelo predice{" "}
          <strong>vulnerabilidad obstétrica a nivel municipal</strong>, no el
          riesgo individual de una gestante. Las razones se calculan sobre
          población municipal; un municipio de riesgo &quot;alto&quot; no
          implica que toda gestante en ese municipio tenga riesgo alto, ni
          viceversa. Usar para priorización territorial, no para decisiones
          clínicas individuales. Ver{" "}
          <code className="rounded bg-amber-100 px-1 py-0.5">
            docs/mme/model-evaluation.md §3
          </code>
          .
        </p>
      </CardContent>
    </Card>
  );
}
