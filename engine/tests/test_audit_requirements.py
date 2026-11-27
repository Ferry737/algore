"""Explicit audit-gate tests for the four mandated engine safeguards.

Every assertion here reads real engine output; no test uses skip/xfail/mocks.
"""
from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from app.bars import Bars
from app.portfolio import Member, size_portfolio
from app.vault import replay_window
from tests.conftest import import_m1, make_strategy

BASE = "/api/v1"


def _curve(start_ts: int = 1_700_000_000, count: int = 9) -> list[tuple[int, float]]:
    eq, out = 10_000.0, []
    for i in range(count):
        eq *= 1.0 + (0.01 if i % 2 == 0 else -0.004)
        out.append((start_ts + i * 86_400, eq))
    return out


def test_a_replay_fast_track_rejects_ts_at_or_before_train_end():
    bars = Bars.from_rows(
        [
            (100, 1, 1, 1, 1, 1),
            (200, 1, 1, 1, 1, 1),
            (300, 1, 1, 1, 1, 1),
        ],
        timeframe="M1",
        symbol="EURUSD",
    )
    window = replay_window(bars, trained_until=200)
    assert len(window.ts) == 1
    assert int(window.ts[0]) == 300
    assert bool((window.ts > 200).all())
    assert bool((replay_window(bars, 300).ts.size == 0))


def test_b_pilot_ingest_dedups_retried_mt5_ticket(
    client: TestClient, headers, pilot_headers, settings, m1_rows
):
    import_m1(client, headers, m1_rows)
    sid, _ = make_strategy(settings, m1_rows)
    pid = client.post(
        f"{BASE}/portfolios",
        headers=headers,
        json={"name": "audit", "strategy_ids": [sid], "target_heat_pct": 1.0,
              "symbol_lock": True, "sizing_mode": "equal_heat"},
    ).json()["portfolio_id"]
    bots = client.post(
        f"{BASE}/portfolios/{pid}/deploy", headers=headers, json={"incubation": True}
    ).json()["bots"]
    magic = str(bots[0]["magic"])
    trade = {
        "v": 1, "type": "trade", "sent_at": "2026-11-27T07:00:00Z",
        "pilot_id": "12345678-FX",
        "account": {"login": 12345678, "server": "Demo", "balance": 10000.0,
                    "equity": 10020.0, "currency": "USD"},
        "trade": {"ticket": 987654321, "position_id": 987000, "magic": magic,
                  "symbol": "EURUSD", "direction": "buy", "lots": 0.1,
                  "open_time": "2026-11-27T06:00:00Z", "close_time": "2026-11-27T07:00:00Z",
                  "open_price": 1.085, "close_price": 1.0875, "profit": 25.0,
                  "commission": -0.7, "swap": 0.0, "sl": 1.08, "tp": 1.09,
                  "reason": "tp", "equity_after": 10020.0},
    }
    first = client.post(f"{BASE}/pilot/ingest", headers=pilot_headers, json=trade)
    assert first.status_code == 202, first.text
    retry = client.post(f"{BASE}/pilot/ingest", headers=pilot_headers, json=trade)
    assert retry.status_code == 200 and retry.json() == {"duplicate": True}
    with sqlite3.connect(settings.db_path) as conn:
        rows = conn.execute("SELECT COUNT(*) FROM pilot_trades").fetchone()[0]
    assert rows == 1
    bot = client.get(f"{BASE}/incubation/{bots[0]['bot_id']}", headers=headers).json()
    assert bot["live_trades"] == 1


def test_c_variance_sizer_falls_back_to_target_heat_over_symbols():
    members = [
        Member("a", "EURUSD", _curve()),
        Member("b", "GBPUSD", _curve(1_700_000_000 + 60)),
    ]
    res = size_portfolio(
        members, target_heat_pct=3.0, symbol_lock=True, sizing_mode="variance_scaled"
    )
    assert res["sizing_fallback"] is True
    assert res["sizing_fallback_reason"]
    assert [m["risk_pct"] for m in res["members"]] == [1.5, 1.5]
    assert abs(res["heat"] - 3.0) < 1e-9


def test_d_both_canonical_sizing_modes_selectable_per_portfolio(
    client: TestClient, headers, settings, m1_rows
):
    import_m1(client, headers, m1_rows)
    sid, _ = make_strategy(settings, m1_rows)
    for mode in ("equal_heat", "variance_scaled"):
        r = client.post(
            f"{BASE}/portfolios",
            headers=headers,
            json={"name": f"p-{mode}", "strategy_ids": [sid], "target_heat_pct": 1.0,
                  "symbol_lock": True, "sizing_mode": mode},
        )
        assert r.status_code == 200, r.text
        assert r.json()["sizing_mode"] == mode
