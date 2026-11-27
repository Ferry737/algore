"use client";

import { useMemo, useState } from "react";
import { AnimatePresence, LayoutGroup, motion } from "framer-motion";
import { Archive, Download, FilterX, LineChart, Sigma } from "lucide-react";
import type { VaultStrategy } from "@/lib/types";
import { useAlgoData } from "@/lib/data-provider";
import { useToast } from "@/components/providers/toast-provider";
import { PageHeader } from "@/components/ui/page-header";
import { Card } from "@/components/ui/card";
import { Badge, type BadgeTone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScoreParts } from "@/components/ui/score-parts";
import { EmptyState } from "@/components/ui/empty-state";
import { HealthBadge } from "@/components/ui/status";
import { cn } from "@/lib/cn";

const MIN_SCORES = [0, 60, 70, 80] as const;

function titleCase(value: string): string {
  return value
    .split("-")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function parityTone(grade: string): BadgeTone {
  if (grade === "A" || grade === "B") {
    return "emerald";
  }
  if (grade === "F") {
    return "rose";
  }
  return "amber";
}

function FilterRow({
  id,
  label,
  options,
  value,
  onChange,
}: {
  id: string;
  label: string;
  options: string[];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-[72px] shrink-0 text-[11px] font-medium uppercase tracking-[0.12em] text-faint">
        {label}
      </span>
      <LayoutGroup id={`filter-${id}`}>
        <div className="no-scrollbar flex min-w-0 flex-1 gap-1.5 overflow-x-auto">
          {["all", ...options].map((option) => {
            const active = value === option;
            return (
              <button
                key={option}
                type="button"
                onClick={() => onChange(option)}
                className={cn(
                  "relative min-h-9 shrink-0 rounded-full px-3 text-[12px] font-medium transition",
                  active ? "text-ink" : "text-subtle hover:text-muted",
                )}
              >
                {active ? (
                  <motion.span
                    layoutId={`filter-${id}-active`}
                    className="absolute inset-0 rounded-full border border-line-strong bg-panel-2"
                    transition={{ type: "spring", stiffness: 520, damping: 38 }}
                  />
                ) : null}
                <span className="relative">
                  {option === "all" ? "All" : id === "archetype" ? titleCase(option) : option}
                </span>
              </button>
            );
          })}
        </div>
      </LayoutGroup>
    </div>
  );
}

function VaultCard({
  strategy,
  busy,
  onDownload,
}: {
  strategy: VaultStrategy;
  busy: boolean;
  onDownload: () => void;
}) {
  return (
    <motion.article
      layout
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.98 }}
      transition={{ type: "spring", stiffness: 320, damping: 30 }}
    >
      <Card className="flex h-full flex-col p-4 sm:p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="truncate text-[16px] font-medium tracking-[-0.02em] text-ink">
              {strategy.name}
            </h2>
            <p className="mt-1 text-[11px] text-subtle">
              {strategy.symbol} · {strategy.timeframe} · {titleCase(strategy.archetype)}
            </p>
          </div>
          <Badge tone={strategy.score >= 80 ? "emerald" : strategy.score >= 65 ? "ink" : "amber"}>
            <Sigma className="h-3 w-3" /> {strategy.score}
          </Badge>
        </div>

        <div className="mt-4 grid grid-cols-3 gap-2">
          <div className="rounded-xl border border-line bg-canvas/40 px-2.5 py-2.5">
            <p className="text-[9px] uppercase tracking-[0.12em] text-faint">OOS Sharpe</p>
            <p className="num mt-1 text-[17px] font-medium leading-none text-ink">
              {strategy.oos.sharpe.toFixed(2)}
            </p>
          </div>
          <div className="rounded-xl border border-line bg-canvas/40 px-2.5 py-2.5">
            <p className="text-[9px] uppercase tracking-[0.12em] text-faint">Max DD</p>
            <p className="num mt-1 text-[17px] font-medium leading-none text-ink">
              {strategy.oos.max_dd.toFixed(1)}%
            </p>
          </div>
          <div className="rounded-xl border border-line bg-canvas/40 px-2.5 py-2.5">
            <p className="text-[9px] uppercase tracking-[0.12em] text-faint">Avg corr</p>
            <p className="num mt-1 text-[17px] font-medium leading-none text-ink">
              {strategy.avg_corr !== undefined ? strategy.avg_corr.toFixed(2) : "—"}
            </p>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Badge tone={parityTone(strategy.parity_grade)}>parity {strategy.parity_grade}</Badge>
          <HealthBadge word={strategy.health} />
          <span className="num ml-auto text-[11px] text-subtle">
            {strategy.oos.trades} OOS trades
          </span>
        </div>

        <ScoreParts strategy={strategy} className="mt-3" />

        <div className="mt-auto pt-3">
          <Button size="sm" variant="secondary" className="w-full" onClick={onDownload} disabled={busy}>
            <Download className="h-3.5 w-3.5" /> {busy ? "Downloading" : "Download .mq5"}
          </Button>
        </div>
      </Card>
    </motion.article>
  );
}

export default function VaultPage() {
  const { mode, data, actions } = useAlgoData();
  const { toast } = useToast();
  const [symbol, setSymbol] = useState("all");
  const [timeframe, setTimeframe] = useState("all");
  const [archetype, setArchetype] = useState("all");
  const [minScore, setMinScore] = useState(0);
  const [downloading, setDownloading] = useState<string | null>(null);

  const symbols = useMemo(
    () => Array.from(new Set(data.vault.map((strategy) => strategy.symbol))).sort(),
    [data.vault],
  );
  const timeframes = useMemo(
    () => Array.from(new Set(data.vault.map((strategy) => strategy.timeframe))).sort(),
    [data.vault],
  );
  const archetypes = useMemo(
    () => Array.from(new Set(data.vault.map((strategy) => strategy.archetype))).sort(),
    [data.vault],
  );

  const filtered = useMemo(() => {
    return data.vault
      .filter((strategy) => {
        if (symbol !== "all" && strategy.symbol !== symbol) return false;
        if (timeframe !== "all" && strategy.timeframe !== timeframe) return false;
        if (archetype !== "all" && strategy.archetype !== archetype) return false;
        if (strategy.score < minScore) return false;
        return true;
      })
      .sort((a, b) => b.score - a.score);
  }, [archetype, data.vault, minScore, symbol, timeframe]);

  const filtersActive = symbol !== "all" || timeframe !== "all" || archetype !== "all" || minScore > 0;

  const reset = () => {
    setSymbol("all");
    setTimeframe("all");
    setArchetype("all");
    setMinScore(0);
  };

  const download = async (strategy: VaultStrategy) => {
    setDownloading(strategy.strategy_id);
    try {
      const result = await actions.downloadMq5(strategy);
      toast({
        title: result.demo ? "Demo .mq5 downloaded" : ".mq5 downloaded",
        message: result.demo
          ? `${result.filename} is a generated placeholder. Set NEXT_PUBLIC_API_URL to fetch the real EA.`
          : `${result.filename} saved from the vault.`,
        tone: result.demo ? "amber" : "emerald",
      });
    } catch (error) {
      toast({
        title: "Download failed",
        message: error instanceof Error ? error.message : "The export endpoint rejected the request.",
        tone: "rose",
      });
    } finally {
      setDownloading(null);
    }
  };

  return (
    <div>
      <PageHeader
        eyebrow="Passport"
        title="Strategy vault"
        description="Every strategy that cleared the gates, with its out-of-sample record and parity grade."
        actions={
          <>
            <Badge tone="ink" dot className="h-7">
              {data.vault.length} strategies
            </Badge>
            {filtersActive ? (
              <Button size="sm" variant="ghost" onClick={reset}>
                <FilterX className="h-3.5 w-3.5" /> Reset
              </Button>
            ) : null}
          </>
        }
      />

      <Card className="p-4 sm:p-5">
        <div className="space-y-3">
          <FilterRow
            id="symbol"
            label="Symbol"
            options={symbols}
            value={symbol}
            onChange={setSymbol}
          />
          <FilterRow
            id="timeframe"
            label="Timeframe"
            options={timeframes}
            value={timeframe}
            onChange={setTimeframe}
          />
          <FilterRow
            id="archetype"
            label="Archetype"
            options={archetypes}
            value={archetype}
            onChange={setArchetype}
          />
          <FilterRow
            id="score"
            label="Min score"
            options={MIN_SCORES.filter((score) => score > 0).map(String)}
            value={minScore === 0 ? "all" : String(minScore)}
            onChange={(value) => setMinScore(value === "all" ? 0 : Number(value))}
          />
        </div>
        <div className="mt-4 flex items-center justify-between border-t border-line pt-3">
          <p className="text-[11px] text-subtle">
            <span className="num text-muted">{filtered.length}</span> shown
            {filtersActive ? " after filters" : ""}
          </p>
          <p className="flex items-center gap-1.5 text-[10px] text-faint">
            <LineChart className="h-3 w-3" /> OOS passport fields
          </p>
        </div>
      </Card>

      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <AnimatePresence mode="popLayout" initial={false}>
          {filtered.map((strategy) => (
            <VaultCard
              key={strategy.strategy_id}
              strategy={strategy}
              busy={downloading === strategy.strategy_id}
              onDownload={() => {
                void download(strategy);
              }}
            />
          ))}
        </AnimatePresence>
      </div>

      {filtered.length === 0 ? (
        <EmptyState
          icon={<Archive className="h-4 w-4" />}
          title="No strategies match"
          description="Loosen a filter or reset the passport search."
          className="mt-4"
        />
      ) : null}

      {mode === "demo" ? (
        <p className="mt-4 text-center text-[11px] leading-4 text-faint">
          Demo exports are generated placeholder text, not compiled EAs.
        </p>
      ) : null}
    </div>
  );
}
