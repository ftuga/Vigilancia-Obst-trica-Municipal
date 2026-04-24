"use client";

import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipProps,
} from "recharts";
import { nombreDepto } from "@/lib/divipola";

export interface DeptoBar {
  cod: string;
  razon_mme_por_1000: number;
  casos_avg: number;
  n_muni: number;
}

const TIER_COLORS = {
  alto: "hsl(0 84% 45%)",
  medio: "hsl(38 92% 50%)",
  bajo: "hsl(142 71% 40%)",
};

function tierFor(razon: number): keyof typeof TIER_COLORS {
  if (razon >= 1.5) return "alto";
  if (razon >= 0.8) return "medio";
  return "bajo";
}

export function DepartamentosBarChart({ data }: { data: DeptoBar[] }) {
  const sorted = [...data].sort(
    (a, b) => b.razon_mme_por_1000 - a.razon_mme_por_1000,
  );
  const enriched = sorted.map((d) => ({
    ...d,
    nombre: nombreDepto(d.cod),
    tier: tierFor(d.razon_mme_por_1000),
  }));

  const height = Math.max(280, enriched.length * 24);

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart
        data={enriched}
        layout="vertical"
        margin={{ top: 8, right: 32, left: 12, bottom: 8 }}
      >
        <XAxis
          type="number"
          tick={{ fontSize: 11 }}
          stroke="hsl(215 16% 47%)"
          domain={[0, "dataMax"]}
        />
        <YAxis
          type="category"
          dataKey="nombre"
          width={140}
          tick={{ fontSize: 11 }}
          stroke="hsl(215 16% 47%)"
          interval={0}
        />
        <Tooltip content={<DeptoTooltip />} />
        <Bar dataKey="razon_mme_por_1000" radius={[0, 3, 3, 0]}>
          {enriched.map((d) => (
            <Cell key={d.cod} fill={TIER_COLORS[d.tier]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function DeptoTooltip({ active, payload }: TooltipProps<number, string>) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload as DeptoBar & { nombre: string; tier: string };
  return (
    <div className="rounded-md border bg-background px-3 py-2 text-xs shadow-sm">
      <p className="font-semibold">{d.nombre}</p>
      <p className="text-muted-foreground">
        Razón promedio:{" "}
        <span className="font-medium text-foreground tabular-nums">
          {d.razon_mme_por_1000.toFixed(2)} × 1.000
        </span>
      </p>
      <p className="text-muted-foreground">
        Casos promedio:{" "}
        <span className="tabular-nums">{d.casos_avg.toFixed(1)}</span>
      </p>
      <p className="text-muted-foreground">
        Municipios en muestra:{" "}
        <span className="tabular-nums">{d.n_muni}</span>
      </p>
    </div>
  );
}
