"""Vault — passport assembly, parity grades, reassessment (SPEC §2.3). CONFIRMED behaviour (CAM-14..20), thresholds ours.

Reassess = replay fast-track: re-run the backtest ONLY on bars with ts > trained_until (strictly newer — no lookahead).
Verdicts: TOO_EARLY (< 15 new trades, CAM-17/19), HOLDING, WEAKENING, REPLACE (CAM-20).
Parity grade bands are CLEAN-ROOM DESIGN: A ≤ 5 %, B ≤ 10 %, C ≤ 20 %, D ≤ 35 %, F.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from . import db
from .bars import Bars
from .fitness import SCORE_WEIGHTS, score
from .genome import archetype_of, mechanism_of
from .parity_backtester import CostModel, run_backtest

PARITY_BANDS: tuple[tuple[float, str], ...] = ((5.0, "A"), (10.0, "B"), (20.0, "C"), (35.0, "D"))
MIN_REASSESS_TRADES = 15
REPLAY_WEIGHTS = {k: v for k, v in SCORE_WEIGHTS.items() if k not in ("persistence", "robustness")}
_rw_total = sum(REPLAY_WEIGHTS.values())
REPLAY_WEIGHTS = {k: v * 100.0 / _rw_total for k, v in REPLAY_WEIGHTS.items()}  # comparable score: no IS-dependent parts


def replay_window(bars: Bars, trained_until: int) -> Bars:
    """Bars strictly after the training boundary (ts > trained_until). Bars at or before it are rejected."""
    return bars.after_ts(int(trained_until))


def parity_grade(diff_pct: float) -> str:
    for limit, grade in PARITY_BANDS:
        if diff_pct <= limit:
            return grade
    return "F"


def add_strategy(conn, survivor: dict[str, Any], campaign_id: str | None, symbol: str, timeframe: str,
                 trained_until: int | None, name: str | None = None) -> str:
    """Insert a survivor (automatic entry after all gates — CAM-14)."""
    sid = uuid.uuid4().hex[:12]
    genome = survivor["genome"]
    archetype = survivor.get("archetype") or archetype_of(genome)
    strat_name = name or f"{symbol}-{archetype}-{sid[:6].upper()}"
    equity = survivor.get("equity") or []
    db.insert(
        conn, "strategies", id=sid, campaign_id=campaign_id, name=strat_name, symbol=symbol, timeframe=timeframe,
        genome_json=json.dumps(genome, separators=(",", ":"), sort_keys=True), score=float(survivor["score"]),
        score_parts_json=json.dumps(survivor.get("parts", {})), archetype=archetype,
        mechanism=survivor.get("mechanism") or mechanism_of(genome),
        metrics_json=json.dumps(survivor.get("metrics", {}), default=float),
        equity_json=json.dumps(equity), trained_until=int(trained_until) if trained_until is not None else None,
        created_at=db.utcnow_iso(),
    )
    return sid


def _strategy(row) -> dict[str, Any]:
    return {
        "strategy_id": row["id"], "name": row["name"], "symbol": row["symbol"], "timeframe": row["timeframe"],
        "score": row["score"], "score_parts": json.loads(row["score_parts_json"] or "{}"), "archetype": row["archetype"],
        "mechanism": row["mechanism"], "metrics": json.loads(row["metrics_json"] or "{}"), "genome": json.loads(row["genome_json"]),
        "equity": json.loads(row["equity_json"] or "[]"), "trained_until": row["trained_until"], "created_at": row["created_at"],
    }


def latest_parity_grade(conn, strategy_id: str) -> str | None:
    return db.scalar(conn, "SELECT grade FROM parity_tests WHERE strategy_id = ? ORDER BY tested_at DESC LIMIT 1", (strategy_id,))


def latest_verdict(conn, strategy_id: str) -> str | None:
    return db.scalar(conn, "SELECT verdict FROM reassessments WHERE strategy_id = ? ORDER BY checked_at DESC LIMIT 1", (strategy_id,))


def list_vault(conn, min_score: float | None = None, symbol: str | None = None, timeframe: str | None = None,
               archetype: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM strategies WHERE 1=1"
    params: list[Any] = []
    if min_score is not None:
        sql += " AND score >= ?"
        params.append(float(min_score))
    for col, val in (("symbol", symbol), ("timeframe", timeframe), ("archetype", archetype)):
        if val:
            sql += f" AND {col} = ?"
            params.append(val)
    out = []
    for row in db.fetchall(conn, sql + " ORDER BY score DESC, created_at DESC", params):
        s = _strategy(row)
        oos = s["metrics"].get("oos", {})
        out.append({
            "strategy_id": s["strategy_id"], "name": s["name"], "symbol": s["symbol"], "timeframe": s["timeframe"],
            "score": s["score"], "score_parts": s["score_parts"], "archetype": s["archetype"], "mechanism": s["mechanism"],
            "oos": {"trades": oos.get("trades", 0), "net": oos.get("net", 0.0), "sharpe": oos.get("sharpe", 0.0),
                    "pf": oos.get("profit_factor", 0.0), "max_dd": oos.get("max_dd_pct", 0.0), "persistence": oos.get("persistence", 0.0)},
            "parity_grade": latest_parity_grade(conn, s["strategy_id"]),
            "health": latest_verdict(conn, s["strategy_id"]) or "UNTESTED",
            "mq5_url": f"/api/v1/vault/{s['strategy_id']}/export.mq5",
        })
    return out


def passport(conn, strategy_id: str) -> dict[str, Any] | None:
    """Passport: score, archetype, mechanism, DNA, equity curve with OOS marked, parity tests, reassessments (CAM-15)."""
    row = db.fetchone(conn, "SELECT * FROM strategies WHERE id = ?", (strategy_id,))
    if row is None:
        return None
    s = _strategy(row)
    parity = [dict(r) for r in db.fetchall(conn, "SELECT mt5_net_return, engine_net_return, grade, tested_at FROM parity_tests WHERE strategy_id = ? ORDER BY tested_at DESC", (strategy_id,))]
    reass = [dict(r) for r in db.fetchall(conn, "SELECT verdict, trades_since, score_delta, expectancy, checked_at FROM reassessments WHERE strategy_id = ? ORDER BY checked_at DESC", (strategy_id,))]
    curve = s["equity"] if s["equity"] and isinstance(s["equity"][0], dict) and "oos" in s["equity"][0] else [
        {"ts": e["ts"], "equity": e["equity"], "oos": False} for e in s["equity"]]
    return {
        "strategy_id": s["strategy_id"], "name": s["name"], "symbol": s["symbol"], "timeframe": s["timeframe"],
        "score": s["score"], "score_parts": s["score_parts"], "archetype": s["archetype"], "mechanism": s["mechanism"],
        "genome": s["genome"], "metrics": s["metrics"], "equity": curve, "parity_tests": parity, "reassessments": reass,
        "parity_grade": latest_parity_grade(conn, strategy_id), "health": latest_verdict(conn, strategy_id) or "UNTESTED",
        "trained_until": s["trained_until"], "created_at": s["created_at"], "mq5_url": f"/api/v1/vault/{strategy_id}/export.mq5",
    }


def record_parity(conn, strategy_id: str, mt5_net_return: float, engine_net_return: float) -> dict[str, Any]:
    """Compare MT5 vs engine net return on the same window; grade bands ours (CAM-16 names CONFIRMED)."""
    diff_pct = abs(float(mt5_net_return) - float(engine_net_return)) / max(abs(float(engine_net_return)), 1e-9) * 100.0
    grade = parity_grade(diff_pct)
    tested_at = db.utcnow_iso()
    conn.execute(
        "INSERT OR REPLACE INTO parity_tests(strategy_id, mt5_net_return, engine_net_return, grade, tested_at) VALUES (?,?,?,?,?)",
        (strategy_id, float(mt5_net_return), float(engine_net_return), grade, tested_at),
    )
    return {"grade": grade, "engine_net_return": float(engine_net_return), "mt5_net_return": float(mt5_net_return), "diff_pct": round(diff_pct, 4), "tested_at": tested_at}


def reassess(conn, strategy_id: str, bars: Bars, m1_bars: Bars | None = None, cost: CostModel | None = None) -> dict[str, Any] | None:
    """Replay fast-track: rerun the strategy on bars strictly newer than trained_until; verdict HOLDING/WEAKENING/REPLACE/TOO_EARLY."""
    row = db.fetchone(conn, "SELECT * FROM strategies WHERE id = ?", (strategy_id,))
    if row is None:
        return None
    genome = json.loads(row["genome_json"])
    trained_until = int(row["trained_until"] or 0)
    window = replay_window(bars, trained_until)
    sub = m1_bars.after_ts(trained_until) if m1_bars is not None else None
    if len(window) < 30:
        return _store_verdict(conn, strategy_id, "TOO_EARLY", 0, 0.0, 0.0)
    res = run_backtest(window, genome, cost or CostModel.for_symbol(row["symbol"]), sub)
    new_m = dict(res.metrics)
    trades_since = int(new_m["trades"])
    expectancy = float(new_m["expectancy_r"])
    if trades_since < MIN_REASSESS_TRADES:
        return _store_verdict(conn, strategy_id, "TOO_EARLY", trades_since, 0.0, expectancy)
    old = json.loads(row["metrics_json"] or "{}").get("oos", {})
    new_score, _ = score(new_m, REPLAY_WEIGHTS, robustness=None)
    old_score, _ = score(old, REPLAY_WEIGHTS, robustness=None)
    score_delta = float(new_score - old_score)
    old_exp = float(old.get("expectancy_r", 0.0))
    if expectancy <= 0 or score_delta <= -15.0:
        verdict = "REPLACE"
    elif score_delta <= -5.0 or (old_exp > 0 and expectancy < 0.5 * old_exp):
        verdict = "WEAKENING"
    else:
        verdict = "HOLDING"
    return _store_verdict(conn, strategy_id, verdict, trades_since, score_delta, expectancy)


def _store_verdict(conn, strategy_id: str, verdict: str, trades_since: int, score_delta: float, expectancy: float) -> dict[str, Any]:
    conn.execute(
        "INSERT OR REPLACE INTO reassessments(strategy_id, verdict, trades_since, score_delta, expectancy, checked_at) VALUES (?,?,?,?,?,?)",
        (strategy_id, verdict, int(trades_since), float(score_delta), float(expectancy), db.utcnow_iso()),
    )
    return {"verdict": verdict, "trades_since": int(trades_since), "score_delta": round(float(score_delta), 4), "expectancy": round(float(expectancy), 4)}


__all__ = ["PARITY_BANDS", "REPLAY_WEIGHTS", "replay_window", "parity_grade", "add_strategy", "list_vault", "passport",
           "record_parity", "reassess", "latest_verdict", "latest_parity_grade"]
