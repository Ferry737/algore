"""Portfolio sizing (SPEC §2.4)."""
from __future__ import annotations

import numpy as np

from app.portfolio import Member, size_portfolio


def curve(returns: list[float], start: float = 10000.0) -> list[tuple[int, float]]:
    out, eq, ts = [], start, 1_700_000_000
    for r in returns:
        eq *= 1 + r
        out.append((ts, eq))
        ts += 86400
    return out


def test_heat_sums_to_target_in_both_modes():
    rng = np.random.default_rng(0)
    members = [Member(f"s{i}", "EURUSD" if i % 2 else "GBPUSD", curve(list(rng.normal(0, 0.01, 40)))) for i in range(4)]
    for mode in ("heat", "decorrelated"):
        res = size_portfolio(members, target_heat_pct=3.0, symbol_lock=True, sizing_mode=mode)
        assert abs(sum(m["risk_pct"] for m in res["members"]) - 3.0) < 1e-9
        assert abs(res["heat"] - 3.0) < 1e-9
        assert res["health"]["distinct_symbols"] == 2
        assert res["health"]["max_symbol_exposure"] == 3.0 / 2 or res["health"]["max_symbol_exposure"] > 1.4
        assert len(res["correlation_matrix"]["labels"]) == 4
        assert len(res["correlation_matrix"]["matrix"]) == 4


def test_higher_average_correlation_means_lower_scale():
    rng = np.random.default_rng(1)
    base = list(rng.normal(0, 0.01, 60))
    noisy = [b + n for b, n in zip(base, rng.normal(0, 0.002, 60))]
    indep = list(rng.normal(0, 0.01, 60))
    members = [Member("twin_a", "EURUSD", curve(base)), Member("twin_b", "GBPUSD", curve(noisy)), Member("solo", "USDJPY", curve(indep))]
    res = size_portfolio(members, target_heat_pct=3.0, symbol_lock=False, sizing_mode="decorrelated")
    by_id = {m["strategy_id"]: m for m in res["members"]}
    assert by_id["twin_a"]["avg_corr"] > by_id["solo"]["avg_corr"]
    assert by_id["twin_a"]["scale"] < by_id["solo"]["scale"]
    assert by_id["twin_a"]["risk_pct"] < by_id["solo"]["risk_pct"]
    assert all(0.5 <= m["scale"] <= 1.5 for m in res["members"])


def test_symbol_lock_divides_by_distinct_symbols():
    members = [Member("a", "EURUSD", None), Member("b", "EURUSD", None), Member("c", "XAUUSD", None)]
    res = size_portfolio(members, target_heat_pct=2.0, symbol_lock=True, sizing_mode="heat")
    assert [round(m["risk_pct"], 6) for m in res["members"]] == [1.0, 1.0, 1.0]
    res2 = size_portfolio(members, target_heat_pct=3.0, symbol_lock=False, sizing_mode="heat")
    assert all(abs(m["risk_pct"] - 1.0) < 1e-9 for m in res2["members"])
    assert res2["health"]["max_symbol_exposure"] == 2.0
