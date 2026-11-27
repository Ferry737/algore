"""Anti-overfit gates — SPEC §2.1 (CONFIRMED CAM-01..07: 100 random, 1000 shuffles, 40 % DD, 50 % nudges, ≥ 15 OOS
trades, persistence ≥ 55). How each is computed is INFERRED / CLEAN-ROOM DESIGN. Every gate returns
{passed, value, threshold}."""
from __future__ import annotations

from typing import Any, Sequence

import numpy as np


def _gate(passed: bool, value: Any, threshold: Any, **extra: Any) -> dict[str, Any]:
    out = {"passed": bool(passed), "value": value, "threshold": threshold}
    out.update(extra)
    return out


def random_gate(oos_net: float, random_nets: Sequence[float], oos_bars: int, beat_pct: float = 95.0) -> dict[str, Any]:
    """Beat the `beat_pct` percentile of N random genomes on OOS net; the bar rises to 98 % when OOS bars < 2000."""
    pct = max(float(beat_pct), 98.0) if int(oos_bars) < 2000 else float(beat_pct)
    if len(random_nets) == 0:
        return _gate(False, float(oos_net), None, percentile=pct, note="no random field")
    threshold = float(np.percentile(np.asarray(random_nets, dtype=float), pct))
    return _gate(float(oos_net) >= threshold, float(oos_net), threshold, percentile=pct, n=len(random_nets))


def shuffle_gate(trade_nets: Sequence[float], start_equity: float = 10000.0, max_dd_pct: float = 40.0, n: int = 1000,
                 seed: int = 0) -> dict[str, Any]:
    """Monte-Carlo trade-order shuffle: reject if ANY ordering's max drawdown exceeds `max_dd_pct` at campaign risk."""
    r = np.asarray(trade_nets, dtype=float)
    if r.size == 0:
        return _gate(False, 0.0, max_dd_pct, n=0)
    r = r / float(start_equity)
    rng = np.random.default_rng(seed)
    n = max(1, int(n))
    idx = np.vstack([rng.permutation(r.size) for _ in range(min(n, 1000))]) if r.size > 1 else np.zeros((1, 1), dtype=int)
    paths = np.cumprod(1.0 + r[idx], axis=1)
    paths = np.hstack([np.ones((paths.shape[0], 1)), paths])
    peak = np.maximum.accumulate(paths, axis=1)
    dd = 1.0 - paths / peak
    worst = float(np.max(dd) * 100.0)
    return _gate(worst <= max_dd_pct, worst, max_dd_pct, n=int(idx.shape[0]))


def nudge_gate(profitable: int, n: int, pass_pct: float = 50.0) -> dict[str, Any]:
    """≥ pass_pct of perturbed genomes must be profitable on OOS."""
    n = max(1, int(n))
    rate = float(profitable) / n * 100.0
    return _gate(rate >= pass_pct, rate, float(pass_pct), n=n, profitable=int(profitable))


def trades_gate(oos_trades: int, minimum: int = 15) -> dict[str, Any]:
    return _gate(int(oos_trades) >= minimum, int(oos_trades), int(minimum))


def persistence_gate(persistence: float, minimum: float = 55.0) -> dict[str, Any]:
    """Persistence ≥ 55 reads GOOD (CONFIRMED CAM-08)."""
    return _gate(float(persistence) >= minimum, round(float(persistence), 2), float(minimum))


__all__ = ["random_gate", "shuffle_gate", "nudge_gate", "trades_gate", "persistence_gate"]
