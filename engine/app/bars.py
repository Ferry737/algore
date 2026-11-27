"""OHLCV bar container (numpy) with timeframe parsing, M1→TF resampling and strict ts slicing."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

import numpy as np

_TF_RE = re.compile(r"^([MHD])(\d+)$")


def timeframe_minutes(tf: str) -> int:
    """'M1'→1, 'H1'→60, 'D1'→1440. Raises ValueError for anything else."""
    m = _TF_RE.match((tf or "").strip().upper())
    if not m:
        raise ValueError(f"unknown timeframe {tf!r}")
    unit, n = m.group(1), int(m.group(2))
    return n * {"M": 1, "H": 60, "D": 1440}[unit]


@dataclass
class Bars:
    ts: np.ndarray
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    timeframe: str = ""
    symbol: str = ""

    def __post_init__(self) -> None:
        self.ts = np.ascontiguousarray(self.ts, dtype=np.int64)
        for name in ("open", "high", "low", "close", "volume"):
            setattr(self, name, np.ascontiguousarray(getattr(self, name), dtype=np.float64))
        if self.ts.size and np.any(np.diff(self.ts) < 0):
            order = np.argsort(self.ts, kind="stable")
            self.ts = self.ts[order]
            for name in ("open", "high", "low", "close", "volume"):
                setattr(self, name, getattr(self, name)[order])

    @classmethod
    def empty(cls, timeframe: str = "", symbol: str = "") -> "Bars":
        z = np.zeros(0)
        return cls(ts=z.astype(np.int64), open=z, high=z, low=z, close=z, volume=z, timeframe=timeframe, symbol=symbol)

    @classmethod
    def from_rows(cls, rows: Iterable[dict | tuple], timeframe: str = "", symbol: str = "") -> "Bars":
        ts, o, h, l, c, v = [], [], [], [], [], []
        for r in rows:
            if isinstance(r, dict):
                ts.append(int(r["ts"])); o.append(float(r["open"])); h.append(float(r["high"]))
                l.append(float(r["low"])); c.append(float(r["close"])); v.append(float(r.get("volume") or 0.0))
            else:
                ts.append(int(r[0])); o.append(float(r[1])); h.append(float(r[2])); l.append(float(r[3])); c.append(float(r[4]))
                v.append(float(r[5]) if len(r) > 5 and r[5] is not None else 0.0)
        return cls(ts=np.array(ts, dtype=np.int64), open=np.array(o), high=np.array(h), low=np.array(l),
                   close=np.array(c), volume=np.array(v), timeframe=timeframe, symbol=symbol)

    def __len__(self) -> int:
        return int(self.ts.size)

    @property
    def n(self) -> int:
        return int(self.ts.size)

    @property
    def hours(self) -> np.ndarray:
        return ((self.ts // 3600) % 24).astype(np.float64)

    @property
    def dows(self) -> np.ndarray:
        # MQL5 convention: Sunday = 0 (epoch day 0 was a Thursday -> 4).
        return (((self.ts // 86400) + 4) % 7).astype(np.float64)

    def minutes(self) -> int:
        """Bar length in minutes: from the timeframe label when present, else the median gap."""
        if self.timeframe:
            try:
                return timeframe_minutes(self.timeframe)
            except ValueError:
                pass
        if self.ts.size > 1:
            return max(1, int(np.median(np.diff(self.ts)) // 60))
        return 1

    def resample(self, minutes: int) -> "Bars":
        """Build higher-timeframe bars: O=first, H=max, L=min, C=last, V=sum per bucket (ts = bucket open)."""
        if minutes <= 1 or self.ts.size == 0:
            return Bars(self.ts.copy(), self.open.copy(), self.high.copy(), self.low.copy(), self.close.copy(),
                        self.volume.copy(), timeframe=self.timeframe or "M1", symbol=self.symbol)
        bucket = self.ts // (minutes * 60)
        _, starts = np.unique(bucket, return_index=True)
        ends = np.append(starts[1:], self.ts.size) - 1
        return Bars(
            ts=bucket[starts] * minutes * 60,
            open=self.open[starts],
            high=np.maximum.reduceat(self.high, starts),
            low=np.minimum.reduceat(self.low, starts),
            close=self.close[ends],
            volume=np.add.reduceat(self.volume, starts),
            timeframe=f"M{minutes}" if minutes < 60 else (f"H{minutes // 60}" if minutes % 60 == 0 else f"M{minutes}"),
            symbol=self.symbol,
        )

    def slice(self, start: int, end: int | None = None) -> "Bars":
        """Index-based copy [start, end)."""
        end = self.ts.size if end is None else end
        return Bars(self.ts[start:end].copy(), self.open[start:end].copy(), self.high[start:end].copy(),
                    self.low[start:end].copy(), self.close[start:end].copy(), self.volume[start:end].copy(),
                    timeframe=self.timeframe, symbol=self.symbol)

    def after_ts(self, trained_until: int) -> "Bars":
        """Replay fast-track window: only bars with ts STRICTLY greater than trained_until (no lookahead)."""
        start = int(np.searchsorted(self.ts, trained_until, side="right"))
        return self.slice(start)

    def rows(self) -> list[dict]:
        return [{"ts": int(t), "open": float(o), "high": float(h), "low": float(l), "close": float(c), "volume": float(v)}
                for t, o, h, l, c, v in zip(self.ts, self.open, self.high, self.low, self.close, self.volume)]
