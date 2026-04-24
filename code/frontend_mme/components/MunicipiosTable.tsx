"use client";

import { useMemo, useState } from "react";
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

type SortField = "razon" | "casos" | "nombre" | "depto";
type SortDir = "asc" | "desc";
type TierFilter = "alto" | "medio" | "bajo" | "todos";

const PAGE_SIZE = 50;

export function MunicipiosTable({ items }: { items: RankingItem[] }) {
  const [query, setQuery] = useState("");
  const [depto, setDepto] = useState<string>("todos");
  const [tier, setTier] = useState<TierFilter>("todos");
  const [sortField, setSortField] = useState<SortField>("razon");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [page, setPage] = useState(0);

  const deptosUnicos = useMemo(() => {
    const codes = new Set(
      items.map((i) => i.departamento_cod.padStart(2, "0")),
    );
    return [...codes].sort();
  }, [items]);

  const tierCounts = useMemo(() => {
    return {
      alto: items.filter((i) => i.risk_tier === "alto").length,
      medio: items.filter((i) => i.risk_tier === "medio").length,
      bajo: items.filter((i) => i.risk_tier === "bajo").length,
    };
  }, [items]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return items
      .filter((i) => {
        if (depto !== "todos" && i.departamento_cod.padStart(2, "0") !== depto) {
          return false;
        }
        if (tier !== "todos" && i.risk_tier !== tier) return false;
        if (q) {
          const haystack =
            `${i.cod_mpio} ${i.nom_mpio ?? ""} ${i.nom_dpto ?? ""}`.toLowerCase();
          if (!haystack.includes(q)) return false;
        }
        return true;
      })
      .sort((a, b) => {
        const dir = sortDir === "asc" ? 1 : -1;
        switch (sortField) {
          case "razon":
            return dir * (a.razon_mme_por_1000 - b.razon_mme_por_1000);
          case "casos":
            return dir * (a.casos_mme_predichos - b.casos_mme_predichos);
          case "nombre":
            return (
              dir * (a.nom_mpio ?? a.cod_mpio).localeCompare(b.nom_mpio ?? b.cod_mpio)
            );
          case "depto":
            return (
              dir *
              (a.nom_dpto ?? a.departamento_cod).localeCompare(
                b.nom_dpto ?? b.departamento_cod,
              )
            );
        }
      });
  }, [items, query, depto, tier, sortField, sortDir]);

  // Reset page si los filtros reducen la lista por debajo del current
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages - 1);
  const visible = filtered.slice(safePage * PAGE_SIZE, (safePage + 1) * PAGE_SIZE);

  const toggleSort = (field: SortField) => {
    if (field === sortField) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortDir(field === "razon" || field === "casos" ? "desc" : "asc");
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="search"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setPage(0);
          }}
          placeholder="Buscar por nombre o código DIVIPOLA…"
          className="h-9 flex-1 min-w-[240px] rounded-md border border-border bg-background px-3 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary"
        />
        <select
          value={depto}
          onChange={(e) => {
            setDepto(e.target.value);
            setPage(0);
          }}
          className="h-9 rounded-md border border-border bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
        >
          <option value="todos">Todos los departamentos</option>
          {deptosUnicos.map((cod) => (
            <option key={cod} value={cod}>
              {nombreDepto(cod)} ({cod})
            </option>
          ))}
        </select>
        <div className="flex items-center gap-1 text-xs">
          {(["todos", "alto", "medio", "bajo"] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => {
                setTier(t);
                setPage(0);
              }}
              className={`rounded-md border px-2.5 py-1.5 transition-colors ${
                tier === t
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border bg-background hover:bg-muted"
              }`}
            >
              {t === "todos"
                ? "Todos"
                : `${t} (${tierCounts[t]})`}
            </button>
          ))}
        </div>
      </div>

      <div className="rounded-lg border">
        <div className="border-b bg-muted/30 px-4 py-2 text-xs text-muted-foreground">
          {filtered.length} de {items.length} municipios · página {safePage + 1}/
          {totalPages}
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-12">#</TableHead>
              <SortHeader
                label="Municipio"
                active={sortField === "nombre"}
                dir={sortDir}
                onClick={() => toggleSort("nombre")}
              />
              <SortHeader
                label="Departamento"
                active={sortField === "depto"}
                dir={sortDir}
                onClick={() => toggleSort("depto")}
              />
              <SortHeader
                label="Casos"
                active={sortField === "casos"}
                dir={sortDir}
                onClick={() => toggleSort("casos")}
                align="right"
              />
              <SortHeader
                label="Razón × 1.000"
                active={sortField === "razon"}
                dir={sortDir}
                onClick={() => toggleSort("razon")}
                align="right"
              />
              <TableHead className="text-right">IC 90%</TableHead>
              <TableHead className="text-right">Riesgo</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {visible.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={7}
                  className="py-8 text-center text-sm text-muted-foreground"
                >
                  Sin resultados con los filtros aplicados.
                </TableCell>
              </TableRow>
            ) : (
              visible.map((item, i) => {
                const ciAvail = isCIAvailable(item.ci_low, item.ci_high);
                return (
                  <TableRow key={item.cod_mpio}>
                    <TableCell className="text-muted-foreground">
                      {safePage * PAGE_SIZE + i + 1}
                    </TableCell>
                    <TableCell>
                      <Link
                        href={`/mme/municipio/${item.cod_mpio}`}
                        className="font-medium hover:underline"
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
              })
            )}
          </TableBody>
        </Table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between gap-2 text-sm">
          <button
            type="button"
            disabled={safePage === 0}
            onClick={() => setPage(Math.max(0, safePage - 1))}
            className="h-8 rounded-md border border-border px-3 text-sm disabled:opacity-40 hover:bg-muted disabled:hover:bg-background"
          >
            ← Anterior
          </button>
          <span className="text-xs text-muted-foreground">
            Mostrando {safePage * PAGE_SIZE + 1}–
            {Math.min((safePage + 1) * PAGE_SIZE, filtered.length)} de{" "}
            {filtered.length}
          </span>
          <button
            type="button"
            disabled={safePage >= totalPages - 1}
            onClick={() => setPage(Math.min(totalPages - 1, safePage + 1))}
            className="h-8 rounded-md border border-border px-3 text-sm disabled:opacity-40 hover:bg-muted disabled:hover:bg-background"
          >
            Siguiente →
          </button>
        </div>
      )}
    </div>
  );
}

function SortHeader({
  label,
  active,
  dir,
  onClick,
  align = "left",
}: {
  label: string;
  active: boolean;
  dir: SortDir;
  onClick: () => void;
  align?: "left" | "right";
}) {
  return (
    <TableHead className={align === "right" ? "text-right" : ""}>
      <button
        type="button"
        onClick={onClick}
        className={`inline-flex items-center gap-1 hover:text-foreground ${
          active ? "text-foreground" : "text-muted-foreground"
        }`}
      >
        {label}
        {active ? (
          <span aria-hidden>{dir === "asc" ? "↑" : "↓"}</span>
        ) : (
          <span className="opacity-30" aria-hidden>
            ↕
          </span>
        )}
      </button>
    </TableHead>
  );
}
