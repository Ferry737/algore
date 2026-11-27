"use client";

import { useState } from "react";
import { LayoutGroup, motion } from "framer-motion";
import {
  CheckCircle2,
  ChevronUp,
  GraduationCap,
  MinusCircle,
} from "lucide-react";
import type { IncubationBot, Tier } from "@/lib/types";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Toggle } from "@/components/ui/toggle";
import { LadderRing } from "@/components/ui/ladder-ring";
import { FrozenBadge, HealthBadge, PilotBadge } from "@/components/ui/status";
import { formatPercent, formatSigned } from "@/lib/format";
import { cn } from "@/lib/cn";

const RUNGS: Array<{ tier: Exclude<Tier, null>; multiplier: number }> = [
  { tier: "INCUBATION", multiplier: 0.25 },
  { tier: "PROVING", multiplier: 0.5 },
  { tier: "FULL", multiplier: 1 },
];

function ProgressRow({
  label,
  current,
  target,
  detail,
  frozen,
}: {
  label: string;
  current: number;
  target: number;
  detail: string;
  frozen: boolean;
}) {
  const ratio = target > 0 ? Math.min(1, current / target) : 0;
  return (
    <div>
      <div className="flex items-center justify-between gap-3">
        <span className="text-[11px] font-medium text-muted">{label}</span>
        <span className="num text-[11px] text-subtle">
          {Math.min(current, target)} / {target}
        </span>
      </div>
      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
        <motion.div
          className={cn("h-full rounded-full", frozen ? "bg-amber" : "bg-emerald")}
          initial={{ width: 0 }}
          animate={{ width: `${ratio * 100}%` }}
          transition={{ type: "spring", stiffness: 80, damping: 20 }}
        />
      </div>
      <p className="mt-1 text-[10px] leading-4 text-faint">{detail}</p>
    </div>
  );
}

function RungRail({ bot }: { bot: IncubationBot }) {
  return (
    <div className="relative mt-5 px-1">
      <div className="absolute inset-x-[16%] top-[11px] h-px bg-white/[0.08]" />
      <div className="relative flex justify-between">
        {RUNGS.map((rung) => {
          const reached = bot.multiplier + 0.001 >= rung.multiplier;
          const current = bot.tier === rung.tier;
          return (
            <div key={rung.tier} className="flex w-1/3 flex-col items-center gap-1.5 text-center">
              <span
                className={cn(
                  "flex h-6 w-6 items-center justify-center rounded-full border text-[10px]",
                  current
                    ? "border-ink bg-ink text-canvas"
                    : reached
                      ? "border-emerald/40 bg-emerald/10 text-emerald"
                      : "border-line bg-canvas text-faint",
                )}
              >
                {current ? (
                  <span className="h-1.5 w-1.5 rounded-full bg-canvas" />
                ) : reached ? (
                  <CheckCircle2 className="h-3 w-3" />
                ) : (
                  <span className="h-1 w-1 rounded-full bg-current" />
                )}
              </span>
              <span
                className={cn(
                  "text-[10px] font-medium tracking-[0.04em]",
                  current ? "text-ink" : "text-subtle",
                )}
              >
                {rung.tier}
              </span>
              <span className="num text-[11px] text-faint">
                {Math.round(rung.multiplier * 100)}%
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Checks({ bot }: { bot: IncubationBot }) {
  const passed = bot.checks.filter((check) => check.pass).length;
  return (
    <div className="mt-4 border-t border-line pt-3">
      <div className="flex items-center justify-between">
        <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-faint">Eight checks</p>
        <span className="num text-[11px] text-subtle">{passed}/8 pass</span>
      </div>
      <div className="mt-2 grid grid-cols-1 gap-1 sm:grid-cols-2">
        {bot.checks.length ? (
          bot.checks.map((check) => (
            <div key={check.id} className="flex min-h-6 items-center gap-2">
              {check.pass ? (
                <CheckCircle2 className="h-3 w-3 shrink-0 text-emerald" />
              ) : (
                <MinusCircle className="h-3 w-3 shrink-0 text-amber" />
              )}
              <span className="truncate text-[11px] text-muted">{check.label}</span>
              <span className={cn("ml-auto text-[9px] font-medium", check.pass ? "text-emerald" : "text-amber")}>
                {check.pass ? "PASS" : "HELD"}
              </span>
            </div>
          ))
        ) : (
          <p className="text-[11px] text-faint">Checks not reported yet.</p>
        )}
      </div>
    </div>
  );
}

function RungMenu({
  disabled,
  onSetRung,
}: {
  disabled: boolean;
  onSetRung: (rung: Exclude<Tier, null>, reason: string) => Promise<void>;
}) {
  const [reason, setReason] = useState("Manual rung override");
  return (
    <details className="relative">
      <summary className="flex h-11 min-w-[112px] cursor-pointer list-none items-center justify-center gap-1.5 rounded-xl border border-line-strong bg-panel-2 px-3 text-[12px] font-medium text-ink transition hover:bg-panel-3 [&::-webkit-details-marker]:hidden">
        <ChevronUp className="h-3.5 w-3.5" /> Set rung
      </summary>
      <div className="absolute bottom-full right-0 z-30 mb-2 w-[248px] rounded-2xl border border-line-strong bg-panel p-3 shadow-[0_18px_50px_rgba(0,0,0,0.6)]">
        <label htmlFor="rung-reason" className="mb-1.5 block text-[10px] font-medium uppercase tracking-[0.12em] text-faint">
          Reason
        </label>
        <input
          id="rung-reason"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          maxLength={80}
          className="h-10 w-full rounded-lg border border-line bg-canvas px-2.5 text-[12px] text-ink outline-none focus:border-emerald/50"
        />
        <div className="mt-2 grid gap-1">
          {RUNGS.map((rung) => (
            <button
              key={rung.tier}
              type="button"
              disabled={disabled}
              onClick={(event) => {
                event.currentTarget.closest("details")?.removeAttribute("open");
                void onSetRung(rung.tier, reason.trim() || "Manual rung override");
              }}
              className="flex min-h-11 items-center justify-between rounded-lg px-2.5 text-[12px] text-muted transition hover:bg-white/[0.05] hover:text-ink disabled:opacity-40"
            >
              <span>{rung.tier}</span>
              <span className="num text-[11px] text-subtle">{Math.round(rung.multiplier * 100)}%</span>
            </button>
          ))}
        </div>
      </div>
    </details>
  );
}

export function IncubationCard({
  bot,
  busy,
  onAuto,
  onPause,
  onGraduate,
  onSetRung,
}: {
  bot: IncubationBot;
  busy: boolean;
  onAuto: (auto: boolean) => Promise<void>;
  onPause: (paused: boolean) => Promise<void>;
  onGraduate: () => Promise<void>;
  onSetRung: (rung: Exclude<Tier, null>, reason: string) => Promise<void>;
}) {
  const simOk = bot.checks.find((check) => check.id === "simulated_record")?.pass ?? false;
  const liveGoal = bot.tier === "INCUBATION" ? 10 : 30;
  const simGoal = bot.tier === "INCUBATION" ? 5 : 30;
  const simCurrent =
    bot.tier === "INCUBATION"
      ? bot.healthy_live_trades
      : bot.healthy_live_trades + bot.sim_healthy_trades;
  const nextTier: Exclude<Tier, null> =
    bot.tier === "INCUBATION" ? "PROVING" : bot.tier === "PROVING" ? "FULL" : "FULL";

  return (
    <Card className="flex flex-col p-4 sm:p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate text-[18px] font-medium tracking-[-0.025em] text-ink">
            {bot.strategy_name ?? bot.bot_id}
          </h2>
          <p className="mt-1 text-[11px] text-subtle">
            {bot.symbol ?? "—"} · {bot.bot_id}
          </p>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1.5">
          <PilotBadge state={bot.pilot_state} />
          <HealthBadge word={bot.health_word} />
        </div>
      </div>

      {bot.frozen_reason ? (
        <div className="mt-3">
          <FrozenBadge reason={bot.frozen_reason} />
        </div>
      ) : null}

      <div className="mt-4 flex items-center gap-4 sm:gap-5">
        <LadderRing multiplier={bot.multiplier} frozen={Boolean(bot.frozen_reason)} size={112} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-faint">
              {bot.tier ?? "NO TIER"}
            </p>
            {bot.pending_graduation ? (
              <Badge tone="amber" dot>
                pending
              </Badge>
            ) : null}
          </div>
          <p className="num mt-1 text-[24px] font-medium leading-none tracking-[-0.04em] text-ink">
            {formatPercent(bot.effective_risk_pct, 2)}
            <span className="ml-1 text-[11px] font-normal text-subtle">effective</span>
          </p>
          <p className="num mt-1.5 text-[11px] text-subtle">
            target {formatPercent(bot.target_risk_pct, 2)} · {bot.multiplier.toFixed(2)}× rung
          </p>
          <div className="mt-3 flex flex-wrap gap-1.5">
            <Badge tone={bot.live_net_r >= 0 ? "emerald" : "rose"}>
              {formatSigned(bot.live_net_r, 1, "R")} live
            </Badge>
            <Badge tone="neutral" className="num">
              {bot.healthy_live_trades} healthy / {bot.live_trades} live
            </Badge>
          </div>
        </div>
      </div>

      <RungRail bot={bot} />

      <div className="mt-4 space-y-3">
        {bot.tier === "FULL" ? (
          <div className="rounded-xl border border-line bg-canvas/40 px-3 py-2.5">
            <p className="text-[12px] text-muted">Full risk. Monitoring for decay and silence.</p>
            <p className="mt-1 text-[10px] text-faint">
              Any rung-worthy event still has to clear the eight checks.
            </p>
          </div>
        ) : (
          <>
            <ProgressRow
              label="Live path"
              current={bot.healthy_live_trades}
              target={liveGoal}
              detail={
                bot.tier === "INCUBATION"
                  ? "Healthy live trades to PROVING."
                  : "Healthy live trades to FULL; live net R must stay positive."
              }
              frozen={Boolean(bot.frozen_reason)}
            />
            <ProgressRow
              label="Simulated path"
              current={simCurrent}
              target={simGoal}
              detail={
                bot.tier === "INCUBATION"
                  ? `Simulated record ${simOk ? "passes" : "held"} · 5 live to PROVING.`
                  : `${bot.healthy_live_trades} live + ${bot.sim_healthy_trades} sim · 10 live minimum.`
              }
              frozen={Boolean(bot.frozen_reason)}
            />
          </>
        )}
      </div>

      <Checks bot={bot} />

      <div className="mt-4 flex flex-col gap-3 border-t border-line pt-4 lg:flex-row lg:items-center lg:justify-between">
        <LayoutGroup id={`${bot.bot_id}-mode`}>
          <div className="inline-flex rounded-xl border border-line bg-canvas/40 p-1">
            {[
              { label: "Auto", value: true },
              { label: "Manual", value: false },
            ].map((option) => {
              const active = bot.auto === option.value;
              return (
                <button
                  key={option.label}
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    void onAuto(option.value);
                  }}
                  className={cn(
                    "relative min-h-11 rounded-lg px-5 text-[12px] font-medium transition disabled:opacity-40",
                    active ? "text-ink" : "text-subtle hover:text-muted",
                  )}
                >
                  {active ? (
                    <motion.span
                      layoutId={`${bot.bot_id}-mode-active`}
                      className="absolute inset-0 rounded-lg border border-line-strong bg-panel-2"
                      transition={{ type: "spring", stiffness: 500, damping: 38 }}
                    />
                  ) : null}
                  <span className="relative">{option.label}</span>
                </button>
              );
            })}
          </div>
        </LayoutGroup>

        <div className="flex flex-wrap items-center gap-2">
          <RungMenu disabled={busy} onSetRung={onSetRung} />
          {!bot.auto && bot.pending_graduation ? (
            <Button
              size="sm"
              variant="primary"
              disabled={busy}
              onClick={() => {
                void onGraduate();
              }}
            >
              <GraduationCap className="h-3.5 w-3.5" /> Graduate to {nextTier ?? "FULL"}
            </Button>
          ) : null}
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-subtle">{bot.paused ? "Paused" : "Trading"}</span>
            <Toggle
              checked={!bot.paused}
              disabled={busy}
              label={bot.paused ? `Resume ${bot.strategy_name ?? bot.bot_id}` : `Pause ${bot.strategy_name ?? bot.bot_id}`}
              onChange={(value) => {
                void onPause(!value);
              }}
            />
          </div>
        </div>
      </div>
    </Card>
  );
}
