"""Score (vault passport, CAM-21) and breeder fitness.

SCORE_WEIGHTS mirror the seven published weights (CAM-21 / CAM-08b): Persistence 20, Recovery 15, Sharpe 15,
Trades 15, Max drawdown 10, Profit factor 10, IS linearity 3 — they sum to 88. The eighth part is not published;
the remaining 12 points are given to "Robustness" (INFERRED, our choice: nudge/shuffle robustness of the gates).
How the parts are normalised and combined is NOT PUBLIC → CLEAN-ROOM DESIGN (functions below, each documented).
"""
from __future__ import annotations

from typing import Any, Mapping

SCORE_WEIGHTS: dict[str, float] = {
    "persistence": 20.0,
    "recovery": 15.0,
    "sharpe": 15.0,
    "trades": 15.0,
    "max_dd": 10.0,
    "profit_factor": 10.0,
    "is_linearity": 3.0,
    "robustness": 12.0,  # INFERRED: 100 − 88 (CAM-21 leaves 12 points unattributed)
}

# Tribe weightings (SPEC §2.1): Consistency leans on Sharpe/Persistence/linearity/DD; Growth on PF/Return(recovery)/trades.
_TRIBE_MULTIPLIERS: dict[str, dict[str, float]] = {
    "Consistency": {"sharpe": 1.3, "persistence": 1.2, "is_linearity": 2.0, "max_dd": 1.2, "recovery": 0.8, "profit_factor": 0.9},
    "Growth": {"profit_factor": 1.4, "recovery": 1.4, "trades": 1.0, "sharpe": 0.8, "persistence": 0.9, "max_dd": 0.8},
}


def _clip(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _num(metrics: Mapping[str, Any], key: str, default: float = 0.0) -> float:
    v = metrics.get(key, default)
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return f if f == f else default  # NaN -> default


def norm_persistence(p: float) -> float:
    """persistence is 0–200; 100+ is full marks."""
    return _clip(_num({"p": p}, "p") / 100.0)


def norm_recovery(r: float) -> float:
    """recovery = net / max drawdown money; 5.0 or more is full marks."""
    return _clip(_num({"r": r}, "r") / 5.0)


def norm_sharpe(s: float) -> float:
    """annualised Sharpe: 0.5 → 0, 2.5 → 1."""
    return _clip((_num({"s": s}, "s") - 0.5) / 2.0)


def norm_trades(t: float) -> float:
    """held-out trade count: 100 trades saturates; the ≥ 15 minimum is a gate, not a score."""
    return _clip(_num({"t": t}, "t") / 100.0)


def norm_max_dd(dd: float) -> float:
    """max drawdown %: 0 → 1, 30 % → 0."""
    return _clip(1.0 - _num({"dd": dd}, "dd") / 30.0)


def norm_profit_factor(pf: float) -> float:
    """profit factor: 1.0 → 0, 2.5 → 1."""
    return _clip((_num({"pf": pf}, "pf") - 1.0) / 1.5)


def norm_is_linearity(v: float) -> float:
    """R² of the in-sample equity curve vs time, already 0–1."""
    return _clip(_num({"v": v}, "v"))


def norm_robustness(v: float) -> float:
    """share of perturbed / shuffled variants that stay within limits, 0–1; neutral 0.5 when unknown."""
    return _clip(_num({"v": v}, "v", 0.5))


_NORMS = {
    "persistence": norm_persistence, "recovery": norm_recovery, "sharpe": norm_sharpe, "trades": norm_trades,
    "max_dd": norm_max_dd, "profit_factor": norm_profit_factor, "is_linearity": norm_is_linearity, "robustness": norm_robustness,
}
_METRIC_KEY = {"max_dd": "max_dd_pct", "profit_factor": "profit_factor", "trades": "trades", "is_linearity": "is_linearity"}


def score(metrics: Mapping[str, Any], weights: Mapping[str, float] | None = None, robustness: float | None = None) -> tuple[float, dict[str, float]]:
    """Weighted 0–100 score from IS/OOS metrics. Returns (total, parts) where parts = weight × norm per part."""
    w = weights or SCORE_WEIGHTS
    parts: dict[str, float] = {}
    for name, weight in w.items():
        if name == "robustness":
            value = robustness if robustness is not None else metrics.get("robustness", 0.5)
        else:
            value = metrics.get(_METRIC_KEY.get(name, name), 0.0)
        parts[name] = float(weight) * _NORMS[name](value if value is not None else 0.0)
    return float(sum(parts.values())), parts


def tribe_weights(tribe: str) -> dict[str, float]:
    """SCORE_WEIGHTS re-weighted per tribe and renormalised to 100."""
    mult = _TRIBE_MULTIPLIERS.get(tribe, {})
    raw = {k: v * mult.get(k, 1.0) for k, v in SCORE_WEIGHTS.items()}
    total = sum(raw.values())
    return {k: v * 100.0 / total for k, v in raw.items()}
