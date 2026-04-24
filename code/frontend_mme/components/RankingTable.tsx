import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { RankingItem } from "@/app/api-actions";
import { isCIAvailable } from "@/lib/utils";
import { nombreDepto } from "@/lib/divipola";

export function RankingTable({
  items,
  caption,
}: {
  items: RankingItem[];
  caption?: string;
}) {
  if (items.length === 0) {
    return (
      <div className="rounded-lg border p-8 text-center text-sm text-muted-foreground">
        Sin datos disponibles.
      </div>
    );
  }

  return (
    <div className="rounded-lg border">
      {caption && (
        <div className="border-b bg-muted/30 px-4 py-2 text-sm font-medium">
          {caption}
        </div>
      )}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-12">#</TableHead>
            <TableHead>Municipio</TableHead>
            <TableHead>Departamento</TableHead>
            <TableHead className="text-right">Casos predichos</TableHead>
            <TableHead className="text-right">Razón × 1.000</TableHead>
            <TableHead className="text-right">IC 90%</TableHead>
            <TableHead className="text-right">Riesgo</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((item, i) => {
            const ciAvail = isCIAvailable(item.ci_low, item.ci_high);
            return (
              <TableRow key={item.cod_mpio} className="cursor-pointer">
                <TableCell className="text-muted-foreground">{i + 1}</TableCell>
                <TableCell className="font-medium">
                  <Link
                    href={`/mme/municipio/${item.cod_mpio}`}
                    className="hover:underline"
                  >
                    {item.nom_mpio ?? item.cod_mpio}
                  </Link>
                  {item.nom_mpio && (
                    <span className="ml-1 text-xs text-muted-foreground">
                      {item.cod_mpio}
                    </span>
                  )}
                </TableCell>
                <TableCell>
                  {item.nom_dpto ?? nombreDepto(item.departamento_cod)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {item.casos_mme_predichos.toFixed(1)}
                </TableCell>
                <TableCell className="text-right font-medium tabular-nums">
                  {item.razon_mme_por_1000.toFixed(2)}
                </TableCell>
                <TableCell className="text-right text-xs tabular-nums text-muted-foreground">
                  {ciAvail
                    ? `[${item.ci_low.toFixed(1)}, ${item.ci_high.toFixed(1)}]`
                    : "—"}
                </TableCell>
                <TableCell className="text-right">
                  <Badge variant={item.risk_tier}>{item.risk_tier}</Badge>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
