-- AlgoRE data model — SPEC §3 verbatim, plus extra indexes.
PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS campaigns(
  id TEXT PRIMARY KEY, name TEXT NOT NULL, symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',   -- queued|running|done|failed|stopped
  params_json TEXT NOT NULL, created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
  error TEXT, stats_json TEXT);
CREATE TABLE IF NOT EXISTS campaign_generations(
  campaign_id TEXT NOT NULL REFERENCES campaigns(id), tribe TEXT NOT NULL, generation INTEGER NOT NULL,
  best_fitness REAL, mean_fitness REAL, survivors INTEGER, elapsed_s REAL,
  PRIMARY KEY(campaign_id, tribe, generation));
CREATE TABLE IF NOT EXISTS bars(
  symbol TEXT NOT NULL, timeframe TEXT NOT NULL, ts INTEGER NOT NULL,   -- ts = bar open, seconds, broker server time
  open REAL, high REAL, low REAL, close REAL, volume REAL,
  PRIMARY KEY(symbol, timeframe, ts));
CREATE TABLE IF NOT EXISTS strategies(
  id TEXT PRIMARY KEY, campaign_id TEXT REFERENCES campaigns(id), name TEXT, symbol TEXT, timeframe TEXT,
  genome_json TEXT NOT NULL, score REAL, score_parts_json TEXT, archetype TEXT, mechanism TEXT,
  metrics_json TEXT,      -- {is:{...}, oos:{trades, net, sharpe, pf, max_dd, expectancy_r, persistence, ...}}
  equity_json TEXT,       -- [{ts, equity}] with oos_from index
  trained_until INTEGER,  -- last bar ts used for training+oos at vault time
  created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS parity_tests(
  strategy_id TEXT NOT NULL REFERENCES strategies(id), mt5_net_return REAL, engine_net_return REAL,
  grade TEXT,             -- A|B|C|D|F
  tested_at TEXT NOT NULL, PRIMARY KEY(strategy_id, tested_at));
CREATE TABLE IF NOT EXISTS reassessments(
  strategy_id TEXT NOT NULL REFERENCES strategies(id), verdict TEXT NOT NULL,  -- HOLDING|WEAKENING|REPLACE|TOO_EARLY
  trades_since INTEGER, score_delta REAL, expectancy REAL, checked_at TEXT NOT NULL,
  PRIMARY KEY(strategy_id, checked_at));
CREATE TABLE IF NOT EXISTS portfolios(
  id TEXT PRIMARY KEY, name TEXT NOT NULL, target_heat_pct REAL NOT NULL, symbol_lock INTEGER NOT NULL DEFAULT 1,
  sizing_mode TEXT NOT NULL DEFAULT 'heat',  -- heat|decorrelated (API stores canonical equal_heat|variance_scaled)
  created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS portfolio_members(
  portfolio_id TEXT NOT NULL REFERENCES portfolios(id), strategy_id TEXT NOT NULL REFERENCES strategies(id),
  risk_pct REAL, scale REAL, avg_corr REAL, deployed_bot_id TEXT,
  PRIMARY KEY(portfolio_id, strategy_id));
CREATE TABLE IF NOT EXISTS bots(
  id TEXT PRIMARY KEY, strategy_id TEXT NOT NULL REFERENCES strategies(id), portfolio_id TEXT REFERENCES portfolios(id),
  symbol TEXT NOT NULL, magic INTEGER NOT NULL UNIQUE, account_login INTEGER, target_risk_pct REAL NOT NULL,
  incubation INTEGER NOT NULL DEFAULT 1, deployed_at TEXT NOT NULL, expires_at TEXT);
CREATE TABLE IF NOT EXISTS incubation_states(
  bot_id TEXT PRIMARY KEY REFERENCES bots(id), tier TEXT,            -- INCUBATION|PROVING|FULL|NULL (NO TIER)
  multiplier REAL NOT NULL, auto INTEGER NOT NULL DEFAULT 1, paused INTEGER NOT NULL DEFAULT 0,
  frozen_reason TEXT, health_word TEXT NOT NULL DEFAULT 'EARLY', pending_graduation INTEGER NOT NULL DEFAULT 0,
  live_trades INTEGER NOT NULL DEFAULT 0, healthy_live_trades INTEGER NOT NULL DEFAULT 0, sim_healthy_trades INTEGER NOT NULL DEFAULT 0,
  live_net_r REAL NOT NULL DEFAULT 0, checks_json TEXT, override_log_json TEXT, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pilot_heartbeats(
  pilot_id TEXT NOT NULL, sent_at TEXT NOT NULL, account_login INTEGER, chart_symbol TEXT, chart_period INTEGER,
  terminal_json TEXT, bots_json TEXT, received_at TEXT NOT NULL, PRIMARY KEY(pilot_id, sent_at));
CREATE TABLE IF NOT EXISTS pilot_trades(
  account_login INTEGER NOT NULL, ticket INTEGER NOT NULL, position_id INTEGER, bot_id TEXT REFERENCES bots(id),
  symbol TEXT, direction TEXT, lots REAL, open_time TEXT, close_time TEXT, open_price REAL, close_price REAL,
  profit REAL, commission REAL, swap REAL, sl REAL, tp REAL, reason TEXT, r_multiple REAL, healthy INTEGER,
  ingested_at TEXT NOT NULL, PRIMARY KEY(account_login, ticket));
CREATE TABLE IF NOT EXISTS decay_alerts(
  id TEXT PRIMARY KEY, bot_id TEXT REFERENCES bots(id), strategy_id TEXT, kind TEXT NOT NULL,  -- decay|silence|loss|pilot_offline|daily_loss
  severity TEXT NOT NULL, message TEXT, value REAL, threshold REAL, created_at TEXT NOT NULL, resolved_at TEXT);
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_bars_tf  ON bars(symbol, timeframe, ts);
CREATE INDEX IF NOT EXISTS idx_trades_bot ON pilot_trades(bot_id, close_time);
CREATE INDEX IF NOT EXISTS idx_hb_time   ON pilot_heartbeats(received_at);
CREATE INDEX IF NOT EXISTS idx_events_id  ON events(id);
-- additional indexes (ours)
CREATE INDEX IF NOT EXISTS idx_events_topic ON events(topic, id);
CREATE INDEX IF NOT EXISTS idx_trades_account ON pilot_trades(account_login, ticket);
CREATE INDEX IF NOT EXISTS idx_members_portfolio ON portfolio_members(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_alerts_active ON decay_alerts(bot_id, resolved_at);
