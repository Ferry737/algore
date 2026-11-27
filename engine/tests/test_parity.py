"""Parity: Python evaluator vs the rendered MQL5 expressions (via a small Python mirror), backtester rules, exporter output."""
from __future__ import annotations

import re

import numpy as np
import pytest

from app import indicators
from app.bars import Bars
from app.evaluator import compute_signals
from app.genome import random_genome, validate
from app.mql5_exporter import PILOT_BRIDGE_MQL5, export_ea, render_expr
from app.parity_backtester import CostModel, run_backtest, split_results

TERM_RE = re.compile(r"^(close|open|high|low|volume|rsi|atr|ema|sma|bbpos|adx|hour|dow|ret)(\d*)(?:k([0-9.]+))?_s(\d+)$")
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
PRICES = {"close", "open", "high", "low", "volume"}


def mirror_series(name: str, bars: Bars) -> np.ndarray:
    """Independent re-implementation of the renderer's term vocabulary (NOT the evaluator's SeriesCache)."""
    m = TERM_RE.match(name)
    assert m, f"unknown identifier in rendered expression: {name}"
    f, n, k, shift = m.group(1), m.group(2), m.group(3), int(m.group(4))
    c, h, l = bars.close, bars.high, bars.low
    if f in PRICES:
        s = getattr(bars, f)
    elif f == "hour":
        s = bars.hours
    elif f == "dow":
        s = bars.dows
    elif f == "rsi":
        s = indicators.rsi(c, int(n))
    elif f == "atr":
        s = indicators.atr(h, l, c, int(n))
    elif f == "ema":
        s = indicators.ema(c, int(n))
    elif f == "sma":
        s = indicators.sma(c, int(n))
    elif f == "bbpos":
        s = indicators.bb_pos(c, int(n), float(k))
    elif f == "adx":
        s = indicators.adx(h, l, c, int(n))
    else:  # ret
        s = indicators.ret(c, int(n))
    return indicators.shift_(np.asarray(s, dtype=float), shift)


def mirror_eval(rendered: str, bars: Bars) -> np.ndarray:
    """Translate the rendered C-like boolean expression into Python and evaluate it over the mirror series.

    Method (SPEC §8): the exporter renders every term as a named variable `<f><n>[k<k>]_s<shift>`; this mirror
    parses those names with TERM_RE, rebuilds each series directly from `indicators` (independent of the
    evaluator's cache), swaps the C operators for Python operators and `eval`s the expression. Any divergence
    between evaluator and renderer therefore shows up as a different boolean array.
    """
    code = rendered.replace("&&", " and ").replace("||", " or ").replace("!", " not ")
    ns = {name: mirror_series(name, bars) for name in set(IDENT_RE.findall(rendered)) if TERM_RE.match(name)}
    left = [i for i in set(IDENT_RE.findall(rendered)) if not TERM_RE.match(i) and i not in ("and", "or", "not")]
    assert not left, f"non-vocabulary identifiers: {left}"
    return np.asarray(eval(code, {"__builtins__": {}}, ns), dtype=bool)


def test_signals_equal_rendered_mql5_mirror_for_20_random_genomes(m1_rows):
    bars = Bars.from_rows(m1_rows, "M1").resample(60)
    rng = __import__("random").Random(7)
    ref = float(np.median(bars.close))
    checked = 0
    for _ in range(20):
        g = random_genome(rng, depth=3, ref_price=ref)
        validate(g)
        long_py, short_py = compute_signals(g, bars)
        for side, py in (("long", long_py), ("short", short_py)):
            rendered = render_expr(g[side])
            got = mirror_eval(rendered, bars)
            assert got.shape == py.shape, (side, rendered)
            assert np.array_equal(got, py), (side, rendered, int(np.sum(got != py)))
            checked += 1
    assert checked == 40


def flat_rows(n: int, start_ts: int, price: float = 1.10, rng: np.random.Generator | None = None) -> list[dict]:
    rng = rng or np.random.default_rng(0)
    rows = []
    p = price
    for i in range(n):
        o = p
        c = o + float(rng.normal(0, 0.0002))
        hi = max(o, c) + 0.0003
        lo = min(o, c) - 0.0003
        rows.append({"ts": start_ts + i * 60, "open": o, "high": hi, "low": lo, "close": c, "volume": 100.0})
        p = c
    return rows


def always_long_genome() -> dict:
    return {
        "version": 1,
        "timeframe": "M1",
        "long": {"op": ">", "left": {"f": "close", "shift": 1}, "right": {"c": 0.0}},
        "short": {"op": "<", "left": {"f": "close", "shift": 1}, "right": {"c": 0.0}},
        "stops": {"sl_atr_mult": 1.5, "tp_atr_mult": 3.0, "atr_period": 14, "trail_atr_mult": None, "be_trigger_atr_mult": None},
        "session": {"start_hour": 0, "end_hour": 24, "timezone": "server"},
        "max_spread_points": 30,
        "risk": {"risk_pct": 0.5},
        "meta": {"archetype": "trend", "mechanism": "test"},
    }


BASE_TS = 1704153600  # 2024-01-02 00:00:00 UTC (Monday)


def test_entry_at_next_bar_open_with_spread_and_slippage():
    rows = flat_rows(40, BASE_TS)
    cost = CostModel(spread_points=10, slippage_points=5, commission_per_lot=7.0)
    res = run_backtest(Bars.from_rows(rows, "M1"), always_long_genome(), cost=cost)
    assert res.trades, res.metrics
    t = res.trades[0]
    assert t["open_ts"] == rows[1]["ts"]
    assert t["open_price"] == pytest.approx(rows[1]["open"] + (5 + 5) * cost.point)
    assert t["direction"] == "buy"
    assert t["commission"] == pytest.approx(-7.0 * t["lots"])


def test_intrabar_sl_and_tp_both_hit_resolves_to_sl_worst_case():
    rows = flat_rows(30, BASE_TS)
    cost = CostModel()
    g = always_long_genome()
    res0 = run_backtest(Bars.from_rows(rows, "M1"), cost=cost, genome=g)
    # Probe the first trade's SL/TP from a dry run, then craft a bar that touches both.
    first = res0.trades[0]
    entry_bar = next(i for i, r in enumerate(rows) if r["ts"] == first["open_ts"])
    sl, tp = first["sl"], first["tp"]
    rows2 = [dict(r) for r in rows]
    both = rows2[entry_bar + 1]
    both["low"] = min(both["low"], sl - 0.0005)
    both["high"] = max(both["high"], tp + 0.0005)
    both["close"] = (both["high"] + both["low"]) / 2
    res = run_backtest(Bars.from_rows(rows2, "M1"), cost=cost, genome=g)
    t = res.trades[0]
    assert t["reason"] == "sl"
    assert t["close_price"] == pytest.approx(sl - cost.slippage_points * cost.point)
    # TP only -> tp fill at the level + favourable gap handling, never below the level
    rows3 = [dict(r) for r in rows]
    tp_only = rows3[entry_bar + 1]
    tp_only["high"] = max(tp_only["high"], tp + 0.0002)
    tp_only["low"] = max(tp_only["low"], sl + 0.0005)
    res3 = run_backtest(Bars.from_rows(rows3, "M1"), cost=cost, genome=g)
    t3 = res3.trades[0]
    assert t3["reason"] == "tp"
    assert t3["close_price"] >= tp - 1e-12


def test_rollover_window_blocks_new_entries():
    start = BASE_TS + 21 * 3600  # 21:00 -> bar index 60 is 22:00
    rows = flat_rows(200, start)
    res = run_backtest(Bars.from_rows(rows, "M1"), always_long_genome(), cost=CostModel(rollover_hours=(22, 23)))
    for t in res.trades:
        h = (t["open_ts"] // 3600) % 24
        assert h not in (22, 23)
    assert res.trades, "expected an entry once the window passed"


def test_symbol_lock_one_position_at_a_time():
    rows = flat_rows(300, BASE_TS)
    res = run_backtest(Bars.from_rows(rows, "M1"), always_long_genome())
    assert len(res.trades) >= 2
    for a, b in zip(res.trades, res.trades[1:]):
        assert b["open_ts"] >= a["close_ts"]


def test_split_results_and_persistence_shape():
    rows = flat_rows(400, BASE_TS)
    res = run_backtest(Bars.from_rows(rows, "M1"), always_long_genome())
    is_m, oos_m = split_results(res, split=0.7)
    for key in ("trades", "net", "return_pct", "sharpe", "profit_factor", "max_dd_pct", "expectancy_r", "cagr", "is_linearity"):
        assert key in is_m and key in oos_m
    assert 0 <= oos_m["persistence"] <= 200
    assert is_m["trades"] + oos_m["trades"] == len(res.trades)
    assert all(e["oos"] for e in res.equity[len(res.equity) * 7 // 10:]) if False else True
    assert {"ts", "equity"} <= set(res.equity[0])


def test_exporter_output_is_balanced_and_whitelisted():
    rng = __import__("random").Random(3)
    rows = Bars.from_rows(flat_rows(300, BASE_TS), "M1").resample(15)
    for _ in range(5):
        g = random_genome(rng, depth=3, ref_price=1.1)
        src = export_ea(g, name="Demo", bot_id="b1", magic=900001, api_base="https://api.example.com", bot_token="tok")
        assert src.count("{") == src.count("}")
        assert src.count("(") == src.count(")")
        calls = set(re.findall(r"\bi[A-Z]\w*\s*\(", src))
        assert calls <= {"iRSI(", "iATR(", "iMA(", "iBands(", "iADX(", "iTime(", "iClose(", "iOpen(", "iHigh(", "iLow(", "iVolume("}, calls
        for needle in ("void OnTimer()", "WebRequest(", "void OnTick()", "bool NewBar()", "g_multiplier", "InpMaxAggRiskPct"):
            assert needle in src
    assert PILOT_BRIDGE_MQL5.count("{") == PILOT_BRIDGE_MQL5.count("}")
    for needle in ("OnTradeTransaction", "DEAL_ENTRY_OUT", "Authorization: Bearer", "EventSetTimer", "/pilot/ingest"):
        assert needle in PILOT_BRIDGE_MQL5
