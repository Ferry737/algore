"""Parity backtester — SPEC §2.2. CLEAN-ROOM DESIGN (event-driven, bar-by-bar).

Fills resolve on M1 OHLC sub-bars (never ticks). Inside one sub-bar the path is bullish O→L→H→C / bearish
O→H→L→C (INFERRED from MT5's 1-minute-OHLC model) and, worst-case first, SL is checked before TP whenever both
lie inside the same sub-bar (CONFIRMED CAM-10: M1 sub-bars; ordering ours).
Entry at the next bar's open ± half spread + slippage; commission per lot; rollover window blocks new entries and
charges swap; Symbol Lock (one position per bot); daily loss limit / optional daily profit stop; lots sized from
risk_money = equity × risk_pct × multiplier over the SL distance.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np

from . import indicators
from .bars import Bars
from .evaluator import SeriesCache, compute_signals
from .genome import validate


def iso(ts: int) -> str:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class CostModel:
    """Per-symbol trading costs. FX 5-digit defaults; for_symbol() adjusts JPY and XAU quotes."""

    symbol: str = "EURUSD"
    point: float = 0.00001
    tick_size: float = 0.00001
    tick_value: float = 1.0
    spread_points: float = 10.0
    slippage_points: float = 5.0
    commission_per_lot: float = 7.0  # round-turn, positive = cost
    swap_long: float = -2.5  # money per lot per rollover (negative = charge)
    swap_short: float = -0.5
    rollover_hours: tuple[int, ...] = (22, 23)
    daily_loss_pct: float = 4.0
    daily_profit_stop_pct: float | None = None
    min_lot: float = 0.01
    max_lot: float = 50.0
    lot_step: float = 0.01

    @property
    def money_per_unit(self) -> float:
        """Account currency per 1.0 price move per lot = tick_value / tick_size."""
        return self.tick_value / self.tick_size if self.tick_size else 0.0

    @classmethod
    def for_symbol(cls, symbol: str) -> "CostModel":
        s = (symbol or "EURUSD").upper()
        if "JPY" in s:
            return cls(symbol=s, point=0.001, tick_size=0.001, tick_value=0.65, spread_points=15.0, slippage_points=8.0)
        if "XAU" in s:
            return cls(symbol=s, point=0.01, tick_size=0.01, tick_value=1.0, spread_points=30.0, slippage_points=10.0)
        return cls(symbol=s)


@dataclass
class BacktestResult:
    trades: list[dict[str, Any]]
    equity: list[dict[str, Any]]
    metrics: dict[str, Any]
    bars_ts: np.ndarray
    oos_start_ts: int | None = None
    minutes: int = 60
    start_equity: float = 10000.0

    @property
    def trade_count(self) -> int:
        return len(self.trades)

    def equity_with_oos(self) -> list[dict[str, Any]]:
        """Equity points tagged with oos=True/False (passport curve, OOS in blue — CAM-15)."""
        start = self.oos_start_ts if self.oos_start_ts is not None else 2**62
        return [{"ts": int(e["ts"]), "equity": float(e["equity"]), "oos": bool(int(e["ts"]) >= start)} for e in self.equity]


class _Position:
    __slots__ = ("dir", "lots", "open_price", "open_ts", "sl", "tp", "atr", "sl_dist", "commission", "swap", "last_swap_day", "be_done")

    def __init__(self, dir_: int, lots: float, open_price: float, open_ts: int, sl: float, tp: float, atr_: float,
                 sl_dist: float, commission: float) -> None:
        self.dir, self.lots, self.open_price, self.open_ts = dir_, lots, open_price, open_ts
        self.sl, self.tp, self.atr, self.sl_dist = sl, tp, atr_, sl_dist
        self.commission, self.swap, self.last_swap_day, self.be_done = commission, 0.0, -1, False

    def floating(self, mark: float, mpu: float) -> float:
        return self.dir * (mark - self.open_price) * self.lots * mpu


def _session_ok(hour: int, start: int, end: int) -> bool:
    return (start <= hour < end) if start <= end else (hour >= start or hour < end)


def size_lots(risk_money: float, sl_dist: float, mpu: float, cost: CostModel) -> float:
    """lots = risk_money / (sl_dist × tick_value / tick_size), rounded down to lot step, min/max enforced."""
    if sl_dist <= 0 or mpu <= 0 or risk_money <= 0:
        return 0.0
    step = cost.lot_step or 0.01
    lots = math.floor(risk_money / (sl_dist * mpu) / step + 1e-9) * step
    return round(min(cost.max_lot, max(cost.min_lot, lots)), 4)


def _close_trade(trades: list[dict[str, Any]], pos: _Position, fill: float, ts: int, reason: str, mpu: float) -> float:
    profit = pos.dir * (fill - pos.open_price) * pos.lots * mpu
    risk_money = pos.sl_dist * pos.lots * mpu
    net = profit + pos.commission + pos.swap
    trades.append({
        "direction": "buy" if pos.dir > 0 else "sell", "lots": pos.lots,
        "open_time": iso(pos.open_ts), "close_time": iso(ts),
        "open_price": pos.open_price, "close_price": fill,
        "profit": profit, "commission": pos.commission, "swap": pos.swap,
        "sl": pos.sl, "tp": pos.tp, "reason": reason,
        "r_multiple": net / risk_money if risk_money > 0 else 0.0,
        "open_ts": pos.open_ts, "close_ts": ts, "net": net,
    })
    return profit + pos.swap


def run_backtest(bars: Bars, genome: dict, cost: CostModel | None = None, m1_bars: Bars | None = None,
                 multiplier: float = 1.0, start_equity: float = 10000.0, sc: SeriesCache | None = None) -> BacktestResult:
    """Run one genome over TF `bars`, resolving fills on `m1_bars` when given (else on the TF bars)."""
    cost = cost or CostModel.for_symbol(bars.symbol)
    validate(genome)
    n = len(bars)
    if n < 3:
        return BacktestResult([], [{"ts": int(bars.ts[0]) if n else 0, "equity": start_equity}] if n else [],
                              compute_metrics([], [], start_equity, bars.minutes()), bars.ts.copy(), minutes=bars.minutes(),
                              start_equity=start_equity)
    long_sig, short_sig = compute_signals(genome, bars, sc)
    stops, sess = genome["stops"], genome["session"]
    risk_pct = float(genome["risk"]["risk_pct"])
    atr_series = indicators.atr(bars.high, bars.low, bars.close, int(stops["atr_period"]))
    tf_min = bars.minutes()
    use_m1 = m1_bars is not None and len(m1_bars) > 0
    sub_ts, sub_o, sub_h, sub_l, sub_c = ((m1_bars.ts, m1_bars.open, m1_bars.high, m1_bars.low, m1_bars.close)
                                          if use_m1 else (bars.ts, bars.open, bars.high, bars.low, bars.close))
    starts = np.searchsorted(sub_ts, bars.ts, side="left")
    ends = np.append(starts[1:], np.searchsorted(sub_ts, int(bars.ts[-1]) + tf_min * 60, side="left"))
    half_spread = cost.spread_points * cost.point / 2.0
    slip = cost.slippage_points * cost.point
    mpu = cost.money_per_unit
    rollover = {int(h) for h in cost.rollover_hours}
    sess_start, sess_end = int(sess["start_hour"]), int(sess["end_hour"])
    trail, be_trig = stops.get("trail_atr_mult"), stops.get("be_trigger_atr_mult")
    sl_mult, tp_mult = float(stops["sl_atr_mult"]), stops.get("tp_atr_mult")
    max_spread = float(genome.get("max_spread_points", 1e9))

    trades: list[dict[str, Any]] = []
    equity_curve: list[dict[str, Any]] = []
    realised = 0.0
    pos: _Position | None = None
    cur_day, day_start_eq, day_blocked = -1, start_equity, False

    for i in range(n):
        ts_i = int(bars.ts[i])
        s0, s1 = int(starts[i]), int(ends[i])
        has_sub = s0 < s1
        if pos is not None:
            eq_open = start_equity + realised + pos.floating(sub_o[s0] if has_sub else bars.open[i], mpu)
        else:
            eq_open = start_equity + realised
        day = ts_i // 86400
        if day != cur_day:
            cur_day, day_start_eq, day_blocked = day, eq_open, False
        a_tr = float(atr_series[i - 1]) if i >= 1 else float("nan")
        if not math.isfinite(a_tr) or a_tr <= 0:  # ATR warmup: use the prior bar's true range
            j = max(0, i - 1)
            a_tr = float(bars.high[j] - bars.low[j])
            if not math.isfinite(a_tr) or a_tr <= 0:
                a_tr = abs(float(bars.close[j])) * 0.001
        # ---- manage an open position on the sub-bars of this TF bar
        if pos is not None:
            for j in range(s0, s1):
                o, h, l, c, tsj = float(sub_o[j]), float(sub_h[j]), float(sub_l[j]), float(sub_c[j]), int(sub_ts[j])
                d = tsj // 86400
                if (tsj // 3600) % 24 in rollover and pos.last_swap_day != d:
                    pos.swap += (cost.swap_long if pos.dir > 0 else cost.swap_short) * pos.lots
                    pos.last_swap_day = d
                if pos.dir > 0:
                    sl_hit, tp_hit = l <= pos.sl, (pos.tp > 0 and h >= pos.tp)
                else:
                    sl_hit, tp_hit = h >= pos.sl, (pos.tp > 0 and l <= pos.tp)
                if sl_hit or tp_hit:  # SL wins whenever both lie inside one sub-bar (worst case first)
                    if sl_hit:
                        reason, fill = "sl", (min(o, pos.sl) if pos.dir > 0 else max(o, pos.sl)) - pos.dir * slip
                    else:
                        # TP fills sit AT the level, with favourable gap handling; no adverse slippage.
                        reason, fill = "tp", (max(o, pos.tp) if pos.dir > 0 else min(o, pos.tp))
                    realised += _close_trade(trades, pos, fill, tsj, reason, mpu)
                    pos = None
                    break
                if math.isfinite(a_tr) and a_tr > 0:
                    if be_trig and not pos.be_done and pos.dir * (c - pos.open_price) >= float(be_trig) * a_tr:
                        pos.sl, pos.be_done = pos.open_price, True
                    if trail:
                        cand = c - pos.dir * float(trail) * a_tr
                        pos.sl = max(pos.sl, cand) if pos.dir > 0 else min(pos.sl, cand)
        # ---- entry at this bar's open (condition evaluated on the previous, closed bar)
        if pos is None and (long_sig[i] or short_sig[i]) and has_sub:
            hour = (ts_i // 3600) % 24
            eq_now = start_equity + realised
            if cost.daily_loss_pct > 0 and (eq_now - day_start_eq) <= -cost.daily_loss_pct / 100.0 * day_start_eq:
                day_blocked = True
            profit_stop = cost.daily_profit_stop_pct is not None and (eq_now - day_start_eq) >= cost.daily_profit_stop_pct / 100.0 * day_start_eq
            if (not day_blocked and not profit_stop and _session_ok(hour, sess_start, sess_end) and hour not in rollover
                    and cost.spread_points <= max_spread and math.isfinite(a_tr) and a_tr > 0):
                direction = 1 if long_sig[i] else -1
                fill = float(sub_o[s0]) + direction * (half_spread + slip)
                sl_dist = a_tr * sl_mult
                tp_dist = a_tr * float(tp_mult) if tp_mult else 0.0
                lots = size_lots(eq_now * risk_pct / 100.0 * multiplier, sl_dist, mpu, cost)
                if lots > 0:
                    commission = -cost.commission_per_lot * lots
                    pos = _Position(direction, lots, fill, int(sub_ts[s0]), fill - direction * sl_dist,
                                    fill + direction * tp_dist if tp_dist > 0 else 0.0, a_tr, sl_dist, commission)
                    realised += commission
        # ---- mark equity at the TF bar close
        mark = float(sub_c[s1 - 1]) if has_sub else float(bars.close[i])
        floating = pos.floating(mark, mpu) if pos is not None else 0.0
        equity_curve.append({"ts": ts_i, "equity": round(start_equity + realised + floating, 6)})

    if pos is not None:  # end of data: close at the last sub-bar close ± slippage
        last = len(sub_c) - 1
        realised += _close_trade(trades, pos, float(sub_c[last]) - pos.dir * slip, int(sub_ts[last]), "end", mpu)
        equity_curve[-1]["equity"] = round(start_equity + realised, 6)
    metrics = compute_metrics(trades, equity_curve, start_equity, tf_min)
    return BacktestResult(trades, equity_curve, metrics, bars.ts.copy(), minutes=tf_min, start_equity=start_equity)


def compute_metrics(trades: list[dict[str, Any]], curve: list[dict[str, Any]], start_equity: float, minutes: int) -> dict[str, Any]:
    """CONFIRMED metric set (CAM-21 passport): trades, net, return, Sharpe, PF, max DD, expectancy (R), CAGR, IS linearity."""
    nets = [float(t.get("net", t["profit"] + t["commission"] + t["swap"])) for t in trades]
    net = float(sum(nets))
    ret_pct = net / start_equity * 100.0 if start_equity else 0.0
    eq = np.array([float(e["equity"]) for e in curve], dtype=np.float64) if curve else np.array([start_equity])
    minutes = max(1, int(minutes))
    bars_per_year = 252.0 * 24.0 * 60.0 / minutes
    if eq.size > 1:
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.diff(eq) / eq[:-1]
        sd = float(np.std(r, ddof=1)) if r.size > 1 else 0.0
        sharpe = float(np.mean(r) / sd * math.sqrt(bars_per_year)) if sd > 0 else 0.0
    else:
        sharpe = 0.0
    peak = np.maximum.accumulate(eq)
    dd = np.where(peak > 0, (peak - eq) / peak, 0.0)
    max_dd_pct = float(np.max(dd) * 100.0) if dd.size else 0.0
    gp = float(sum(x for x in nets if x > 0))
    gl = float(-sum(x for x in nets if x < 0))
    if gl > 0:
        pf = gp / gl
    else:
        pf = 99.0 if gp > 0 else 0.0
    rs = [float(t["r_multiple"]) for t in trades]
    expectancy = float(np.mean(rs)) if rs else 0.0
    dd_money = max_dd_pct / 100.0 * start_equity
    recovery = (net / dd_money) if dd_money > 0 else (99.0 if net > 0 else 0.0)
    ts = [int(e["ts"]) for e in curve]
    years = (ts[-1] - ts[0]) / (365.25 * 86400.0) if len(ts) > 1 else 0.0
    growth = 1.0 + ret_pct / 100.0
    if years > 0 and growth > 0:
        cagr = (growth ** (1.0 / years) - 1.0) * 100.0
    else:
        cagr = 0.0
    if eq.size > 2 and float(np.std(eq)) > 0:
        x = np.arange(eq.size, dtype=np.float64)
        corr = float(np.corrcoef(x, eq)[0, 1]) if float(np.std(x)) > 0 else 0.0
        linearity = float(min(1.0, max(0.0, corr * corr)))
    else:
        linearity = 0.0
    wins = sum(1 for x in nets if x > 0)
    return {
        "trades": len(trades), "net": net, "return_pct": ret_pct, "sharpe": sharpe, "profit_factor": pf,
        "max_dd_pct": max_dd_pct, "expectancy_r": expectancy, "cagr": cagr, "is_linearity": linearity,
        "recovery": recovery, "wins": wins, "win_rate": (wins / len(trades) * 100.0) if trades else 0.0,
        "gross_profit": gp, "gross_loss": gl,
    }


def split_results(result: BacktestResult, split: float = 0.7) -> tuple[dict[str, Any], dict[str, Any]]:
    """IS = first `split` of the bars, OOS = the rest. Sets result.oos_start_ts and returns (is_metrics, oos_metrics).

    persistence = oos_expectancy_r / is_expectancy_r × 100, clipped to 0–200 (SPEC §2.1 / INFERRED definition).
    """
    n = len(result.bars_ts)
    k = min(max(1, int(n * split)), n - 1) if n > 1 else 0
    oos_ts = int(result.bars_ts[k]) if n > 1 else 0
    result.oos_start_ts = oos_ts
    is_trades = [t for t in result.trades if int(t["open_ts"]) < oos_ts]
    oos_trades = [t for t in result.trades if int(t["open_ts"]) >= oos_ts]
    is_curve, oos_curve = result.equity[: k + 1], result.equity[k:]
    is_m = compute_metrics(is_trades, is_curve, result.start_equity, result.minutes)
    oos_base = float(oos_curve[0]["equity"]) if oos_curve else result.start_equity
    oos_m = compute_metrics(oos_trades, oos_curve, oos_base, result.minutes)
    is_exp, oos_exp = float(is_m["expectancy_r"]), float(oos_m["expectancy_r"])
    oos_m["persistence"] = float(min(200.0, max(0.0, oos_exp / is_exp * 100.0))) if is_exp > 0 else 0.0
    oos_m["oos_bars"] = int(n - k)
    is_m["oos_bars"] = int(k)
    return is_m, oos_m


def evaluate_genome(bars: Bars, genome: dict, cost: CostModel, m1_bars: Bars | None = None, split: float = 0.7,
                    sc: SeriesCache | None = None) -> dict[str, Any]:
    """Backtest + split in one call. Returns JSON-friendly dict (no numpy) for inter-process transfer."""
    res = run_backtest(bars, genome, cost, m1_bars, sc=sc)
    is_m, oos_m = split_results(res, split)
    return {
        "is": is_m, "oos": oos_m, "trades": len(res.trades), "oos_start_ts": res.oos_start_ts,
        "oos_nets": [float(t["net"]) for t in res.trades if int(t["open_ts"]) >= int(res.oos_start_ts or 0)],
    }
