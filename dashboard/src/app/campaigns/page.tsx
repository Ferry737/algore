"use client";

import { useMemo, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { LayoutGroup, motion } from "framer-motion";
import {
  ChevronRight,
  CircleStop,
  Dna,
  FlaskConical,
  Gauge,
  Play,
  Timer,
  Trophy,
} from "lucide-react";
import type { CampaignCreateInput, CampaignStage, CampaignSummary } from "@/lib/types";
import { useAlgoData } from "@/lib/data-provider";
import { useToast } from "@/components/providers/toast-provider";
import { PageHeader } from "@/components/ui/page-header";
import { Card, CardHeader } from "@/components/ui/card";
import { Badge, Dot, type BadgeTone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FitnessChart } from "@/components/ui/fitness-chart";
import { ConfirmSheet } from "@/components/ui/confirm-sheet";
import { EmptyState } from "@/components/ui/empty-state";
import { StageBadge } from "@/components/ui/status";
import { formatDuration } from "@/lib/format";
import { cn } from "@/lib/cn";

const TRIBES = ["Consistency", "Growth"] as const;
type Tribe = (typeof TRIBES)[number];

function statusTone(status: CampaignSummary["status"]): BadgeTone {
  switch (status) {
    case "running":
      return "emerald";
    case "done":
      return "emerald";
    case "queued":
      return "amber";
    case "failed":
      return "rose";
    default:
      return "neutral";
  }
}

function statusLabel(status: CampaignSummary["status"]): string {
  return status;
}

function FormField({
  label,
  htmlFor,
  children,
  hint,
}: {
  label: string;
  htmlFor: string;
  children: ReactNode;
  hint?: string;
}) {
  return (
    <div className="min-w-0">
      <label htmlFor={htmlFor} className="mb-1.5 block text-[11px] font-medium text-muted">
        {label}
      </label>
      {children}
      {hint ? <p className="mt-1 text-[10px] text-faint">{hint}</p> : null}
    </div>
  );
}

const inputClass =
  "h-11 w-full rounded-xl border border-line bg-canvas px-3 text-[13px] text-ink transition outline-none placeholder:text-faint focus:border-emerald/50 focus:ring-2 focus:ring-emerald/10";

export default function CampaignsPage() {
  const { mode, data, actions } = useAlgoData();
  const { toast } = useToast();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tribe, setTribe] = useState<Tribe>("Consistency");
  const [stopTarget, setStopTarget] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    name: "Aurora follow-up",
    symbol: "EURUSD",
    timeframe: "H1",
    generations: "20",
    population: "3000",
    seed: "42",
  });

  const fallbackSummary = useMemo(
    () =>
      data.campaigns.find((campaign) => campaign.status === "running") ??
      data.campaigns[0] ??
      null,
    [data.campaigns],
  );
  const selectedSummary = useMemo(
    () =>
      data.campaigns.find((campaign) => campaign.campaign_id === selectedId) ??
      fallbackSummary,
    [data.campaigns, fallbackSummary, selectedId],
  );
  const activeId = selectedSummary?.campaign_id ?? null;
  const detail = activeId ? data.campaignDetails[activeId] : undefined;
  const selected = detail ?? selectedSummary;
  const tribePoints = useMemo(
    () => (detail?.generations ?? []).filter((point) => point.tribe === tribe),
    [detail?.generations, tribe],
  );
  const lastPoint = tribePoints[tribePoints.length - 1];
  const progress =
    selected && selected.generations_total > 0
      ? Math.min(1, selected.generation / selected.generations_total)
      : 0;

  const startCampaign = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    try {
      const payload: CampaignCreateInput = {
        name: form.name.trim() || "Untitled run",
        symbol: form.symbol,
        timeframe: form.timeframe,
        generations: Number(form.generations) || 20,
        population: Number(form.population) || 3000,
        seed: Number(form.seed) || 42,
      };
      const campaignId = await actions.startCampaign(payload);
      setSelectedId(campaignId);
      toast({
        title: "Campaign queued",
        message:
          mode === "demo"
            ? `"${payload.name}" is running in the local simulation.`
            : `"${payload.name}" was accepted by the engine.`,
      });
    } catch (error) {
      toast({
        title: "Could not start campaign",
        message: error instanceof Error ? error.message : "The API rejected the request.",
        tone: "rose",
      });
    } finally {
      setBusy(false);
    }
  };

  const stopCampaign = async () => {
    if (!stopTarget) {
      return;
    }
    setBusy(true);
    try {
      await actions.stopCampaign(stopTarget);
      toast({ title: "Campaign stopped", message: "The run will finish its current generation." });
      setStopTarget(null);
    } catch (error) {
      toast({
        title: "Could not stop campaign",
        message: error instanceof Error ? error.message : "The API rejected the request.",
        tone: "rose",
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <PageHeader
        eyebrow="Breeder"
        title="Campaigns"
        description="Breed two tribes, merge the best, and hold the winner to the out-of-sample gates."
        actions={
          <>
            <Badge tone="ink" dot className="h-7">
              {data.campaigns.filter((campaign) => campaign.status === "running").length} running
            </Badge>
            <Button
              size="sm"
              onClick={() =>
                document
                  .getElementById("campaign-form")
                  ?.scrollIntoView({ behavior: "smooth", block: "start" })
              }
            >
              <Play className="h-3.5 w-3.5" /> New run
            </Button>
          </>
        }
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card className="p-4 sm:p-5">
            {selected ? (
              <>
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h2 className="text-[20px] font-medium tracking-[-0.025em] text-ink">
                        {selected.name}
                      </h2>
                      <Badge tone={statusTone(selected.status)} dot>
                        {statusLabel(selected.status)}
                      </Badge>
                      <StageBadge stage={selected.stage as CampaignStage} />
                    </div>
                    <p className="mt-1.5 text-[12px] text-subtle">
                      {selected.symbol} · {selected.timeframe} · {selected.campaign_id}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {selected.status === "running" || selected.status === "queued" ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setStopTarget(selected.campaign_id)}
                        disabled={busy}
                      >
                        <CircleStop className="h-3.5 w-3.5" /> Stop
                      </Button>
                    ) : null}
                  </div>
                </div>

                <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <div className="rounded-xl border border-line bg-canvas/40 p-3">
                    <p className="text-[10px] uppercase tracking-[0.14em] text-faint">Generation</p>
                    <p className="num mt-1.5 text-[20px] font-medium leading-none text-ink">
                      {selected.generation}
                      <span className="text-[12px] text-subtle"> / {selected.generations_total}</span>
                    </p>
                  </div>
                  <div className="rounded-xl border border-line bg-canvas/40 p-3">
                    <p className="text-[10px] uppercase tracking-[0.14em] text-faint">Best fitness</p>
                    <p className="num mt-1.5 text-[20px] font-medium leading-none text-ink">
                      {selected.best_fitness ? selected.best_fitness.toFixed(1) : "—"}
                    </p>
                  </div>
                  <div className="rounded-xl border border-line bg-canvas/40 p-3">
                    <p className="text-[10px] uppercase tracking-[0.14em] text-faint">Mean fitness</p>
                    <p className="num mt-1.5 text-[20px] font-medium leading-none text-ink">
                      {lastPoint ? lastPoint.mean_fitness.toFixed(1) : "—"}
                    </p>
                  </div>
                  <div className="rounded-xl border border-line bg-canvas/40 p-3">
                    <p className="text-[10px] uppercase tracking-[0.14em] text-faint">Elapsed / ETA</p>
                    <p className="num mt-1.5 text-[20px] font-medium leading-none text-ink">
                      {formatDuration(selected.elapsed_s)}
                    </p>
                    <p className="num mt-1 text-[10px] text-subtle">
                      ETA {formatDuration(selected.eta_s)}
                    </p>
                  </div>
                </div>

                <div className="mt-4">
                  <div className="flex items-center justify-between text-[11px] text-subtle">
                    <span>Breeding progress</span>
                    <span className="num">{Math.round(progress * 100)}%</span>
                  </div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
                    <motion.div
                      className="h-full rounded-full bg-emerald"
                      initial={{ width: 0 }}
                      animate={{ width: `${progress * 100}%` }}
                      transition={{ type: "spring", stiffness: 80, damping: 20 }}
                    />
                  </div>
                </div>

                <div className="mt-5 flex items-center justify-between gap-3">
                  <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-faint">
                    Fitness convergence
                  </p>
                  <LayoutGroup id="tribe-tabs">
                    <div className="flex rounded-xl border border-line bg-canvas/40 p-1">
                      {TRIBES.map((item) => (
                        <button
                          key={item}
                          type="button"
                          onClick={() => setTribe(item)}
                          className={cn(
                            "relative min-h-9 rounded-lg px-3 text-[12px] font-medium transition",
                            tribe === item ? "text-ink" : "text-subtle hover:text-muted",
                          )}
                        >
                          {tribe === item ? (
                            <motion.span
                              layoutId="tribe-active"
                              className="absolute inset-0 rounded-lg border border-line-strong bg-panel-2"
                              transition={{ type: "spring", stiffness: 500, damping: 38 }}
                            />
                          ) : null}
                          <span className="relative">{item}</span>
                        </button>
                      ))}
                    </div>
                  </LayoutGroup>
                </div>

                <div className="mt-3">
                  {tribePoints.length ? (
                    <FitnessChart points={detail?.generations ?? []} tribe={tribe} />
                  ) : (
                    <EmptyState
                      icon={<Dna className="h-4 w-4" />}
                      title="Waiting for the first generation"
                      description={
                        selected.status === "queued"
                          ? "This run is queued behind the engine's two workers."
                          : "The first scored generation will draw here."
                      }
                    />
                  )}
                </div>

                <div className="mt-4 grid grid-cols-2 gap-3 border-t border-line pt-4 sm:grid-cols-4">
                  <div className="flex items-center gap-2">
                    <Gauge className="h-3.5 w-3.5 text-faint" />
                    <span className="text-[11px] text-subtle">
                      <span className="num text-muted">{selected.vaulted}</span> vaulted
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Trophy className="h-3.5 w-3.5 text-faint" />
                    <span className="text-[11px] text-subtle">
                      <span className="num text-muted">
                        {lastPoint?.survivors ?? "—"}
                      </span>{" "}
                      survivors
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <FlaskConical className="h-3.5 w-3.5 text-faint" />
                    <span className="text-[11px] text-subtle">
                      gates {selected.status === "done" ? "cleared" : "pending"}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Timer className="h-3.5 w-3.5 text-faint" />
                    <span className="text-[11px] text-subtle">
                      stage <span className="text-muted">{selected.stage}</span>
                    </span>
                  </div>
                </div>
              </>
            ) : (
              <EmptyState
                icon={<Dna className="h-4 w-4" />}
                title="No campaign selected"
                description="Start a run to breed the first generation."
              />
            )}
          </Card>

          <Card className="p-4 sm:p-5">
            <CardHeader
              title="Run log"
              hint="Every campaign on the engine"
              action={<Badge tone="neutral">{data.campaigns.length} total</Badge>}
            />
            <div className="mt-2">
              {data.campaigns.length ? (
                data.campaigns.map((campaign) => {
                  const active = campaign.campaign_id === selectedId;
                  return (
                    <button
                      key={campaign.campaign_id}
                      type="button"
                      onClick={() => setSelectedId(campaign.campaign_id)}
                      className={cn(
                        "flex min-h-[56px] w-full items-center gap-3 rounded-xl border-t border-line px-2 py-2.5 text-left transition first:border-t-0",
                        active ? "bg-white/[0.035]" : "hover:bg-white/[0.02]",
                      )}
                    >
                      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-line bg-canvas/60">
                        {campaign.status === "running" ? (
                          <Dot tone="emerald" pulse />
                        ) : campaign.status === "done" ? (
                          <Dot tone="emerald" />
                        ) : campaign.status === "queued" ? (
                          <Dot tone="amber" />
                        ) : (
                          <Dot tone="neutral" />
                        )}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[13px] font-medium text-ink">
                          {campaign.name}
                        </span>
                        <span className="mt-0.5 block text-[11px] text-subtle">
                          {campaign.symbol} · {campaign.timeframe} · {campaign.stage}
                        </span>
                      </span>
                      <span className="num hidden text-[12px] text-muted sm:block">
                        {campaign.generation}/{campaign.generations_total}
                      </span>
                      <span className="num hidden text-[12px] text-muted md:block">
                        {campaign.best_fitness ? campaign.best_fitness.toFixed(1) : "—"}
                      </span>
                      <ChevronRight className="h-4 w-4 text-faint" />
                    </button>
                  );
                })
              ) : (
                <EmptyState
                  icon={<FlaskConical className="h-4 w-4" />}
                  title="No campaigns yet"
                  description="Start a run and the generation log will appear here."
                />
              )}
            </div>
          </Card>
        </div>

        <div className="lg:col-span-1">
          <Card id="campaign-form" className="p-4 sm:p-5 lg:sticky lg:top-24">
            <CardHeader
              title="Start a run"
              hint="Two tribes · 20 generations · final war"
              action={<Dna className="h-4 w-4 text-faint" />}
            />
            <form onSubmit={startCampaign} className="mt-4 space-y-3">
              <FormField label="Campaign name" htmlFor="campaign-name">
                <input
                  id="campaign-name"
                  className={inputClass}
                  value={form.name}
                  onChange={(event) => setForm({ ...form, name: event.target.value })}
                  placeholder="Aurora follow-up"
                  maxLength={64}
                  required
                />
              </FormField>
              <div className="grid grid-cols-2 gap-3">
                <FormField label="Symbol" htmlFor="campaign-symbol">
                  <select
                    id="campaign-symbol"
                    className={inputClass}
                    value={form.symbol}
                    onChange={(event) => setForm({ ...form, symbol: event.target.value })}
                  >
                    {["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "XAUUSD"].map((symbol) => (
                      <option key={symbol} value={symbol}>
                        {symbol}
                      </option>
                    ))}
                  </select>
                </FormField>
                <FormField label="Timeframe" htmlFor="campaign-timeframe">
                  <select
                    id="campaign-timeframe"
                    className={inputClass}
                    value={form.timeframe}
                    onChange={(event) => setForm({ ...form, timeframe: event.target.value })}
                  >
                    {["M15", "H1", "H4", "D1"].map((timeframe) => (
                      <option key={timeframe} value={timeframe}>
                        {timeframe}
                      </option>
                    ))}
                  </select>
                </FormField>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <FormField label="Generations" htmlFor="campaign-generations">
                  <input
                    id="campaign-generations"
                    type="number"
                    min={1}
                    max={200}
                    className={inputClass}
                    value={form.generations}
                    onChange={(event) => setForm({ ...form, generations: event.target.value })}
                  />
                </FormField>
                <FormField label="Population" htmlFor="campaign-population">
                  <input
                    id="campaign-population"
                    type="number"
                    min={10}
                    max={10000}
                    step={10}
                    className={inputClass}
                    value={form.population}
                    onChange={(event) => setForm({ ...form, population: event.target.value })}
                  />
                </FormField>
              </div>
              <FormField label="Seed" htmlFor="campaign-seed" hint="Same seed, same run.">
                <input
                  id="campaign-seed"
                  type="number"
                  className={inputClass}
                  value={form.seed}
                  onChange={(event) => setForm({ ...form, seed: event.target.value })}
                />
              </FormField>
              <Button type="submit" variant="primary" className="h-12 w-full" disabled={busy}>
                <Play className="h-4 w-4" /> Start campaign
              </Button>
              <p className="text-center text-[10px] leading-4 text-faint">
                {mode === "demo"
                  ? "Demo mode: the run is simulated locally."
                  : "POST /api/v1/campaigns · accepted as 202."}
              </p>
            </form>
          </Card>
        </div>
      </div>

      <ConfirmSheet
        open={stopTarget !== null}
        onClose={() => setStopTarget(null)}
        onConfirm={() => {
          void stopCampaign();
        }}
        tone="amber"
        title="Stop this campaign?"
        description="The engine will stop breeding at the current generation. Scored generations stay on the run."
        confirmLabel="Stop campaign"
      />
    </div>
  );
}
