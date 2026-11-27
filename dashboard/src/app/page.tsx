"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import {
  Activity,
  BellRing,
  ChevronRight,
  Gauge,
  Pause,
  Play,
  Radio,
  Wallet,
} from "lucide-react";
import type { Alert, IncubationBot } from "@/lib/types";
import { useAlgoData } from "@/lib/data-provider";
import { useToast } from "@/components/providers/toast-provider";
import { PageHeader } from "@/components/ui/page-header";
import { Card, CardHeader } from "@/components/ui/card";
import { Badge, Dot } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sparkline } from "@/components/ui/sparkline";
import { ConfirmSheet } from "@/components/ui/confirm-sheet";
import { EmptyState } from "@/components/ui/empty-state";
import {
  formatCompactUsd,
  formatPercent,
  formatSigned,
  formatTime,
  formatUsd,
} from "@/lib/format";
import { cn } from "@/lib/cn";

function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  accent = "default",
}: {
  label: string;
  value: string;
  hint: string;
  icon: typeof Wallet;
  accent?: "emerald" | "amber" | "default";
}) {
  return (
    <Card className="p-4 sm:p-5">
      <div className="flex items-start justify-between gap-3">
        <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-subtle">{label}</p>
        <Icon
          className={cn(
            "h-4 w-4",
            accent === "emerald" && "text-emerald",
            accent === "amber" && "text-amber",
            accent === "default" && "text-faint",
          )}
          strokeWidth={1.8}
        />
      </div>
      <p className="num mt-3 text-[26px] font-medium leading-none tracking-[-0.04em] text-ink">
        {value}
      </p>
      <p className="mt-2 text-[12px] leading-4 text-subtle">{hint}</p>
    </Card>
  );
}

function MiniRungs({ bot }: { bot: IncubationBot }) {
  return (
    <span className="flex w-[54px] shrink-0 items-center gap-1" aria-hidden="true">
      {[0.25, 0.5, 1].map((rung) => (
        <span
          key={rung}
          className={cn(
            "h-1.5 flex-1 rounded-full",
            bot.multiplier + 0.001 >= rung
              ? bot.frozen_reason
                ? "bg-amber"
                : "bg-emerald"
              : "bg-white/[0.08]",
          )}
        />
      ))}
    </span>
  );
}

function BotRow({ bot }: { bot: IncubationBot }) {
  return (
    <Link
      href="/incubation"
      className="group flex min-h-[56px] items-center gap-3 border-t border-line py-2.5 first:border-t-0"
    >
      <MiniRungs bot={bot} />
      <div className="min-w-0 flex-1">
        <p className="truncate text-[13px] font-medium text-ink">
          {bot.strategy_name ?? bot.bot_id}
        </p>
        <p className="mt-0.5 text-[11px] text-subtle">
          {bot.symbol ?? "—"} · {bot.tier ?? "NO TIER"}
          {bot.paused ? " · paused" : ""}
        </p>
      </div>
      <span className="num text-[13px] text-ink/90">
        {formatPercent(bot.effective_risk_pct, 2)}
      </span>
      <Dot
        tone={
          bot.health_word === "OK"
            ? "emerald"
            : bot.health_word === "REPLACE"
              ? "rose"
              : "amber"
        }
      />
      <ChevronRight className="h-4 w-4 text-faint transition group-hover:text-muted" />
    </Link>
  );
}

function AlertRow({ alert }: { alert: Alert }) {
  return (
    <div className="flex gap-3 border-t border-line py-3 first:border-t-0">
      <span className="mt-1.5">
        <Dot tone={alert.severity === "low" ? "emerald" : "amber"} />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[13px] leading-5 text-ink/90">{alert.message}</p>
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-subtle">
          <span className="capitalize">{alert.kind}</span>
          <span className="text-faint">·</span>
          <span>{alert.bot_id ?? "system"}</span>
          <span className="text-faint">·</span>
          <span>{formatTime(alert.created_at)} UTC</span>
        </div>
      </div>
    </div>
  );
}

export default function OverviewPage() {
  const { mode, data, actions } = useAlgoData();
  const { toast } = useToast();
  const [confirm, setConfirm] = useState<"pause" | "resume" | null>(null);
  const [busy, setBusy] = useState(false);

  const stats = useMemo(() => {
    const equity = data.equity[data.equity.length - 1]?.equity ?? 0;
    const start = data.equity[0]?.equity ?? equity;
    const pnl = equity - start;
    const pnlPct = start ? (pnl / start) * 100 : 0;
    const peak = data.equity.reduce((max, point) => Math.max(max, point.equity), equity);
    const drawdown = peak ? ((peak - equity) / peak) * 100 : 0;
    const activeBots = data.bots.filter((bot) => !bot.paused).length;
    const risk = data.bots.reduce(
      (sum, bot) => sum + (bot.paused ? 0 : bot.effective_risk_pct),
      0,
    );
    return { equity, pnl, pnlPct, peak, drawdown, activeBots, risk };
  }, [data.bots, data.equity]);

  const allPaused = data.bots.length > 0 && data.bots.every((bot) => bot.paused);
  const pilot = data.pilot;
  const alerts = data.alerts.filter((alert) => !alert.resolved_at);

  const handleConfirm = async () => {
    if (!confirm) {
      return;
    }
    setBusy(true);
    try {
      await actions.pauseAll(confirm === "pause", confirm === "pause" ? "emergency pause" : "resume");
      toast({
        title: confirm === "pause" ? "All bots paused" : "All bots resumed",
        message:
          confirm === "pause"
            ? "Emergency Pause is active. New entries are blocked; open positions are untouched."
            : "New entries are allowed again at each bot's current rung.",
        tone: confirm === "pause" ? "amber" : "emerald",
      });
      setConfirm(null);
    } catch (error) {
      toast({
        title: "Action failed",
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
        eyebrow="Command"
        title="Overview"
        description="One read on the book: equity at risk, the pilot bridge, and every bot on the ladder."
        actions={
          <Badge tone="ink" dot className="h-7">
            {mode === "demo" ? "live simulation" : "live feed"}
          </Badge>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 lg:gap-4">
        <StatCard
          label="Equity"
          value={stats.equity ? formatCompactUsd(stats.equity) : "—"}
          hint={
            stats.equity
              ? `${formatSigned(stats.pnlPct, 2)} · ${formatUsd(stats.pnl, true)} session`
              : "Waiting for the first tick"
          }
          icon={Wallet}
          accent={stats.pnl >= 0 ? "emerald" : "amber"}
        />
        <StatCard
          label="Risk deployed"
          value={formatPercent(stats.risk, 2)}
          hint={`${stats.activeBots} of ${data.bots.length} bots live`}
          icon={Gauge}
        />
        <StatCard
          label="Pilot bridge"
          value={pilot?.online ? "Online" : "Offline"}
          hint={
            pilot?.chart
              ? `${pilot.chart.symbol} · ${pilot.chart.period_minutes}m chart`
              : "No chart attached"
          }
          icon={Radio}
          accent={pilot?.online ? "emerald" : "amber"}
        />
        <StatCard
          label="Active alerts"
          value={String(alerts.length)}
          hint={alerts[0] ? `highest: ${alerts[0].severity}` : "nothing open"}
          icon={BellRing}
          accent={alerts.length ? "amber" : "default"}
        />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card className="p-4 sm:p-5 lg:col-span-2">
          <CardHeader
            title="Equity curve"
            hint="Session equity, marked to market"
            action={<Badge tone={mode === "demo" ? "amber" : "emerald"} dot>{mode === "demo" ? "simulated" : "live"}</Badge>}
          />
          <div className="mt-4 flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="num text-[34px] font-medium leading-none tracking-[-0.045em] text-ink sm:text-[40px]">
                {stats.equity ? formatUsd(stats.equity, true) : "—"}
              </p>
              <p className={cn("num mt-2 text-[12px]", stats.pnl >= 0 ? "text-emerald" : "text-rose")}>
                {formatSigned(stats.pnl, 2, "")} USD · {formatSigned(stats.pnlPct, 2)} session
              </p>
            </div>
            <div className="flex gap-5">
              <div>
                <p className="text-[10px] uppercase tracking-[0.14em] text-faint">Peak</p>
                <p className="num mt-1 text-[12px] text-muted">
                  {stats.peak ? formatCompactUsd(stats.peak) : "—"}
                </p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-[0.14em] text-faint">Drawdown</p>
                <p className="num mt-1 text-[12px] text-muted">{formatPercent(stats.drawdown, 2)}</p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-[0.14em] text-faint">Last tick</p>
                <p className="num mt-1 text-[12px] text-muted">
                  {formatTime(data.equity[data.equity.length - 1]?.ts)} UTC
                </p>
              </div>
            </div>
          </div>
          <div className="mt-3">
            {data.equity.length > 1 ? (
              <Sparkline points={data.equity} />
            ) : (
              <EmptyState
                icon={<Activity className="h-4 w-4" />}
                title="No equity ticks yet"
                description="The pilot bridge will stream equity as soon as the account is connected."
              />
            )}
          </div>
        </Card>

        <Card className="flex flex-col p-4 sm:p-5">
          <CardHeader
            title="Emergency control"
            hint="One flag for every bot"
            action={
              <Badge tone={allPaused ? "amber" : "emerald"} dot>
                {allPaused ? "paused" : "armed"}
              </Badge>
            }
          />
          <div className="mt-4 rounded-xl border border-line bg-canvas/40 p-4">
            <div className="flex items-center justify-between gap-3">
              <span className="text-[12px] text-muted">Pilot connection</span>
              <Dot tone={pilot?.online ? "emerald" : "amber"} pulse={pilot?.online} />
            </div>
            <p className="mt-2 text-[20px] font-medium tracking-[-0.03em] text-ink">
              {pilot?.online ? "Bridge online" : "Bridge offline"}
            </p>
            <p className="mt-1 text-[11px] leading-4 text-subtle">
              Last heartbeat {formatTime(pilot?.last_heartbeat_at)} UTC
              {pilot?.account ? ` · ${pilot.account.login}` : ""}
            </p>
          </div>
          <div className="mt-3 rounded-xl border border-line bg-canvas/40 p-4">
            <div className="flex items-center justify-between gap-3">
              <span className="text-[12px] text-muted">Deployment</span>
              <span className="num text-[12px] text-ink">{formatPercent(stats.risk, 2)}</span>
            </div>
            <p className="mt-2 text-[13px] leading-5 text-muted">
              {allPaused
                ? "All bots are paused. No new entries will open."
                : `${stats.activeBots} bots can open new trades at their current rung.`}
            </p>
          </div>
          <div className="mt-auto pt-4">
            <Button
              variant={allPaused ? "primary" : "amber"}
              className="h-12 w-full"
              onClick={() => setConfirm(allPaused ? "resume" : "pause")}
              disabled={busy || data.bots.length === 0}
            >
              {allPaused ? <Play className="h-4 w-4" /> : <Pause className="h-4 w-4" />}
              {allPaused ? "Resume all bots" : "Pause all bots"}
            </Button>
            <p className="mt-2 text-center text-[11px] leading-4 text-subtle">
              Applies to the next entry only. Open positions are never touched.
            </p>
          </div>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card className="p-4 sm:p-5">
          <CardHeader
            title="Live book"
            hint={`${data.bots.length} bots · ${data.bots.filter((bot) => bot.pending_graduation).length} pending graduation`}
            action={
              <Link
                href="/incubation"
                className="flex min-h-9 items-center gap-1 rounded-lg px-2 text-[11px] font-medium text-muted transition hover:bg-white/[0.04] hover:text-ink"
              >
                Ladder <ChevronRight className="h-3.5 w-3.5" />
              </Link>
            }
          />
          <div className="mt-2">
            {data.bots.length ? (
              data.bots.slice(0, 5).map((bot) => <BotRow key={bot.bot_id} bot={bot} />)
            ) : (
              <EmptyState
                icon={<Activity className="h-4 w-4" />}
                title="No bots deployed"
                description="Deploy a vault strategy to open the first incubation rung."
              />
            )}
          </div>
        </Card>

        <Card className="p-4 sm:p-5">
          <CardHeader
            title="Active alerts"
            hint="Decay, silence, loss and ladder events"
            action={<Badge tone={alerts.length ? "amber" : "neutral"}>{alerts.length} open</Badge>}
          />
          <div className="mt-2">
            {alerts.length ? (
              alerts.slice(0, 5).map((alert) => <AlertRow key={alert.id} alert={alert} />)
            ) : (
              <EmptyState
                icon={<BellRing className="h-4 w-4" />}
                title="No active alerts"
                description="The book is quiet. New decay, silence and pilot events land here."
              />
            )}
          </div>
        </Card>
      </div>

      <ConfirmSheet
        open={confirm !== null}
        onClose={() => setConfirm(null)}
        onConfirm={() => {
          void handleConfirm();
        }}
        tone={confirm === "resume" ? "emerald" : "amber"}
        title={confirm === "resume" ? "Resume every bot?" : "Pause every bot?"}
        description={
          confirm === "resume"
            ? "This clears the pause flag for every bot. Each bot can open new trades at its current rung."
            : "This sets paused=true for every bot. Each EA stops opening new trades; open positions keep their stops and targets."
        }
        confirmLabel={confirm === "resume" ? "Resume all bots" : "Pause all bots"}
      />
    </div>
  );
}
