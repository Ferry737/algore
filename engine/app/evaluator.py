"""Vectorised AST evaluation over bar arrays → boolean long/short signal arrays.

Module-level functions only in the hot path so ProcessPool workers can call them. Signals are shifted by one bar:
a condition true on bar t (using closed bars only, shift >= 1) fires on bar t+1 (entry at its open).
"""
from __future__ import annotations

import functools
from typing import Any

import numpy as np

from . import indicators
from .bars import Bars
from .genome import ALL_FEATURES, CMP_OPS, CROSS_OPS, SLOPE_OPS

CacheKey = tuple[Any, ...]


class SeriesCache:
    """Lazily computes and memoises feature series for one Bars object (shared across many genomes)."""

    def __init__(self, bars: Bars) -> None:
        self.bars = bars
        self._cache: dict[CacheKey, np.ndarray] = {}

    def series(self, term: dict) -> np.ndarray:
        if "c" in term:
            return np.full(self.bars.n, float(term["c"]))
        f = term["f"]
        shift = int(term.get("shift", 1))
        if f in ("rsi", "atr", "ema", "sma", "bb_pos", "adx", "ret"):
            key: CacheKey = (f, int(term["n"]), float(term.get("k", 2.0)) if f == "bb_pos" else None)
        else:
            key = (f,)
        base = self._cache.get(key)
        if base is None:
            base = self._compute(key)
            self._cache[key] = base
        return indicators.shift_(base, shift)

    def _compute(self, key: CacheKey) -> np.ndarray:
        f = key[0]
        b = self.bars
        if f in ("open", "high", "low", "close", "volume"):
            return getattr(b, f)
        if f == "hour":
            return b.hours
        if f == "dow":
            return b.dows
        n = int(key[1])
        if f == "rsi":
            return indicators.rsi(b.close, n)
        if f == "atr":
            return indicators.atr(b.high, b.low, b.close, n)
        if f == "ema":
            return indicators.ema(b.close, n)
        if f == "sma":
            return indicators.sma(b.close, n)
        if f == "bb_pos":
            return indicators.bb_pos(b.close, n, float(key[2] or 2.0))
        if f == "adx":
            return indicators.adx(b.high, b.low, b.close, n)
        if f == "ret":
            return indicators.ret(b.close, n)
        raise ValueError(f"unknown feature {f!r}")


_CMP = {">": np.greater, "<": np.less, ">=": np.greater_equal, "<=": np.less_equal}


def eval_expr(expr: dict, sc: SeriesCache) -> np.ndarray:
    """Evaluate one §7 expression into a boolean array aligned with the bars (NaN comparisons are False)."""
    op = expr["op"]
    if op == "and":
        return functools.reduce(np.logical_and, (eval_expr(a, sc) for a in expr["args"]))
    if op == "or":
        return functools.reduce(np.logical_or, (eval_expr(a, sc) for a in expr["args"]))
    if op == "not":
        return ~eval_expr(expr["arg"], sc)
    if op in CMP_OPS:
        return _CMP[op](sc.series(expr["left"]), sc.series(expr["right"]))
    if op in CROSS_OPS:
        a, b = sc.series(expr["left"]), sc.series(expr["right"])
        pa, pb = indicators.shift_(a, 1), indicators.shift_(b, 1)
        return (a > b) & (pa <= pb) if op == "cross_up" else (a < b) & (pa >= pb)
    if op in SLOPE_OPS:
        x = sc.series(expr["arg"])
        ok = np.ones(x.shape, dtype=bool)
        for i in range(int(expr.get("lookback", 2))):
            a, b = indicators.shift_(x, i), indicators.shift_(x, i + 1)
            ok &= (a > b) if op == "rising" else (a < b)
        return ok
    raise ValueError(f"unknown op {op!r}")


def fire_next_bar(condition: np.ndarray) -> np.ndarray:
    """Return the condition array aligned to the bar whose open receives the entry.

    Every §7 term already applies ``shift >= 1`` (closed bars only), so the condition at
    index t is computed from data available at t's close and fires at t's next bar open.
    An additional shift would double-count that delay and break the MQL5 mirror.
    """
    return np.asarray(condition, dtype=bool).copy()


def compute_signals(genome: dict, bars: Bars, sc: SeriesCache | None = None) -> tuple[np.ndarray, np.ndarray]:
    """(long, short) boolean arrays; True at index i means 'enter at the open of bar i'."""
    sc = sc or SeriesCache(bars)
    return fire_next_bar(eval_expr(genome["long"], sc)), fire_next_bar(eval_expr(genome["short"], sc))


def evaluate_signals(bars: Bars, genome: dict) -> tuple[np.ndarray, np.ndarray]:
    """Top-level pure entry point (importable by ProcessPool workers)."""
    return compute_signals(genome, bars)


__all__ = ["SeriesCache", "eval_expr", "compute_signals", "evaluate_signals", "fire_next_bar", "ALL_FEATURES"]
