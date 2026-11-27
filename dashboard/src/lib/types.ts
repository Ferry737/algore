export type Mode = "demo" | "live";

export const HEALTH_WORDS = ["OK", "EARLY", "WATCH", "REPLACE", "DUPLICATE"] as const;
export type HealthWord = (typeof HEALTH_WORDS)[number];

export const FROZEN_REASONS = ["LOSS", "DECAY", "SILENCE", "PILOT_OFFLINE"] as const;
export type FrozenReason = (typeof FROZEN_REASONS)[number];

export const TIERS = ["INCUBATION", "PROVING", "FULL"] as const;
export type Tier = (typeof TIERS)[number];

export const PILOT_STATES = ["ONLINE", "EA_SILENT", "PILOT_OFFLINE"] as const;
export type PilotState = (typeof PILOT_STATES)[number];

export const CAMPAIGN_STAGES = [
  "init",
  "breeding",
  "final_war",
  "gates",
  "done",
] as const;
export type CampaignStage = (typeof CAMPAIGN_STAGES)[number];

export type CampaignStatus = "queued" | "running" | "done" | "failed" | "stopped";

export const CHECK_IDS = [
  "enough_live_trades",
  "time_in_incubation",
  "simulated_record",
  "making_money",
  "no_decay_warning",
  "health_word",
  "trading_normally",
  "no_bad_streak",
] as const;
export type CheckId = (typeof CHECK_IDS)[number];

export interface HealthResponse {
  status: string;
  version: string;
  time: string;
  db: string;
  campaigns_active: number;
  pilot_online: boolean;
  bots: number;
}

export interface TokenResponse {
  access_token: string;
  token_type: "Bearer";
  expires_in: number;
}

export interface GenerationPoint {
  tribe: string;
  generation: number;
  best_fitness: number;
  mean_fitness: number;
  survivors?: number;
  elapsed_s?: number;
}

export interface CampaignProgress {
  campaign_id: string;
  tribe: string;
  generation: number;
  generations_total: number;
  best_fitness: number;
  mean_fitness: number;
  survivors: number;
  stage: CampaignStage;
  elapsed_s: number;
  eta_s: number | null;
}

export interface CampaignSummary {
  campaign_id: string;
  name: string;
  symbol: string;
  timeframe: string;
  status: CampaignStatus;
  generation: number;
  generations_total: number;
  best_fitness: number;
  stage: CampaignStage;
  elapsed_s: number;
  eta_s: number | null;
  vaulted: number;
}

export interface CampaignGates {
  passed: boolean;
  rejected_by: Record<string, number>;
}

export interface CampaignDetail extends CampaignSummary {
  progress?: CampaignProgress;
  generations: GenerationPoint[];
  gates: CampaignGates;
}

export interface CampaignCreateInput {
  name: string;
  symbol: string;
  timeframe: string;
  generations?: number;
  population?: number;
  breed_pop?: number;
  seed?: number;
  tribes?: string[];
}

export interface ScorePart {
  key: string;
  value: number;
  weight?: number;
}

export interface ScoreParts {
  persistence: number;
  recovery: number;
  sharpe: number;
  trades: number;
  max_drawdown: number;
  profit_factor: number;
  is_linearity: number;
  robustness: number;
}

export interface VaultOos {
  trades: number;
  net: number;
  sharpe: number;
  pf: number;
  max_dd: number;
  persistence: number;
}

export interface VaultStrategy {
  strategy_id: string;
  name: string;
  symbol: string;
  timeframe: string;
  score: number;
  score_parts: ScoreParts | ScorePart[] | Record<string, number>;
  robustness_inferred?: boolean;
  archetype: string;
  oos: VaultOos;
  parity_grade: string;
  health: HealthWord;
  mq5_url?: string;
  avg_corr?: number;
}

export interface VaultEquityPoint {
  ts: number;
  equity: number;
  oos: boolean;
}

export interface ParityTest {
  mt5_net_return: number;
  engine_net_return: number;
  grade: string;
  tested_at: string;
}

export interface Reassessment {
  verdict: "HOLDING" | "WEAKENING" | "REPLACE" | "TOO_EARLY";
  trades_since: number;
  score_delta: number;
  expectancy: number;
  checked_at: string;
}

export interface VaultPassport {
  strategy_id: string;
  name: string;
  symbol: string;
  timeframe: string;
  genome: unknown;
  metrics: {
    is: Record<string, number>;
    oos: Record<string, number>;
  };
  equity: VaultEquityPoint[];
  parity_tests: ParityTest[];
  reassessments: Reassessment[];
}

export interface IncubationCheck {
  id: CheckId | string;
  label: string;
  pass: boolean;
  value: string | number | null;
  text: string;
}

export interface IncubationBot {
  bot_id: string;
  strategy_id: string;
  strategy_name?: string;
  symbol?: string;
  magic?: number;
  tier: Tier | null;
  multiplier: number;
  target_risk_pct: number;
  effective_risk_pct: number;
  auto: boolean;
  paused: boolean;
  frozen_reason: FrozenReason | null;
  health_word: HealthWord;
  pending_graduation: boolean;
  live_trades: number;
  healthy_live_trades: number;
  sim_healthy_trades: number;
  live_net_r: number;
  checks: IncubationCheck[];
  pilot_state: PilotState;
  updated_at: string;
}

export type Severity = "info" | "low" | "medium" | "high" | "critical";

export interface Alert {
  id: string;
  bot_id: string | null;
  kind: string;
  severity: Severity;
  message: string;
  value: number | null;
  threshold: number | null;
  created_at: string;
  resolved_at: string | null;
}

export interface EquityPoint {
  account_login?: number;
  equity: number;
  balance?: number;
  ts: string;
}

export interface PilotBotState {
  bot_id: string;
  state: string;
}

export interface PilotStatus {
  online: boolean;
  last_heartbeat_at: string | null;
  chart: {
    symbol: string;
    period_minutes: number;
    chart_id?: number;
  } | null;
  account: {
    login: number;
    server: string;
  } | null;
  bots: PilotBotState[];
  silent_bots: string[];
}

export interface PilotTrade {
  ticket: number;
  position_id?: number;
  bot_id?: string;
  symbol?: string;
  direction?: "buy" | "sell";
  lots?: number;
  open_time?: string;
  close_time?: string;
  open_price?: number;
  close_price?: number;
  profit?: number;
  commission?: number;
  swap?: number;
  sl?: number;
  tp?: number;
  reason?: string;
  r_multiple?: number;
  healthy?: boolean;
  equity_after?: number;
}

export interface PortfolioMember {
  strategy_id: string;
  symbol: string;
  risk_pct: number;
  scale: number;
  avg_corr: number;
  bot_id: string;
}

export interface PortfolioHealth {
  distinct_symbols: number;
  max_symbol_exposure: number;
  avg_member_corr: number;
}

export interface PortfolioDetail {
  portfolio_id: string;
  name: string;
  target_heat_pct: number;
  symbol_lock: boolean;
  sizing_mode: "heat" | "decorrelated";
  heat: number;
  members: PortfolioMember[];
  correlation_matrix: {
    labels: string[];
    matrix: number[][];
  };
  health: PortfolioHealth;
}

export interface AlgoSnapshot {
  health: HealthResponse | null;
  equity: EquityPoint[];
  campaigns: CampaignSummary[];
  campaignDetails: Record<string, CampaignDetail>;
  vault: VaultStrategy[];
  bots: IncubationBot[];
  alerts: Alert[];
  pilot: PilotStatus | null;
  portfolios: PortfolioDetail[];
}

export interface CampaignProgressData {
  campaign_id: string;
  tribe: string;
  generation: number;
  generations_total: number;
  best_fitness: number;
  mean_fitness: number;
  survivors: number;
  stage: CampaignStage;
  elapsed_s: number;
  eta_s: number | null;
}

export interface CampaignDoneData {
  campaign_id: string;
  vaulted: string[];
  rejected: Record<string, number>;
}

export interface VaultAddedData {
  strategy_id: string;
  name: string;
  symbol: string;
  timeframe: string;
  score: number;
}

export interface EquityUpdateData {
  account_login: number;
  equity: number;
  balance?: number;
  ts: string;
}

export type TransitionReason =
  | "live_10"
  | "live_30"
  | "sim_5"
  | "sim_30"
  | "hot_start"
  | "decay"
  | "silence"
  | "loss"
  | "manual"
  | "override"
  | "auto_recheck";

export interface IncubationTransitionData {
  bot_id: string;
  from_tier: Tier | null;
  to_tier: Tier | null;
  reason: TransitionReason;
  multiplier_before: number;
  multiplier_after: number;
}

export interface PilotHeartbeatData {
  pilot_id: string;
  online: boolean;
  chart?: {
    symbol?: string;
    period_minutes?: number;
    chart_id?: number;
  };
  bots_n: number;
}

export interface AlertEventData {
  kind: string;
  bot_id: string | null;
  severity: Severity;
  message: string;
}

export type WsEvent =
  | { type: "campaign.progress"; ts?: string; data: CampaignProgressData }
  | { type: "campaign.done"; ts?: string; data: CampaignDoneData }
  | { type: "vault.added"; ts?: string; data: VaultAddedData }
  | { type: "equity.update"; ts?: string; data: EquityUpdateData }
  | { type: "incubation.transition"; ts?: string; data: IncubationTransitionData }
  | { type: "pilot.heartbeat"; ts?: string; data: PilotHeartbeatData }
  | { type: "pilot.trade"; ts?: string; data: PilotTrade }
  | { type: "alert"; ts?: string; data: AlertEventData };

export type WsEventName = WsEvent["type"];

export const WS_EVENT_NAMES: WsEventName[] = [
  "campaign.progress",
  "campaign.done",
  "vault.added",
  "equity.update",
  "incubation.transition",
  "pilot.heartbeat",
  "pilot.trade",
  "alert",
];
