"""Incubation ladder — SPEC §2.5 state machine T1–T15. CONFIRMED behaviour (INC-01..15), CLEAN-ROOM thresholds.

State per bot: rung ∈ {INCUBATION 0.25, PROVING 0.50, FULL 1.00}, auto, paused, frozen_reason ∈ {LOSS, DECAY,
SILENCE, PILOT_OFFLINE}, health_word ∈ {OK, EARLY, WATCH, REPLACE, DUPLICATE}, counters, override_log.
The engine never touches open positions: it only publishes a multiplier and a paused flag (INC-11).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

INCUBATION, PROVING, FULL = "INCUBATION", "PROVING", "FULL"
RUNG_MULTIPLIER: dict[str, float] = {INCUBATION: 0.25, PROVING: 0.5, FULL: 1.0}
RUNG_ORDER: tuple[str, ...] = (INCUBATION, PROVING, FULL)
BLOCKING_WORDS: tuple[str, ...] = ("WATCH", "REPLACE", "DUPLICATE")
HEALTHY_RATIO = 0.55  # INFERRED: a live trade is healthy when the running live mean R >= 55 % of the backtest mean R (CAM-08)
MIN_HEALTH_TRADES = 15  # CAM-17: re-scored once 15 new trades exist
BAD_STREAK = 5
PROMOTION_TRADES = {INCUBATION: 10, PROVING: 30}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class BotState:
    bot_id: str
    tier: str | None
    multiplier: float
    auto: bool = True
    paused: bool = False
    frozen_reason: str | None = None
    health_word: str = "EARLY"
    pending_graduation: bool = False
    live_trades: int = 0
    healthy_live_trades: int = 0
    sim_healthy_trades: int = 0
    live_net_r: float = 0.0
    checks_json: str | None = None
    override_log: list[dict[str, Any]] = field(default_factory=list)
    updated_at: str = field(default_factory=now_iso)

    @classmethod
    def from_row(cls, row: Any) -> "BotState":
        import json

        def load(text: str | None, default: Any) -> Any:
            try:
                return json.loads(text) if text else default
            except (TypeError, ValueError):
                return default

        keys = row.keys()
        return cls(
            bot_id=row["bot_id"], tier=row["tier"], multiplier=float(row["multiplier"]), auto=bool(row["auto"]),
            paused=bool(row["paused"]), frozen_reason=row["frozen_reason"], health_word=row["health_word"],
            pending_graduation=bool(row["pending_graduation"]), live_trades=int(row["live_trades"]),
            healthy_live_trades=int(row["healthy_live_trades"]), sim_healthy_trades=int(row["sim_healthy_trades"]),
            live_net_r=float(row["live_net_r"]), checks_json=row["checks_json"] if "checks_json" in keys else None,
            override_log=load(row["override_log_json"] if "override_log_json" in keys else None, []),
            updated_at=row["updated_at"] if "updated_at" in keys else now_iso(),
        )

    def to_row(self) -> dict[str, Any]:
        import json

        return {
            "bot_id": self.bot_id, "tier": self.tier, "multiplier": self.multiplier, "auto": int(self.auto),
            "paused": int(self.paused), "frozen_reason": self.frozen_reason, "health_word": self.health_word,
            "pending_graduation": int(self.pending_graduation), "live_trades": self.live_trades,
            "healthy_live_trades": self.healthy_live_trades, "sim_healthy_trades": self.sim_healthy_trades,
            "live_net_r": self.live_net_r, "checks_json": self.checks_json,
            "override_log_json": json.dumps(self.override_log, separators=(",", ":")), "updated_at": self.updated_at,
        }


@dataclass
class IncubationContext:
    """Everything the state machine needs from the outside world (computed by the API layer from DB rows)."""

    pilot_online: bool = True
    sim_ok: bool = False
    decay_verdict: str | None = None
    live_max_dd_pct: float = 0.0
    backtest_max_dd_pct: float = 0.0
    backtest_mean_r: float = 0.0
    live_wins_first_n: int = 0
    hot_start_done: bool = False
    consecutive_losses: int = 0
    live_trades_last_period: float = 10.0
    expected_trades_last_period: float = 10.0
    deployed_days: float = 0.0
    duplicate: bool = False
    hot_trades: int = 5
    hot_wins: int = 4
    silence_days: int = 30
    silence_ratio: float = 0.25


@dataclass
class IncubationEvaluation:
    state: BotState
    transitions: list[dict[str, Any]]
    checks: list[dict[str, Any]]
    frozen_changed: bool


# ----------------------------------------------------------------------------- helpers
def initial_state(bot_id: str, incubation: bool = True) -> BotState:
    """T14: incubation=false at deploy → rung FULL, tier None (NO TIER)."""
    if incubation:
        return BotState(bot_id=bot_id, tier=INCUBATION, multiplier=RUNG_MULTIPLIER[INCUBATION])
    return BotState(bot_id=bot_id, tier=None, multiplier=1.0, health_word="OK")


def _clone(state: BotState) -> BotState:
    s = copy.copy(state)
    s.override_log = copy.deepcopy(state.override_log)
    return s


def mean_r(state: BotState) -> float:
    return state.live_net_r / state.live_trades if state.live_trades else 0.0


def health_word(state: BotState, ctx: IncubationContext) -> str:
    """OK / EARLY / WATCH / REPLACE / DUPLICATE (nothing climbs while the word is WATCH / REPLACE / DUPLICATE)."""
    if ctx.duplicate:
        return "DUPLICATE"
    if ctx.decay_verdict == "REPLACE":
        return "REPLACE"
    mr = mean_r(state)
    if ctx.backtest_max_dd_pct > 0 and ctx.live_max_dd_pct > 2.0 * ctx.backtest_max_dd_pct:
        return "REPLACE"
    if state.live_trades > 0 and mr < 0:  # a losing record is never merely EARLY (T8)
        return "REPLACE"
    if ctx.decay_verdict == "WEAKENING":
        return "WATCH"
    if state.live_trades < MIN_HEALTH_TRADES:
        return "EARLY"
    if ctx.backtest_mean_r > 0 and mr >= HEALTHY_RATIO * ctx.backtest_mean_r and mr > 0:
        return "OK"
    return "WATCH" if mr >= 0 else "REPLACE"


def update_counters(state: BotState, r_multiple: float, bt_first_n_mean_r: float) -> BotState:
    """T15: fold one live trade into the counters. Trades count as healthy while the record is winning and the
    running mean R keeps ≥ 55 % of the backtest's mean R over the same number of trades."""
    state.live_trades += 1
    state.live_net_r += float(r_multiple)
    running = mean_r(state)
    if running >= 0 and running >= HEALTHY_RATIO * float(bt_first_n_mean_r):
        state.healthy_live_trades += 1
    return state


def _transition(transitions: list[dict[str, Any]], state: BotState, from_tier: str | None, to_tier: str, reason: str, before: float) -> None:
    transitions.append({"bot_id": state.bot_id, "from_tier": from_tier, "to_tier": to_tier, "reason": reason,
                        "multiplier_before": before, "multiplier_after": state.multiplier})


def _set_tier(state: BotState, tier: str, reason: str, transitions: list[dict[str, Any]]) -> BotState:
    before, from_tier = state.multiplier, state.tier
    state.tier, state.multiplier = tier, RUNG_MULTIPLIER[tier]
    state.updated_at = now_iso()
    _transition(transitions, state, from_tier, tier, reason, before)
    return state


def _promote(state: BotState, reason: str, transitions: list[dict[str, Any]]) -> BotState:
    idx = RUNG_ORDER.index(state.tier) if state.tier in RUNG_ORDER else -1
    return _set_tier(state, RUNG_ORDER[min(idx + 1, len(RUNG_ORDER) - 1)], reason, transitions)


def checks(state: BotState, ctx: IncubationContext) -> list[dict[str, Any]]:
    """The eight PASS/HELD checks exposed per bot."""
    mr = mean_r(state)
    silence = state.frozen_reason == "SILENCE" or not ctx.pilot_online
    out = [
        {"id": "enough_live_trades", "label": "Enough live trades", "pass": state.live_trades >= PROMOTION_TRADES[state.tier] if state.tier in PROMOTION_TRADES else True,
         "value": state.live_trades, "text": f"{state.live_trades} live trades ({state.healthy_live_trades} healthy)"},
        {"id": "time_in_incubation", "label": "Time in incubation", "pass": ctx.deployed_days >= 14, "value": round(ctx.deployed_days, 1),
         "text": f"{ctx.deployed_days:.0f} days deployed — informational only: time alone never promotes"},
        {"id": "simulated_record", "label": "Simulated record", "pass": bool(ctx.sim_ok), "value": bool(ctx.sim_ok),
         "text": "replay since training holds up" if ctx.sim_ok else "replay since training not confirmed"},
        {"id": "making_money", "label": "Making money", "pass": state.live_net_r > 0, "value": round(state.live_net_r, 2),
         "text": f"net {state.live_net_r:+.2f}R, mean {mr:+.2f}R"},
        {"id": "no_decay_warning", "label": "No decay warning", "pass": state.frozen_reason != "DECAY",
         "value": ctx.decay_verdict or "none", "text": f"verdict {ctx.decay_verdict or 'none'}"},
        {"id": "health_word", "label": "Health word", "pass": state.health_word not in BLOCKING_WORDS, "value": state.health_word,
         "text": f"health word {state.health_word}"},
        {"id": "trading_normally", "label": "Trading normally", "pass": not silence,
         "value": f"{ctx.live_trades_last_period:g}/{ctx.expected_trades_last_period:g}",
         "text": "EA silent / pilot offline" if not ctx.pilot_online else (f"{ctx.live_trades_last_period:g} trades vs {ctx.expected_trades_last_period:g} expected" if silence else "trading at backtest frequency")},
        {"id": "no_bad_streak", "label": "No bad streak", "pass": ctx.consecutive_losses < BAD_STREAK, "value": ctx.consecutive_losses,
         "text": f"{ctx.consecutive_losses} consecutive losers (5 holds)"},
    ]
    return out


# ----------------------------------------------------------------------------- state machine
def evaluate(state: BotState, ctx: IncubationContext) -> IncubationEvaluation:
    """Apply T1–T10 / T15 to a bot state. Pure function: returns a new state plus transitions (only on rung change)."""
    s = _clone(state)
    # A caller may attach the observed trade frequency to the state (legacy API); prefer it over the
    # context default so a silent bot is frozen even when the context was built with defaults.
    if hasattr(state, "live_trades_last_period"):
        ctx = copy.copy(ctx)
        ctx.live_trades_last_period = float(getattr(state, "live_trades_last_period"))
    s.health_word = health_word(s, ctx)
    prev_frozen = s.frozen_reason
    transitions: list[dict[str, Any]] = []
    # ---- freezes (T6 decay, T7 silence, T8 losing record, T9 pilot offline)
    frozen: str | None = None
    if not ctx.pilot_online:
        frozen = "PILOT_OFFLINE"
    elif ctx.decay_verdict in ("WEAKENING", "REPLACE") or (ctx.backtest_max_dd_pct > 0 and ctx.live_max_dd_pct > 2.0 * ctx.backtest_max_dd_pct):
        frozen = "DECAY"
    elif s.live_trades > 0 and mean_r(s) < 0:
        frozen = "LOSS"
    elif ctx.deployed_days >= ctx.silence_days and ctx.live_trades_last_period < ctx.silence_ratio * ctx.expected_trades_last_period:
        frozen = "SILENCE"
    s.frozen_reason = frozen
    if frozen == "DECAY" and ctx.decay_verdict == "REPLACE" and s.auto and prev_frozen != "DECAY" and s.tier in RUNG_MULTIPLIER and s.tier != INCUBATION:
        _set_tier(s, RUNG_ORDER[RUNG_ORDER.index(s.tier) - 1], "decay", transitions)  # T6 AUTO demotion
    # ---- promotions (T1–T5, T10)
    held = ctx.consecutive_losses >= BAD_STREAK or s.health_word in BLOCKING_WORDS
    earned: str | None = None
    if frozen is None and not s.paused and not held and s.tier in RUNG_MULTIPLIER:
        mr = mean_r(s)
        if s.live_trades >= ctx.hot_trades and not ctx.hot_start_done and ctx.live_wins_first_n >= ctx.hot_wins and mr >= ctx.backtest_mean_r:
            earned = "hot_start"  # T5
        elif s.tier == INCUBATION and s.healthy_live_trades >= 10:
            earned = "live_10"  # T1
        elif s.tier == INCUBATION and ctx.sim_ok and s.healthy_live_trades >= 5:
            earned = "sim_5"  # T3
        elif s.tier == PROVING and s.healthy_live_trades >= 30 and s.live_net_r > 0:
            earned = "live_30"  # T2
        elif s.tier == PROVING and ctx.sim_ok and s.healthy_live_trades + s.sim_healthy_trades >= 30 and s.healthy_live_trades >= 10:
            earned = "sim_30"  # T4
    if earned:
        if s.auto:
            _promote(s, earned, transitions)
            s.pending_graduation = False
        else:
            s.pending_graduation = True  # T10: AUTO off → wait for POST /graduate
    else:
        s.pending_graduation = False
    result = checks(s, ctx)
    import json

    s.checks_json = json.dumps(result, separators=(",", ":"))
    return IncubationEvaluation(s, transitions, result, frozen_changed=(prev_frozen != frozen))


def graduate(state: BotState, ctx: IncubationContext) -> IncubationEvaluation:
    """Apply a pending promotion with reason 'manual' (INC-09 GRADUATE button)."""
    probe = _clone(state)
    probe.auto = True
    ev = evaluate(probe, ctx)
    if ev.transitions:
        ev.transitions[-1]["reason"] = "manual"
        ev.state.auto = state.auto
        ev.state.pending_graduation = False
        return ev
    return evaluate(state, ctx)


def apply_rung(state: BotState, rung: str, reason: str, at: str | None = None) -> tuple[BotState, dict[str, Any]]:
    """T11: manual rung override (dashboard scope) — sets the rung and logs the override."""
    if rung not in RUNG_MULTIPLIER:
        raise ValueError(f"unknown rung {rung!r}")
    s = _clone(state)
    transitions: list[dict[str, Any]] = []
    _set_tier(s, rung, "override", transitions)
    s.pending_graduation = False
    s.override_log.append({"at": at or now_iso(), "rung": rung, "reason": reason, "by": "dashboard"})
    return s, transitions[0]


def apply_auto(state: BotState, auto: bool, ctx: IncubationContext) -> IncubationEvaluation:
    """T12: auto toggled — re-evaluate from live results when turning on."""
    s = _clone(state)
    s.auto = bool(auto)
    ev = evaluate(s, ctx)
    if auto:
        for t in ev.transitions:
            t["reason"] = "auto_recheck"
    return ev


def apply_pause(state: BotState, paused: bool) -> BotState:
    """T13: Emergency Pause — EA opens no new trades; multiplier unchanged."""
    s = _clone(state)
    s.paused = bool(paused)
    s.updated_at = now_iso()
    return s


__all__ = ["INCUBATION", "PROVING", "FULL", "RUNG_MULTIPLIER", "RUNG_ORDER", "BotState", "IncubationContext",
           "IncubationEvaluation", "initial_state", "evaluate", "graduate", "apply_rung", "apply_auto", "apply_pause",
           "update_counters", "health_word", "checks", "mean_r"]
