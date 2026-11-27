import type {
  AlgoSnapshot,
  Alert,
  CampaignDetail,
  CampaignStage,
  CampaignSummary,
  CheckId,
  EquityPoint,
  HealthWord,
  IncubationBot,
  PilotState,
  PortfolioDetail,
  Severity,
  Tier,
  VaultStrategy,
} from "./types";

const DEMO_SEED = 0x5eeda11;
const DEMO_EPOCH = Date.UTC(2026, 10, 27, 7, 0, 0);

type Rng = () => number;

function mulberry32(seed: number): Rng {
  let state = seed;
  return () => {
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function iso(offsetSeconds: number): string {
  return new Date(DEMO_EPOCH + offsetSeconds * 1000).toISOString();
}

const STRATEGY_NAMES = [
  "Aurora Drift",
  "Basin Reversal",
  "Cinder Break",
  "Dune Momentum",
  "Ember Pullback",
  "Fjord Trend",
  "Granite Range",
  "Harbor Mean",
  "Ion Breakout",
  "Juniper Swing",
  "Kestrel Momentum",
  "Lattice Session",
  "Meridian Cross",
  "North Gap",
  "Orbit Reversion",
  "Pinnacle Break",
  "Quarry Trend",
  "Ridge Filter",
  "Sable Session",
  "Tide Momentum",
  "Umber Range",
  "Vantage Pullback",
  "Willow Cross",
  "Zephyr Breakout",
] as const;

const SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "XAUUSD"] as const;
const TIMEFRAMES = ["M15", "H1", "H4", "D1"] as const;
const ARCHETYPES = ["trend", "mean-reversion", "breakout", "momentum", "session"] as const;

function buildVault(rng: Rng): VaultStrategy[] {
  return STRATEGY_NAMES.map((name, index) => {
    const persistence = Math.round(clamp(64 + rng() * 34, 55, 99));
    const recovery = Math.round(clamp(58 + rng() * 38, 50, 98));
    const sharpe = Math.round(clamp(62 + rng() * 34, 52, 99));
    const trades = Math.round(clamp(60 + rng() * 36, 50, 98));
    const maxDrawdown = Math.round(clamp(58 + rng() * 40, 50, 98));
    const profitFactor = Math.round(clamp(60 + rng() * 36, 50, 98));
    const isLinearity = Math.round(clamp(56 + rng() * 40, 45, 98));
    const robustness = Math.round(clamp(55 + rng() * 38, 45, 96));
    const score = Math.round(
      (persistence * 20 +
        recovery * 15 +
        sharpe * 15 +
        trades * 15 +
        maxDrawdown * 10 +
        profitFactor * 10 +
        isLinearity * 3 +
        robustness * 12) /
        100,
    );
    const oosSharpe = Number((1.05 + (sharpe / 100) * 1.85 + rng() * 0.2).toFixed(2));
    const maxDd = Number((2.8 + (100 - maxDrawdown) * 0.11 + rng() * 2).toFixed(1));
    const tradesCount = Math.round(18 + (trades / 100) * 72 + rng() * 10);
    const pf = Number((1.15 + (profitFactor / 100) * 1.2 + rng() * 0.08).toFixed(2));
    const health: HealthWord =
      index === 3 ? "WATCH" : index === 8 ? "EARLY" : index === 17 ? "DUPLICATE" : "OK";
    const strategyId = `st_${String(index + 1).padStart(3, "0")}_${name
      .toLowerCase()
      .replace(/[^a-z]+/g, "_")}`;
    return {
      strategy_id: strategyId,
      name,
      symbol: SYMBOLS[index % SYMBOLS.length],
      timeframe: TIMEFRAMES[(index * 3) % TIMEFRAMES.length],
      score,
      score_parts: {
        persistence,
        recovery,
        sharpe,
        trades,
        max_drawdown: maxDrawdown,
        profit_factor: profitFactor,
        is_linearity: isLinearity,
        robustness,
      },
      robustness_inferred: true,
      archetype: ARCHETYPES[(index * 7) % ARCHETYPES.length],
      oos: {
        trades: tradesCount,
        net: Math.round(900 + score * 54 + rng() * 900),
        sharpe: oosSharpe,
        pf,
        max_dd: maxDd,
        persistence: Number((persistence / 100).toFixed(2)),
      },
      parity_grade: index % 11 === 0 ? "C" : index % 4 === 0 ? "B" : "A",
      health,
      mq5_url: `/api/v1/vault/${strategyId}/export.mq5`,
      avg_corr: Number((0.06 + rng() * 0.48).toFixed(2)),
    };
  });
}

function buildEquity(rng: Rng, count = 64): EquityPoint[] {
  const points: EquityPoint[] = [];
  let equity = 98_420;
  for (let index = 0; index < count; index += 1) {
    const cycle = Math.sin(index / 7) * 110;
    equity += 70 + cycle * 0.2 + (rng() - 0.44) * 260;
    if (index === 21) equity -= 720;
    if (index === 47) equity += 510;
    points.push({
      equity: Math.round(equity * 100) / 100,
      balance: Math.round((equity - 140 - index * 1.8) * 100) / 100,
      ts: iso(index * 60),
    });
  }
  return points;
}

interface SeriesOptions {
  seed: number;
  total: number;
  completed: number;
  startBest: number;
  gain: number;
}

function buildGenerations({ seed, total, completed, startBest, gain }: SeriesOptions) {
  const rng = mulberry32(seed);
  return (["Consistency", "Growth"] as const).flatMap((tribe) => {
    const offset = tribe === "Growth" ? 2.4 : 0;
    return Array.from({ length: Math.min(completed, total) }, (_, index) => {
      const progress = total <= 1 ? 1 : index / (total - 1);
      const best = startBest + gain * (1 - Math.pow(1 - progress, 2.1)) + offset + rng() * 1.1;
      const mean = best - 8 - rng() * 6 - (1 - progress) * 4;
      return {
        tribe,
        generation: index + 1,
        best_fitness: Number(best.toFixed(2)),
        mean_fitness: Number(mean.toFixed(2)),
        survivors: 300 - Math.round(index * 2.1),
        elapsed_s: Math.round((index + 1) * 84),
      };
    });
  });
}

function campaignDetail(
  summary: CampaignSummary,
  generations: ReturnType<typeof buildGenerations>,
): CampaignDetail {
  return {
    ...summary,
    progress: {
      campaign_id: summary.campaign_id,
      tribe: "Consistency",
      generation: summary.generation,
      generations_total: summary.generations_total,
      best_fitness: summary.best_fitness,
      mean_fitness: Number((summary.best_fitness - 9.4).toFixed(2)),
      survivors: 268,
      stage: summary.stage,
      elapsed_s: summary.elapsed_s,
      eta_s: summary.eta_s,
    },
    generations,
    gates: {
      passed: summary.status === "done",
      rejected_by: summary.status === "done" ? { random_gate: 6, shuffle: 2, nudge: 3, trades: 1 } : {},
    },
  };
}

function buildCampaigns(): {
  summaries: CampaignSummary[];
  details: Record<string, CampaignDetail>;
} {
  const aurora: CampaignSummary = {
    campaign_id: "cmp_aurora",
    name: "Aurora H1 sweep",
    symbol: "EURUSD",
    timeframe: "H1",
    status: "running",
    generation: 12,
    generations_total: 20,
    best_fitness: 84.2,
    stage: "breeding",
    elapsed_s: 1684,
    eta_s: 1240,
    vaulted: 0,
  };
  const ironwood: CampaignSummary = {
    campaign_id: "cmp_ironwood",
    name: "Ironwood gold breakout",
    symbol: "XAUUSD",
    timeframe: "H4",
    status: "done",
    generation: 20,
    generations_total: 20,
    best_fitness: 91.4,
    stage: "done",
    elapsed_s: 5210,
    eta_s: 0,
    vaulted: 4,
  };
  const juniper: CampaignSummary = {
    campaign_id: "cmp_juniper",
    name: "Juniper GBP mean reversion",
    symbol: "GBPUSD",
    timeframe: "M15",
    status: "queued",
    generation: 0,
    generations_total: 20,
    best_fitness: 0,
    stage: "init",
    elapsed_s: 0,
    eta_s: null,
    vaulted: 0,
  };
  const summaries = [aurora, ironwood, juniper];
  const details: Record<string, CampaignDetail> = {
    [aurora.campaign_id]: campaignDetail(
      aurora,
      buildGenerations({ seed: 41, total: 20, completed: 12, startBest: 58, gain: 27 }),
    ),
    [ironwood.campaign_id]: campaignDetail(
      ironwood,
      buildGenerations({ seed: 87, total: 20, completed: 20, startBest: 55, gain: 37 }),
    ),
    [juniper.campaign_id]: campaignDetail(juniper, []),
  };
  return { summaries, details };
}

function check(
  id: CheckId,
  label: string,
  pass: boolean,
  value: string | number | null,
  text: string,
) {
  return { id, label, pass, value, text };
}

function buildBots(vault: VaultStrategy[]): IncubationBot[] {
  const strategy = (index: number) => vault[index];
  const checksFor = (
    healthy: number,
    liveNetR: number,
    health: HealthWord,
    frozen: IncubationBot["frozen_reason"],
    silent = false,
  ) => [
    check("enough_live_trades", "Enough live trades", healthy >= 10, healthy, `${healthy} healthy`),
    check("time_in_incubation", "Time in incubation", true, "—", "Informational only"),
    check("simulated_record", "Simulated record", healthy >= 5, healthy, healthy >= 5 ? "Pass" : "Held"),
    check("making_money", "Making money", liveNetR > 0, liveNetR, `${liveNetR.toFixed(1)}R`),
    check("no_decay_warning", "No decay warning", frozen !== "DECAY", frozen ?? "none", frozen ?? "Clear"),
    check("health_word", "Health word", health === "OK" || health === "EARLY", health, health),
    check("trading_normally", "Trading normally", !silent, silent ? "EA_SILENT" : "normal", silent ? "Held" : "Pass"),
    check("no_bad_streak", "No bad streak", liveNetR > -1, liveNetR > -1 ? "0" : "5+", liveNetR > -1 ? "Clear" : "Held"),
  ];

  return [
    {
      bot_id: "bt_aurora",
      strategy_id: strategy(0).strategy_id,
      strategy_name: strategy(0).name,
      symbol: "EURUSD",
      magic: 900001,
      tier: "PROVING" as Tier,
      multiplier: 0.5,
      target_risk_pct: 0.5,
      effective_risk_pct: 0.25,
      auto: true,
      paused: false,
      frozen_reason: null,
      health_word: "OK",
      pending_graduation: false,
      live_trades: 18,
      healthy_live_trades: 17,
      sim_healthy_trades: 12,
      live_net_r: 6.4,
      checks: checksFor(17, 6.4, "OK", null),
      pilot_state: "ONLINE" as PilotState,
      updated_at: iso(-42),
    },
    {
      bot_id: "bt_basin",
      strategy_id: strategy(1).strategy_id,
      strategy_name: strategy(1).name,
      symbol: "GBPUSD",
      magic: 900002,
      tier: "INCUBATION" as Tier,
      multiplier: 0.25,
      target_risk_pct: 0.4,
      effective_risk_pct: 0.1,
      auto: true,
      paused: false,
      frozen_reason: null,
      health_word: "EARLY",
      pending_graduation: false,
      live_trades: 4,
      healthy_live_trades: 4,
      sim_healthy_trades: 0,
      live_net_r: 1.1,
      checks: checksFor(4, 1.1, "EARLY", null),
      pilot_state: "ONLINE" as PilotState,
      updated_at: iso(-95),
    },
    {
      bot_id: "bt_cinder",
      strategy_id: strategy(2).strategy_id,
      strategy_name: strategy(2).name,
      symbol: "XAUUSD",
      magic: 900003,
      tier: "FULL" as Tier,
      multiplier: 1,
      target_risk_pct: 0.75,
      effective_risk_pct: 0.75,
      auto: true,
      paused: false,
      frozen_reason: "DECAY",
      health_word: "WATCH",
      pending_graduation: false,
      live_trades: 44,
      healthy_live_trades: 31,
      sim_healthy_trades: 18,
      live_net_r: -1.8,
      checks: checksFor(31, -1.8, "WATCH", "DECAY"),
      pilot_state: "ONLINE" as PilotState,
      updated_at: iso(-14),
    },
    {
      bot_id: "bt_dune",
      strategy_id: strategy(3).strategy_id,
      strategy_name: strategy(3).name,
      symbol: "USDJPY",
      magic: 900004,
      tier: "PROVING" as Tier,
      multiplier: 0.5,
      target_risk_pct: 0.5,
      effective_risk_pct: 0.25,
      auto: false,
      paused: false,
      frozen_reason: null,
      health_word: "OK",
      pending_graduation: true,
      live_trades: 31,
      healthy_live_trades: 30,
      sim_healthy_trades: 16,
      live_net_r: 8.2,
      checks: checksFor(30, 8.2, "OK", null),
      pilot_state: "ONLINE" as PilotState,
      updated_at: iso(-31),
    },
    {
      bot_id: "bt_ember",
      strategy_id: strategy(4).strategy_id,
      strategy_name: strategy(4).name,
      symbol: "AUDUSD",
      magic: 900005,
      tier: "INCUBATION" as Tier,
      multiplier: 0.25,
      target_risk_pct: 0.4,
      effective_risk_pct: 0.1,
      auto: true,
      paused: false,
      frozen_reason: "SILENCE",
      health_word: "EARLY",
      pending_graduation: false,
      live_trades: 6,
      healthy_live_trades: 5,
      sim_healthy_trades: 0,
      live_net_r: 0.8,
      checks: checksFor(5, 0.8, "EARLY", "SILENCE", true),
      pilot_state: "EA_SILENT" as PilotState,
      updated_at: iso(-130),
    },
  ];
}

function buildAlerts(): Alert[] {
  return [
    {
      id: "al_decay_cinder",
      bot_id: "bt_cinder",
      kind: "decay",
      severity: "high" as Severity,
      message: "Live drawdown is 2.3× backtest max. Rung held by DECAY.",
      value: 2.3,
      threshold: 2,
      created_at: iso(-1860),
      resolved_at: null,
    },
    {
      id: "al_silence_ember",
      bot_id: "bt_ember",
      kind: "silence",
      severity: "medium" as Severity,
      message: "Only 2 trades in 30 days; below the expected frequency.",
      value: 2,
      threshold: 7,
      created_at: iso(-920),
      resolved_at: null,
    },
    {
      id: "al_grad_dune",
      bot_id: "bt_dune",
      kind: "graduation",
      severity: "low" as Severity,
      message: "30 healthy live trades: FULL rung is ready for manual graduation.",
      value: 30,
      threshold: 30,
      created_at: iso(-64),
      resolved_at: null,
    },
  ];
}

function buildPortfolios(vault: VaultStrategy[], bots: IncubationBot[]): PortfolioDetail[] {
  const members = bots.slice(0, 5).map((bot, index) => ({
    strategy_id: bot.strategy_id,
    symbol: bot.symbol ?? "EURUSD",
    risk_pct: bot.effective_risk_pct,
    scale: 1,
    avg_corr: vault[index]?.avg_corr ?? 0.2,
    bot_id: bot.bot_id,
  }));
  const labels = members.map((member) => member.symbol);
  return [
    {
      portfolio_id: "pf_core",
      name: "Core ladder",
      target_heat_pct: 2.5,
      symbol_lock: true,
      sizing_mode: "decorrelated",
      heat: 2.5,
      members,
      correlation_matrix: {
        labels,
        matrix: labels.map((_, row) =>
          labels.map((__, column) => (row === column ? 1 : 0.12 + ((row + column) % 5) * 0.05)),
        ),
      },
      health: {
        distinct_symbols: new Set(labels).size,
        max_symbol_exposure: 0.75,
        avg_member_corr: 0.24,
      },
    },
    {
      portfolio_id: "pf_satellite",
      name: "Satellite basket",
      target_heat_pct: 1.5,
      symbol_lock: false,
      sizing_mode: "heat",
      heat: 1.25,
      members: members.slice(2),
      correlation_matrix: {
        labels: labels.slice(2),
        matrix: labels.slice(2).map((_, row) =>
          labels
            .slice(2)
            .map((__, column) => (row === column ? 1 : 0.2 + ((row + column) % 4) * 0.06)),
        ),
      },
      health: {
        distinct_symbols: new Set(labels.slice(2)).size,
        max_symbol_exposure: 0.5,
        avg_member_corr: 0.31,
      },
    },
  ];
}

export function buildDemoSnapshot(): AlgoSnapshot {
  const rng = mulberry32(DEMO_SEED);
  const vault = buildVault(rng);
  const bots = buildBots(vault);
  const { summaries, details } = buildCampaigns();
  const alerts = buildAlerts();
  const pilot = {
    online: true,
    last_heartbeat_at: iso(-2),
    chart: { symbol: "EURUSD", period_minutes: 60, chart_id: 1325417983171 },
    account: { login: 51820473, server: "AlgoRE-Demo" },
    bots: bots.map((bot) => ({
      bot_id: bot.bot_id,
      state: bot.pilot_state === "EA_SILENT" ? "EA_SILENT" : "ONLINE",
    })),
    silent_bots: ["bt_ember"],
  };

  return {
    health: {
      status: "ok",
      version: "demo-1.0",
      time: iso(0),
      db: "ok",
      campaigns_active: 1,
      pilot_online: true,
      bots: bots.length,
    },
    equity: buildEquity(rng),
    campaigns: summaries,
    campaignDetails: details,
    vault,
    bots,
    alerts,
    pilot,
    portfolios: buildPortfolios(vault, bots),
  };
}

function nextCampaign(snapshot: AlgoSnapshot): AlgoSnapshot {
  const running = snapshot.campaigns.find((campaign) => campaign.status === "running");
  if (!running || running.generation >= running.generations_total) {
    return snapshot;
  }

  const nextGeneration = Math.min(running.generations_total, running.generation + 1);
  const rng = mulberry32(DEMO_SEED + nextGeneration * 17);
  const best = Number(
    (running.best_fitness + (running.generations_total - nextGeneration) * 0.11 + rng() * 0.4).toFixed(2),
  );
  const stage: CampaignStage =
    nextGeneration >= running.generations_total
      ? "done"
      : nextGeneration >= running.generations_total - 2
        ? "gates"
        : nextGeneration >= running.generations_total - 5
          ? "final_war"
          : "breeding";
  const finished = stage === "done";
  const summary: CampaignSummary = {
    ...running,
    generation: nextGeneration,
    best_fitness: best,
    stage,
    elapsed_s: running.elapsed_s + 82,
    eta_s: finished ? 0 : Math.max(0, Math.round((running.generations_total - nextGeneration) * 84)),
    status: finished ? "done" : "running",
    vaulted: finished ? 3 : running.vaulted,
  };
  const previous = snapshot.campaignDetails[summary.campaign_id];
  const point = {
    tribe: "Consistency",
    generation: nextGeneration,
    best_fitness: best,
    mean_fitness: Number((best - 9.2).toFixed(2)),
    survivors: 268,
    elapsed_s: summary.elapsed_s,
  };
  const detail: CampaignDetail = {
    ...(previous ?? summary),
    ...summary,
    progress: {
      campaign_id: summary.campaign_id,
      tribe: "Consistency",
      generation: nextGeneration,
      generations_total: summary.generations_total,
      best_fitness: best,
      mean_fitness: point.mean_fitness,
      survivors: 268,
      stage,
      elapsed_s: summary.elapsed_s,
      eta_s: summary.eta_s,
    },
    generations: [...(previous?.generations ?? []), point],
    gates: previous?.gates ?? { passed: false, rejected_by: {} },
  };
  return {
    ...snapshot,
    campaigns: snapshot.campaigns.map((campaign) =>
      campaign.campaign_id === summary.campaign_id ? summary : campaign,
    ),
    campaignDetails: {
      ...snapshot.campaignDetails,
      [summary.campaign_id]: detail,
    },
  };
}

export function advanceDemoSnapshot(snapshot: AlgoSnapshot, tick: number): AlgoSnapshot {
  if (tick % 2 === 0 && snapshot.pilot) {
    snapshot = {
      ...snapshot,
      pilot: {
        ...snapshot.pilot,
        last_heartbeat_at: new Date().toISOString(),
      },
    };
  }

  const last = snapshot.equity[snapshot.equity.length - 1];
  if (last) {
    const rng = mulberry32(DEMO_SEED + tick * 131);
    const drift = 12 + Math.sin(tick / 9) * 34;
    const equity = Math.round((last.equity + drift + (rng() - 0.47) * 78) * 100) / 100;
    snapshot = {
      ...snapshot,
      equity: [...snapshot.equity.slice(-89), {
        equity,
        balance: Math.round((equity - 142) * 100) / 100,
        ts: new Date().toISOString(),
      }],
    };
  }

  if (tick > 0 && tick % 6 === 0) {
    snapshot = nextCampaign(snapshot);
  }

  return snapshot;
}

export function createDemoCampaign(
  snapshot: AlgoSnapshot,
  input: {
    name: string;
    symbol: string;
    timeframe: string;
    generations?: number;
    population?: number;
    seed?: number;
  },
): { snapshot: AlgoSnapshot; campaignId: string } {
  const id = `cmp_${input.name.toLowerCase().replace(/[^a-z0-9]+/g, "_").slice(0, 24) || "run"}_${Date.now().toString(36)}`;
  const summary: CampaignSummary = {
    campaign_id: id,
    name: input.name,
    symbol: input.symbol,
    timeframe: input.timeframe,
    status: "queued",
    generation: 0,
    generations_total: input.generations ?? 20,
    best_fitness: 0,
    stage: "init",
    elapsed_s: 0,
    eta_s: null,
    vaulted: 0,
  };
  const detail: CampaignDetail = {
    ...summary,
    generations: [],
    gates: { passed: false, rejected_by: {} },
  };
  return {
    campaignId: id,
    snapshot: {
      ...snapshot,
      campaigns: [summary, ...snapshot.campaigns],
      campaignDetails: { ...snapshot.campaignDetails, [id]: detail },
      health: snapshot.health
        ? { ...snapshot.health, campaigns_active: snapshot.health.campaigns_active + 1 }
        : null,
    },
  };
}

export function demoMq5(strategy: VaultStrategy): string {
  return `//+------------------------------------------------------------------+
//| AlgoRE demo export — ${strategy.name}
//| This is a placeholder generated in demo mode. It is not a compiled
//| strategy and must not be attached to a live MetaTrader 5 chart.
//+------------------------------------------------------------------+
#property copyright "AlgoRE demo"
#property version   "1.00"
#property strict

input long   InpMagic       = 900001;
input double InpRiskPercent = ${strategy.oos.trades ? 0.5 : 0.25};

int OnInit()
  {
   Print("AlgoRE demo export: ${strategy.name} (${strategy.symbol} ${strategy.timeframe})");
   Print("OOS Sharpe ${strategy.oos.sharpe.toFixed(2)} | Max DD ${strategy.oos.max_dd.toFixed(1)}% | Score ${strategy.score}");
   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason) { }

void OnTick()
  {
   // Demo placeholder. Connect NEXT_PUBLIC_API_URL to download the real EA.
  }
//+------------------------------------------------------------------+
`;
}
