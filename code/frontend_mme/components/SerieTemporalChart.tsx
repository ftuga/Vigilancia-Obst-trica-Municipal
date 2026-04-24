"use client";

import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipProps,
} from "recharts";
import type { TemporalPoint } from "@/app/api-actions";

interface SerieTemporalChartProps {
  serie: TemporalPoint[];
  metric?: "razon" | "casos";
}

export function SerieTemporalChart({
  serie,
  metric = "razon",
}: SerieTemporalChartProps) {
  const data = serie.map((p) => {
    const center =
      metric === "razon" ? p.razon_mme_por_1000 : p.casos_mme_predichos;
    // Para razón, los CI vienen en escala count → reescalar proporcionalmente.
    // Si la razón es center y los counts son y_point, scale = razon/y_point.
    const scale =
      metric === "razon" && p.casos_mme_predichos > 0
        ? p.razon_mme_por_1000 / p.casos_mme_predichos
        : 1;
    return {
      anio: p.anio,
      center: p.available ? center : null,
      ci_low: p.available ? p.ci_low * scale : null,
      ci_high: p.available ? p.ci_high * scale : null,
      ci_band: p.available ? [p.ci_low * scale, p.ci_high * scale] : null,
    };
  });

  const yLabel =
    metric === "razon" ? "Razón MME × 1.000 hab" : "Casos MME predichos (semestre)";

  return (
    <ResponsiveContainer width="100%" height={300}>
      <ComposedChart data={data} margin={{ top: 16, right: 24, left: 8, bottom: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="hsl(220 13% 91%)" />
        <XAxis
          dataKey="anio"
          tick={{ fontSize: 12 }}
          stroke="hsl(215 16% 47%)"
        />
        <YAxis
          tick={{ fontSize: 12 }}
          stroke="hsl(215 16% 47%)"
          label={{
            value: yLabel,
            angle: -90,
            position: "insideLeft",
            style: { fill: "hsl(215 16% 47%)", fontSize: 11 },
          }}
        />
        <Tooltip content={<CustomTooltip metric={metric} />} />
        <Area
          type="monotone"
          dataKey="ci_band"
          stroke="none"
          fill="hsl(0 84% 45%)"
          fillOpacity={0.12}
          name="IC 90%"
          isAnimationActive={false}
        />
        <Line
          type="monotone"
          dataKey="center"
          stroke="hsl(0 84% 45%)"
          strokeWidth={2}
          dot={{ r: 3, fill: "hsl(0 84% 45%)" }}
          activeDot={{ r: 5 }}
          name="Predicción"
          isAnimationActive={false}
          connectNulls={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

function CustomTooltip({
  active,
  payload,
  label,
  metric,
}: TooltipProps<number, string> & { metric: "razon" | "casos" }) {
  if (!active || !payload?.length) return null;
  const center = payload.find((p) => p.dataKey === "center");
  const band = payload.find((p) => p.dataKey === "ci_band");
  const bandValue = Array.isArray(band?.value) ? band.value : null;
  const unit = metric === "razon" ? "× 1.000" : "casos";

  return (
    <div className="rounded-md border bg-background px-3 py-2 text-xs shadow-sm">
      <p className="font-semibold">{label}</p>
      <p className="text-muted-foreground">
        Predicción:{" "}
        <span className="font-medium text-foreground tabular-nums">
          {center?.value != null ? Number(center.value).toFixed(2) : "—"} {unit}
        </span>
      </p>
      {bandValue && (
        <p className="text-muted-foreground">
          IC 90%:{" "}
          <span className="tabular-nums">
            [{Number(bandValue[0]).toFixed(2)}, {Number(bandValue[1]).toFixed(2)}]
          </span>
        </p>
      )}
    </div>
  );
}
