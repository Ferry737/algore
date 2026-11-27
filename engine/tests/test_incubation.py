"""Incubation ladder T1–T15 (SPEC §2.5)."""
from __future__ import annotations

from app.incubation import (
    FULL,
    INCUBATION,
    PROVING,
    RUNG_MULTIPLIER,
    BotState,
    IncubationContext,
    apply_auto,
    apply_pause,
    apply_rung,
    evaluate,
    graduate,
    initial_state,
    update_counters,
)


def ctx(**kw) -> IncubationContext:
    base = dict(pilot_online=True, backtest_mean_r=0.5, backtest_max_dd_pct=10.0, expected_trades_last_period=10.0, deployed_days=40.0)
    base.update(kw)
    return IncubationContext(**base)


def live(n: int, healthy: int | None = None, mean_r: float = 0.5, incubation: bool = True) -> BotState:
    s = initial_state("bot-1", incubation=incubation)
    s.live_trades = n
    s.healthy_live_trades = n if healthy is None else healthy
    s.live_net_r = mean_r * n
    s.live_trades_last_period = n  # type: ignore[attr-defined]
    return s


def test_initial_state_rungs_and_no_tier():
    s = initial_state("b", incubation=True)
    assert s.tier == INCUBATION and s.multiplier == 0.25 and s.auto and not s.paused and s.frozen_reason is None
    s2 = initial_state("b", incubation=False)
    assert s2.tier is None and s2.multiplier == 1.0


def test_live_path_10_to_proving_then_30_profitable_to_full():
    ev = evaluate(live(10), ctx(live_trades_last_period=10))
    assert ev.state.tier == PROVING and ev.state.multiplier == 0.5
    assert ev.transitions[0]["reason"] == "live_10"
    ev2 = evaluate(ev.state, ctx(live_trades_last_period=30))
    assert ev2.state.tier == PROVING  # only 10 healthy trades so far -> stays
    ev3 = evaluate(live(30, mean_r=0.5, incubation=False) if False else _at(live(30), PROVING), ctx(live_trades_last_period=30))
    assert ev3.state.tier == FULL and ev3.state.multiplier == 1.0
    assert ev3.transitions[0]["reason"] == "live_30"
    assert ev3.transitions[0]["multiplier_before"] == 0.5 and ev3.transitions[0]["multiplier_after"] == 1.0


def _at(s: BotState, tier: str) -> BotState:
    s.tier = tier
    s.multiplier = RUNG_MULTIPLIER[tier]
    return s


def test_sim_path_5_to_proving_and_30_with_10_live_to_full():
    ev = evaluate(live(5), ctx(sim_ok=True))
    assert ev.state.tier == PROVING and ev.transitions[0]["reason"] == "sim_5"
    s = _at(live(10), PROVING)
    s.sim_healthy_trades = 25
    ev2 = evaluate(s, ctx(sim_ok=True))
    assert ev2.state.tier == FULL and ev2.transitions[0]["reason"] == "sim_30"
    s3 = _at(live(5), PROVING)
    s3.sim_healthy_trades = 40
    assert evaluate(s3, ctx(sim_ok=True)).state.tier == PROVING  # needs >= 10 live


def test_hot_start_skips_first_wait_once():
    s = live(5, mean_r=0.6)
    ev = evaluate(s, ctx(live_wins_first_n=4))
    assert ev.state.tier == PROVING and ev.transitions[0]["reason"] == "hot_start"
    ev2 = evaluate(_at(s, PROVING), ctx(live_wins_first_n=4, hot_start_done=True))
    assert ev2.state.tier == PROVING and not ev2.transitions
    ev3 = evaluate(live(5, mean_r=0.6), ctx(live_wins_first_n=3))
    assert ev3.state.tier == INCUBATION


def test_decay_freeze_and_auto_demotion_on_replace():
    s = _at(live(12), PROVING)
    ev = evaluate(s, ctx(decay_verdict="REPLACE"))
    assert ev.state.frozen_reason == "DECAY" and ev.state.tier == INCUBATION
    assert ev.transitions[0]["reason"] == "decay" and ev.transitions[0]["multiplier_after"] == 0.25
    # a second evaluation under the same verdict does not demote again
    ev2 = evaluate(ev.state, ctx(decay_verdict="REPLACE"))
    assert ev2.state.tier == INCUBATION and not ev2.transitions
    s2 = _at(live(12), PROVING)
    s2.auto = False
    ev3 = evaluate(s2, ctx(decay_verdict="REPLACE"))
    assert ev3.state.frozen_reason == "DECAY" and ev3.state.tier == PROVING
    ev4 = evaluate(_at(live(12), PROVING), ctx(decay_verdict="WEAKENING"))
    assert ev4.state.frozen_reason == "DECAY" and ev4.state.tier == PROVING
    assert ev4.state.health_word == "WATCH" or ev4.state.health_word == "REPLACE"
    # frozen bots never climb
    ev5 = evaluate(_at(live(40), PROVING), ctx(decay_verdict="WEAKENING"))
    assert ev5.state.tier == PROVING


def test_silence_freeze():
    s = live(10)
    s.live_trades_last_period = 1  # type: ignore[attr-defined]
    ev = evaluate(s, ctx(expected_trades_last_period=10.0, deployed_days=45.0))
    assert ev.state.frozen_reason == "SILENCE" and ev.state.tier == INCUBATION


def test_losing_record_holds_and_stops_healthy_counting():
    s = live(12, mean_r=-0.2)
    ev = evaluate(s, ctx())
    assert ev.state.frozen_reason == "LOSS" and ev.state.tier == INCUBATION and ev.state.health_word == "REPLACE"
    s2 = initial_state("b", True)
    for r in (0.5, 0.4, -1.0, -1.0, -1.0):
        update_counters(s2, r, 0.3)
    assert s2.live_trades == 5 and s2.healthy_live_trades == 2  # losers stop counting once the record is negative


def test_manual_mode_blocks_promotion_until_graduate():
    s = live(10)
    s.auto = False
    ev = evaluate(s, ctx())
    assert ev.state.tier == INCUBATION and ev.state.pending_graduation is True
    ev2 = graduate(ev.state, ctx())
    assert ev2.state.tier == PROVING and ev2.state.pending_graduation is False
    assert ev2.transitions[0]["reason"] == "manual"
    s3 = live(10)
    s3.auto = False
    ev3 = apply_auto(s3, True, ctx())
    assert ev3.state.tier == PROVING and ev3.transitions[0]["reason"] == "auto_recheck"


def test_rung_override_logs_and_sets_multiplier():
    s = initial_state("b", True)
    s2, tr = apply_rung(s, "FULL", "operator decision")
    assert s2.tier == FULL and s2.multiplier == 1.0 and s2.pending_graduation is False
    assert s2.override_log[-1]["rung"] == "FULL" and s2.override_log[-1]["reason"] == "operator decision"
    assert tr["reason"] == "override"


def test_pause_all_sets_paused_and_keeps_multiplier():
    s = _at(live(30), PROVING)
    s2 = apply_pause(s, True)
    assert s2.paused and s2.multiplier == 0.5
    ev = evaluate(s2, ctx())
    assert ev.state.tier == PROVING and not ev.transitions


def test_pilot_offline_freezes_ladder_globally():
    ev = evaluate(_at(live(40), PROVING), ctx(pilot_online=False))
    assert ev.state.frozen_reason == "PILOT_OFFLINE" and ev.state.tier == PROVING and not ev.transitions
    checks = {c["id"]: c for c in ev.checks}
    assert checks["trading_normally"]["pass"] is False


def test_time_alone_never_promotes():
    s = initial_state("b", True)
    ev = evaluate(s, ctx(deployed_days=400.0))
    assert ev.state.tier == INCUBATION and not ev.transitions
    checks = {c["id"]: c for c in ev.checks}
    assert set(checks) == {
        "enough_live_trades", "time_in_incubation", "simulated_record", "making_money", "no_decay_warning",
        "health_word", "trading_normally", "no_bad_streak",
    }
    assert checks["time_in_incubation"]["pass"] is True and "never" in checks["time_in_incubation"]["text"].lower()


def test_bad_streak_holds():
    ev = evaluate(live(12), ctx(consecutive_losses=5))
    checks = {c["id"]: c for c in ev.checks}
    assert checks["no_bad_streak"]["pass"] is False
    assert ev.state.tier == INCUBATION


def test_duplicate_health_word_blocks():
    ev = evaluate(live(12), ctx(duplicate=True))
    assert ev.state.health_word == "DUPLICATE" and ev.state.tier == INCUBATION
