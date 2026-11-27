"use client";

import { useState } from "react";
import type { ReactNode } from "react";
import { Layers, Pause, Play, Radar, ShieldAlert } from "lucide-react";
import type { IncubationBot, Tier } from "@/lib/types";
import { useAlgoData } from "@/lib/data-provider";
import { useToast } from "@/components/providers/toast-provider";
import { PageHeader } from "@/components/ui/page-header";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { IncubationCard } from "@/components/incubation/incubation-card";
import { formatPercent } from "@/lib/format";

function Stat({
  label,
  value,
  hint,
  icon,
}: {
  label: string;
  value: string;
  hint: string;
  icon: ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-line bg-panel p-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[10px] font-medium uppercase tracking-[0.12em] text-faint">{label}</p>
        <span className="text-subtle">{icon}</span>
      </div>
      <p className="num mt-2 text-[26px] font-medium leading-none tracking-[-0.04em] text-ink">{value}</p>
      <p className="mt-2 text-[10px] leading-4 text-faint">{hint}</p>
    </div>
  );
}

export default function IncubationPage() {
  const { mode, data, actions } = useAlgoData();
  const { toast } = useToast();
  const [busyBot, setBusyBot] = useState<string | null>(null);

  const bots = data.bots;
  const risk = bots.reduce((sum, bot) => sum + bot.effective_risk_pct, 0);
  const pending = bots.filter((bot) => bot.pending_graduation).length;
  const frozen = bots.filter((bot) => bot.frozen_reason).length;
  const online = bots.filter((bot) => bot.pilot_state === "ONLINE").length;
  const live = bots.filter((bot) => !bot.paused).length;

  const run = async (
    bot: IncubationBot,
    action: () => Promise<void>,
    success: { title: string; message: string },
  ) => {
    setBusyBot(bot.bot_id);
    try {
      await action();
      toast({ ...success, tone: "emerald" });
    } catch (error) {
      toast({
        title: "Action failed",
        message: error instanceof Error ? error.message : "The incubation endpoint rejected the request.",
        tone: "rose",
      });
    } finally {
      setBusyBot(null);
    }
  };

  const handleAuto = (bot: IncubationBot, auto: boolean) =>
    run(bot, () => actions.setAuto(bot.bot_id, auto), {
      title: auto ? "Auto rung enabled" : "Manual rung enabled",
      message: auto
        ? `${bot.strategy_name ?? bot.bot_id} will graduate itself when every check passes.`
        : `${bot.strategy_name ?? bot.bot_id} waits for a manual graduation.`,
    });

  const handlePause = (bot: IncubationBot, paused: boolean) =>
    run(bot, () => actions.pauseBot(bot.bot_id, paused), {
      title: paused ? "Bot paused" : "Bot resumed",
      message: `${bot.strategy_name ?? bot.bot_id} is ${paused ? "paused" : "trading"} at ${formatPercent(bot.effective_risk_pct, 2)} risk.`,
    });

  const handleGraduate = (bot: IncubationBot) =>
    run(bot, () => actions.graduate(bot.bot_id), {
      title: "Graduation applied",
      message: `${bot.strategy_name ?? bot.bot_id} moved to the next rung.`,
    });

  const handleRung = (bot: IncubationBot, rung: Exclude<Tier, null>, reason: string) =>
    run(bot, () => actions.setRung(bot.bot_id, rung, reason), {
      title: `Rung set to ${rung}`,
      message: `${bot.strategy_name ?? bot.bot_id} is at ${Math.round((rung === "FULL" ? 1 : rung === "PROVING" ? 0.5 : 0.25) * 100)}% target risk.`,
    });

  return (
    <div>
      <PageHeader
        eyebrow="Live risk"
        title="Incubation ladder"
        description="Risk is earned on live trades. Each rung has to clear the eight checks before capital steps up."
        actions={
          <>
            <Badge tone="ink" dot className="h-7">
              {bots.length} bots
            </Badge>
            {pending > 0 ? (
              <Badge tone="amber" dot className="h-7">
                {pending} pending
              </Badge>
            ) : null}
          </>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat
          label="Risk deployed"
          value={formatPercent(risk, 2)}
          hint={`${live} of ${bots.length} bots trading · effective`}
          icon={<Radar className="h-3.5 w-3.5" />}
        />
        <Stat
          label="Pending"
          value={String(pending)}
          hint="Graduations waiting for a decision"
          icon={<Layers className="h-3.5 w-3.5" />}
        />
        <Stat
          label="Frozen"
          value={String(frozen)}
          hint="Loss, decay, silence, or pilot offline"
          icon={<ShieldAlert className="h-3.5 w-3.5" />}
        />
        <Stat
          label="Pilot online"
          value={`${online}/${bots.length}`}
          hint={mode === "demo" ? "Simulated heartbeat · 2 s" : "Bridge heartbeat"}
          icon={online === bots.length ? <Play className="h-3.5 w-3.5" /> : <Pause className="h-3.5 w-3.5" />}
        />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        {bots.map((bot) => (
          <IncubationCard
            key={bot.bot_id}
            bot={bot}
            busy={busyBot === bot.bot_id}
            onAuto={(auto) => handleAuto(bot, auto)}
            onPause={(paused) => handlePause(bot, paused)}
            onGraduate={() => handleGraduate(bot)}
            onSetRung={(rung, reason) => handleRung(bot, rung, reason)}
          />
        ))}
      </div>

      {bots.length === 0 ? (
        <EmptyState
          icon={<Layers className="h-4 w-4" />}
          title="No bots on the ladder"
          description="Promote a vault strategy into incubation to start earning risk."
          className="mt-4"
        />
      ) : null}

      <p className="mt-4 text-center text-[11px] leading-4 text-faint">
        10 healthy live trades earn the 50% rung · 30 earn 100%. The simulated path needs 5 live
        trades to leave 25%.
      </p>
    </div>
  );
}
