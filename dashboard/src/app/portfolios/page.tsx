"use client";

import { Boxes, Gauge, Lock, Network, Unlock } from "lucide-react";
import type { PortfolioDetail } from "@/lib/types";
import { useAlgoData } from "@/lib/data-provider";
import { PageHeader } from "@/components/ui/page-header";
import { Card, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { formatNumber, formatPercent } from "@/lib/format";
import { cn } from "@/lib/cn";

/** Human labels for the two sizing modes published by the HTTP contract. */
function sizingModeLabel(mode: PortfolioDetail["sizing_mode"]): string {
  return mode === "heat" ? "Equal heat" : "Variance scaled";
}

function correlationColor(value: number): string {
  const clamped = Math.max(-1, Math.min(1, value));
  if (clamped < 0) {
    return `rgba(56, 189, 148, ${(Math.abs(clamped) * 0.55).toFixed(2)})`;
  }
  return `rgba(245, 158, 11, ${(clamped * 0.55).toFixed(2)})`;
}

function Metric({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-xl border border-line bg-canvas/40 px-3 py-2.5">
      <p className="text-[9px] uppercase tracking-[0.12em] text-faint">{label}</p>
      <p className="num mt-1 text-[17px] font-medium leading-none text-ink">{value}</p>
    </div>
  );
}

function PortfolioCard({ portfolio }: { portfolio: PortfolioDetail }) {
  const heatPct = portfolio.target_heat_pct
    ? Math.min(100, (portfolio.heat / portfolio.target_heat_pct) * 100)
    : 0;
  const overHeat = Boolean(portfolio.target_heat_pct && portfolio.heat > portfolio.target_heat_pct);

  return (
    <Card className="p-4 sm:p-5">
      <CardHeader
        title={portfolio.name}
        hint="Risk budget and cross-correlation at a glance"
        action={
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="ink">{sizingModeLabel(portfolio.sizing_mode)}</Badge>
            <Badge tone={portfolio.symbol_lock ? "emerald" : "amber"} dot>
              {portfolio.symbol_lock ? (
                <Lock className="h-3 w-3" />
              ) : (
                <Unlock className="h-3 w-3" />
              )}
              {portfolio.symbol_lock ? "symbol lock" : "open symbols"}
            </Badge>
          </div>
        }
      />

      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Metric label="Heat" value={formatPercent(portfolio.heat, 2)} />
        <Metric label="Target" value={formatPercent(portfolio.target_heat_pct, 2)} />
        <Metric label="Symbols" value={formatNumber(portfolio.health.distinct_symbols)} />
        <Metric label="Avg corr" value={portfolio.health.avg_member_corr.toFixed(2)} />
      </div>

      <div className="mt-3">
        <div className="flex items-center justify-between text-[11px]">
          <span className="flex items-center gap-1.5 text-subtle">
            <Gauge className="h-3.5 w-3.5" /> Heat budget
          </span>
          <span className={cn("num", overHeat ? "text-amber" : "text-muted")}>
            {formatPercent(portfolio.heat, 2)} / {formatPercent(portfolio.target_heat_pct, 2)}
          </span>
        </div>
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/[0.08]">
          <div
            className={cn("h-full rounded-full", overHeat ? "bg-amber" : "bg-emerald")}
            style={{ width: `${heatPct}%` }}
          />
        </div>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <div>
          <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-faint">
            Members · {portfolio.members.length}
          </p>
          <div className="mt-2 divide-y divide-line">
            {portfolio.members.map((member) => (
              <div
                key={`${portfolio.portfolio_id}-${member.strategy_id}-${member.bot_id}`}
                className="flex items-center justify-between gap-3 py-2"
              >
                <div className="min-w-0">
                  <p className="truncate text-[13px] text-ink/90">{member.symbol}</p>
                  <p className="truncate font-mono text-[10px] text-faint">{member.strategy_id}</p>
                </div>
                <div className="flex shrink-0 items-center gap-3">
                  <span className="num text-[11px] text-subtle">
                    corr {member.avg_corr.toFixed(2)}
                  </span>
                  <span className="num text-[13px] text-ink">
                    {formatPercent(member.risk_pct, 2)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div>
          <p className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-[0.14em] text-faint">
            <Network className="h-3.5 w-3.5" /> Correlation
          </p>
          <div
            className="mt-2 grid gap-1"
            style={{
              gridTemplateColumns: `repeat(${Math.max(1, portfolio.correlation_matrix.labels.length)}, minmax(0, 1fr))`,
            }}
          >
            {portfolio.correlation_matrix.matrix.flatMap((row, rowIndex) =>
              row.map((value, columnIndex) => (
                <div
                  key={`${rowIndex}-${columnIndex}`}
                  title={`${portfolio.correlation_matrix.labels[rowIndex]} × ${portfolio.correlation_matrix.labels[columnIndex]}: ${value.toFixed(2)}`}
                  className="num flex aspect-square min-h-[24px] items-center justify-center rounded text-[9px] text-ink/80"
                  style={{ backgroundColor: correlationColor(value) }}
                >
                  {value.toFixed(1)}
                </div>
              )),
            )}
          </div>
          <p className="mt-2 text-[10px] text-faint">
            Max symbol exposure {formatPercent(portfolio.health.max_symbol_exposure, 0)}
          </p>
        </div>
      </div>
    </Card>
  );
}

export default function PortfoliosPage() {
  const { data } = useAlgoData();

  return (
    <div>
      <PageHeader
        eyebrow="Allocation"
        title="Portfolios"
        description="How vault strategies share the heat budget, and how correlated their edges really are."
        actions={
          <Badge tone="ink" dot className="h-7">
            {data.portfolios.length} portfolios
          </Badge>
        }
      />

      {data.portfolios.length ? (
        <div className="space-y-4">
          {data.portfolios.map((portfolio) => (
            <PortfolioCard key={portfolio.portfolio_id} portfolio={portfolio} />
          ))}
        </div>
      ) : (
        <EmptyState
          icon={<Boxes className="h-4 w-4" />}
          title="No portfolios yet"
          description="Deploy vault strategies into a portfolio to see heat and correlation here."
        />
      )}
    </div>
  );
}
