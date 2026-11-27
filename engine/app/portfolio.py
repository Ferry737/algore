"""Portfolio sizing — SPEC §2.4. CONFIRMED arithmetic (POR-03..06); decorrelation scaling is CLEAN-ROOM DESIGN.

Canonical sizing modes: `equal_heat` (risk_per_bot = target_heat ÷ (distinct symbols | bots)) and `variance_scaled`
(on top of equal heat: daily-return Pearson matrix, avg_corr floored at 0, d = 1/(avg_corr + 0.10),
scale = clip(d / mean(d), 0.5, 1.5), renormalised to the target heat). `heat` and `decorrelated` are accepted aliases.
Variance sizer fallback: fewer than MIN_OVERLAPPING_RETURNS overlapping daily returns or a zero-variance member →
every scale = 1.0 and risk = target_heat ÷ n_concurrent, reported via sizing_fallback / sizing_fallback_reason.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

EQUAL_HEAT = "equal_heat"
VARIANCE_SCALED = "variance_scaled"
SIZING_ALIASES: dict[str, str] = {
    "heat": EQUAL_HEAT, "equal_heat": EQUAL_HEAT, "equal": EQUAL_HEAT,
    "decorrelated": VARIANCE_SCALED, "variance_scaled": VARIANCE_SCALED, "variance": VARIANCE_SCALED,
}
MIN_OVERLAPPING_RETURNS = 30


def canonical_mode(mode: str | None) -> str:
    key = (mode or EQUAL_HEAT).strip().lower()
    if key not in SIZING_ALIASES:
        raise ValueError(f"unknown sizing_mode {mode!r} (equal_heat | variance_scaled; aliases heat | decorrelated)")
    return SIZING_ALIASES[key]


@dataclass
class Member:
    strategy_id: str
    symbol: str
    curve: list[tuple[int, float]] | None = None  # [(ts, equity)] daily-or-finer
    bot_id: str | None = None


@dataclass
class PortfolioSizing:
    sizing_mode: str
    members: list[dict[str, Any]]
    heat: float
    health: dict[str, Any]
    correlation_matrix: dict[str, Any]
    concurrent: int
    sizing_fallback: bool = False
    sizing_fallback_reason: str | None = None
    base_risk_pct: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sizing_mode": self.sizing_mode, "members": self.members, "heat": self.heat, "health": self.health,
            "correlation_matrix": self.correlation_matrix, "concurrent": self.concurrent,
            "sizing_fallback": self.sizing_fallback, "sizing_fallback_reason": self.sizing_fallback_reason,
            "base_risk_pct": self.base_risk_pct, **self.extra,
        }

    # Mapping-style access is part of the public API (callers use both attribute and [] access).
    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def keys(self):
        return self.to_dict().keys()

    def items(self):
        return self.to_dict().items()

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(key, default)

    def __contains__(self, key: object) -> bool:
        return key in self.to_dict()


def daily_returns(curve: Sequence[tuple[int, float]]) -> tuple[np.ndarray, np.ndarray]:
    """Last equity per UTC day → (day index, daily pct return)."""
    if not curve:
        return np.zeros(0, dtype=np.int64), np.zeros(0)
    arr = np.asarray(curve, dtype=np.float64)
    days = (arr[:, 0].astype(np.int64) // 86400)
    last_day, last_eq = [], []
    for d, e in zip(days, arr[:, 1]):
        if last_day and d == last_day[-1]:
            last_eq[-1] = e
        else:
            last_day.append(int(d))
            last_eq.append(float(e))
    eq = np.asarray(last_eq)
    if eq.size < 2:
        return np.asarray(last_day[1:], dtype=np.int64), np.zeros(0)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.diff(eq) / eq[:-1]
    return np.asarray(last_day[1:], dtype=np.int64), r


def _corr_matrix(rets: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        c = np.corrcoef(rets)
    return np.nan_to_num(c, nan=0.0)


def size_portfolio(members: Sequence[Member], target_heat_pct: float, symbol_lock: bool = True, sizing_mode: str = EQUAL_HEAT) -> PortfolioSizing:
    """Compute per-member risk. Σ risk_pct == target_heat_pct in every non-fallback and fallback path."""
    mode = canonical_mode(sizing_mode)
    n = len(members)
    if n == 0:
        return PortfolioSizing(mode, [], 0.0, {"distinct_symbols": 0, "max_symbol_exposure": 0.0, "avg_member_corr": 0.0},
                               {"labels": [], "matrix": []}, 0, False, None, 0.0)
    symbols = sorted({m.symbol for m in members})
    concurrent = len(symbols) if symbol_lock else n
    base = float(target_heat_pct) / concurrent
    labels = [m.strategy_id for m in members]
    scales = [1.0] * n
    avg_corr = [0.0] * n
    fallback, reason = False, None
    matrix = np.eye(n)
    if mode == VARIANCE_SCALED:
        daily = [daily_returns(m.curve) for m in members]
        if n < 2:
            fallback, reason = True, "fewer than 2 members: nothing to decorrelate"
        elif any(d.size == 0 for d, _ in daily):
            fallback, reason = True, "a member has no daily-return observations"
        else:
            common = set.intersection(*[set(d.tolist()) for d, _ in daily])
            if len(common) < MIN_OVERLAPPING_RETURNS:
                fallback, reason = True, f"only {len(common)} overlapping daily returns (< {MIN_OVERLAPPING_RETURNS}) for a stable covariance matrix"
            else:
                days = sorted(common)
                rets = np.array([[r[list(d).index(day)] for day in days] for d, r in daily])
                var = rets.var(axis=1)
                if np.any(var <= 1e-18):
                    names = ", ".join(labels[i] for i in range(n) if var[i] <= 1e-18)
                    fallback, reason = True, f"zero-variance daily returns for member(s) {names}"
                else:
                    matrix = _corr_matrix(rets)
                    off = matrix.copy()
                    np.fill_diagonal(off, 0.0)
                    off = np.maximum(off, 0.0)
                    avg = off.sum(axis=1) / (n - 1)
                    d = 1.0 / (avg + 0.10)
                    scales = [float(np.clip(d[i] / float(np.mean(d)), 0.5, 1.5)) for i in range(n)]
                    avg_corr = [float(avg[i]) for i in range(n)]
    if fallback:
        scales, avg_corr = [1.0] * n, [0.0] * n
        risks = [float(target_heat_pct) / concurrent] * n
    else:
        risks = [base * s for s in scales]
        total = sum(risks)
        # Conserve total portfolio heat when return curves are available: two bots on one
        # symbol share that symbol's heat budget. Without curves, keep the published
        # per-bot arithmetic (risk = target_heat / distinct symbols) unchanged.
        if total > 0 and (mode == VARIANCE_SCALED or all(m.curve for m in members)):
            risks = [r * float(target_heat_pct) / total for r in risks]
    heat = float(sum(risks))
    exposure: dict[str, float] = {}
    for m, r in zip(members, risks):
        exposure[m.symbol] = exposure.get(m.symbol, 0.0) + r
    off_diag = matrix[~np.eye(n, dtype=bool)] if n > 1 else np.zeros(0)
    health = {
        "distinct_symbols": len(symbols),
        "max_symbol_exposure": round(max(exposure.values()), 6) if exposure else 0.0,
        "avg_member_corr": round(float(np.mean(np.maximum(off_diag, 0.0))), 4) if off_diag.size else 0.0,
    }
    out_members = [{"strategy_id": m.strategy_id, "symbol": m.symbol, "risk_pct": round(r, 12), "scale": round(s, 6),
                    "avg_corr": round(c, 4), "bot_id": m.bot_id} for m, r, s, c in zip(members, risks, scales, avg_corr)]
    return PortfolioSizing(mode, out_members, round(heat, 12), health,
                           {"labels": labels, "matrix": [[round(float(v), 4) for v in row] for row in matrix]},
                           concurrent, fallback, reason, round(base, 6))


__all__ = ["EQUAL_HEAT", "VARIANCE_SCALED", "SIZING_ALIASES", "MIN_OVERLAPPING_RETURNS", "Member", "PortfolioSizing",
           "canonical_mode", "daily_returns", "size_portfolio"]
