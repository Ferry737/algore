"""Indicator series on numpy arrays. NaN-safe, no lookahead (every value uses bars up to and including t only).

CLEAN-ROOM DESIGN. Wilder-style smoothing via pandas ewm(alpha=1/n, adjust=False); warmup bars are NaN.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def shift_(x: np.ndarray, s: int) -> np.ndarray:
    """x shifted forward by s bars (out[t] = x[t-s]); the first s values are NaN."""
    x = np.asarray(x, dtype=np.float64)
    if s <= 0:
        return x.copy()
    out = np.full(x.shape, np.nan)
    out[s:] = x[:-s]
    return out


def _ewm(x: np.ndarray, alpha: float) -> np.ndarray:
    # pandas may hand back a read-only view; indicator callers write warmup NaNs into it.
    values = pd.Series(x, dtype="float64").ewm(alpha=alpha, adjust=False).mean().to_numpy()
    return np.array(values, dtype=np.float64, copy=True)


def sma(x: np.ndarray, n: int) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    n = max(1, int(n))
    out = np.full(x.shape, np.nan)
    if x.size >= n:
        c = np.cumsum(np.insert(x, 0, 0.0))
        out[n - 1:] = (c[n:] - c[:-n]) / n
    return out


def ema(x: np.ndarray, n: int) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    n = max(1, int(n))
    out = _ewm(x, 2.0 / (n + 1.0))
    out[: min(n - 1, x.size)] = np.nan
    return out


def rsi(close: np.ndarray, n: int) -> np.ndarray:
    c = np.asarray(close, dtype=np.float64)
    n = max(2, int(n))
    delta = np.diff(c, prepend=c[:1])
    gain = np.clip(delta, 0.0, None)
    loss = np.clip(-delta, 0.0, None)
    ag = _ewm(gain, 1.0 / n)
    al = _ewm(loss, 1.0 / n)
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = ag / al
        out = 100.0 - 100.0 / (1.0 + rs)
        out = np.where((al == 0) & (ag > 0), 100.0, out)
        out = np.where((al == 0) & (ag == 0), 50.0, out)
    out[: min(n, c.size)] = np.nan
    return out


def true_range(h: np.ndarray, l: np.ndarray, c: np.ndarray) -> np.ndarray:
    pc = np.roll(c, 1)
    pc[0] = c[0] if c.size else 0.0
    return np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))


def atr(h: np.ndarray, l: np.ndarray, c: np.ndarray, n: int) -> np.ndarray:
    n = max(1, int(n))
    out = _ewm(true_range(np.asarray(h, dtype=np.float64), np.asarray(l, dtype=np.float64), np.asarray(c, dtype=np.float64)), 1.0 / n)
    out[: min(n, out.size)] = np.nan
    return out


def bb_pos(close: np.ndarray, n: int, k: float = 2.0) -> np.ndarray:
    """Position inside Bollinger bands: (close - sma) / (k * std). 0 when the band width is zero.

    `k` is an integer band-width multiplier; quantising here keeps the Python evaluator and
    the rendered MQL5 term name (`bbpos<n>k<k>_s<shift>`) bit-for-bit identical.
    """
    k = max(1, int(round(float(k))))
    c = np.asarray(close, dtype=np.float64)
    n = max(2, int(n))
    mid = sma(c, n)
    std = pd.Series(c).rolling(n).std(ddof=0).to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        out = (c - mid) / (float(k) * std)
        out = np.where(std <= 0, 0.0, out)
    out[: min(n - 1, c.size)] = np.nan
    return out


def adx(h: np.ndarray, l: np.ndarray, c: np.ndarray, n: int) -> np.ndarray:
    n = max(2, int(n))
    h, l, c = (np.asarray(a, dtype=np.float64) for a in (h, l, c))
    up = np.diff(h, prepend=h[:1])
    dn = -np.diff(l, prepend=l[:1])
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = _ewm(true_range(h, l, c), 1.0 / n)
    with np.errstate(divide="ignore", invalid="ignore"):
        plus_di = 100.0 * _ewm(plus_dm, 1.0 / n) / tr
        minus_di = 100.0 * _ewm(minus_dm, 1.0 / n) / tr
        dx = 100.0 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
    dx = np.where(np.isnan(dx), 0.0, dx)
    out = _ewm(dx, 1.0 / n)
    out[: min(n * 2, out.size)] = np.nan
    return out


def ret(x: np.ndarray, n: int) -> np.ndarray:
    """n-bar simple return x[t]/x[t-n] - 1."""
    x = np.asarray(x, dtype=np.float64)
    n = max(1, int(n))
    out = np.full(x.shape, np.nan)
    if x.size > n:
        with np.errstate(divide="ignore", invalid="ignore"):
            out[n:] = x[n:] / x[:-n] - 1.0
    return out
