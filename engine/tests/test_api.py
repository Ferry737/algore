"""HTTP + WebSocket contract (SPEC §4/§5, §8 test_api)."""
from __future__ import annotations

import time
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api import create_app
from app.config import Settings
from tests.conftest import TEST_KEY, h1_bars, import_m1, make_strategy, small_campaign, wait_status

BASE = "/api/v1"


def test_health_and_401_without_token(client: TestClient):
    r = client.get(f"{BASE}/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["db"] == "ok" and "pilot_online" in body and "bots" in body and "campaigns_active" in body
    r = client.get(f"{BASE}/vault")
    assert r.status_code == 401 and r.json() == {"detail": "invalid or missing token"}
    r = client.post(f"{BASE}/auth/token", json={"api_key": "wrong"})
    assert r.status_code == 401


def test_token_exchange_and_scopes(client: TestClient, headers, pilot_headers):
    tok = client.post(f"{BASE}/auth/token", json={"api_key": TEST_KEY}).json()
    assert tok["token_type"] == "Bearer" and tok["expires_in"] == 3600 and tok["access_token"]
    r = client.get(f"{BASE}/vault", headers=pilot_headers)
    assert r.status_code == 403 and r.json() == {"detail": "scope"}
    r = client.post(f"{BASE}/pilot/ingest", headers=headers, json={"v": 1})
    assert r.status_code == 403  # dashboard token may not post as pilot


def test_data_import_idempotent_and_list(client: TestClient, headers, m1_rows):
    a = import_m1(client, headers, m1_rows)
    assert a["inserted"] == len(m1_rows) and a["first_ts"] == m1_rows[0]["ts"] and a["last_ts"] == m1_rows[-1]["ts"]
    b = import_m1(client, headers, m1_rows)
    assert b["inserted"] == len(m1_rows)
    listing = client.get(f"{BASE}/data", headers=headers).json()
    assert listing == [{"symbol": "EURUSD", "timeframe": "M1", "bars": len(m1_rows), "first_ts": m1_rows[0]["ts"], "last_ts": m1_rows[-1]["ts"]}]
    csv = "ts,open,high,low,close,volume\n" + "\n".join(f"{r['ts']},{r['open']},{r['high']},{r['low']},{r['close']},{r['volume']}" for r in m1_rows[:5])
    r = client.post(f"{BASE}/data/import", headers=headers, json={"symbol": "GBPUSD", "timeframe": "M1", "csv": csv})
    assert r.status_code == 200 and r.json()["inserted"] == 5


def test_campaign_create_progress_done_and_stop(client: TestClient, headers, m1_rows):
    import_m1(client, headers, m1_rows)
    r = client.post(f"{BASE}/campaigns", headers=headers, json=small_campaign())
    assert r.status_code == 202 and r.json()["status"] == "queued"
    cid = r.json()["campaign_id"]
    row = wait_status(client, headers, cid)
    assert row["status"] == "done", row
    assert row["generations"] and {"tribe", "generation", "best_fitness", "mean_fitness", "survivors"} <= set(row["generations"][0])
    assert "passed" in row["gates"] and "rejected_by" in row["gates"]
    assert row["progress"]["stage"] == "done"
    lst = client.get(f"{BASE}/campaigns", headers=headers).json()
    assert lst[0]["campaign_id"] == cid and lst[0]["generations_total"] == 2 and "vaulted" in lst[0]
    r = client.post(f"{BASE}/campaigns", headers=headers, json=small_campaign(generations=6, population=12, breed_pop=8, seed=9))
    cid2 = r.json()["campaign_id"]
    time.sleep(0.3)
    r = client.post(f"{BASE}/campaigns/{cid2}/stop", headers=headers)
    assert r.status_code == 200 and r.json() == {"status": "stopped"}
    row2 = wait_status(client, headers, cid2)
    assert row2["status"] == "stopped"


def test_vault_list_passport_export_parity_reassess(client: TestClient, headers, settings, m1_rows):
    import_m1(client, headers, m1_rows)
    sid, _ = make_strategy(settings, m1_rows)
    lst = client.get(f"{BASE}/vault", headers=headers,json=None).json()
    item = next(s for s in lst if s["strategy_id"] == sid)
    assert {"strategy_id", "name", "symbol", "timeframe", "score", "score_parts", "archetype", "oos", "parity_grade", "health", "mq5_url"} <= set(item)
    assert set(item["oos"]) >= {"trades", "net", "sharpe", "pf", "max_dd", "persistence"}
    assert client.get(f"{BASE}/vault?symbol=NOPE", headers=headers).json() == []
    assert client.get(f"{BASE}/vault?symbol=EURUSD&timeframe=H1", headers=headers).json()[0]["strategy_id"] == sid
    passport = client.get(f"{BASE}/vault/{sid}", headers=headers).json()
    assert passport["strategy_id"] == sid and {"is", "oos"} <= set(passport["metrics"])
    assert passport["equity"] and {"ts", "equity", "oos"} <= set(passport["equity"][0])
    assert passport["parity_tests"] == [] and passport["reassessments"] == []
    r = client.get(f"{BASE}/vault/{sid}/export.mq5", headers=headers)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    assert "attachment" in r.headers["content-disposition"] and r.text.count("{") == r.text.count("}")
    assert client.get(f"{BASE}/vault/nope", headers=headers).status_code == 404
    engine_net = passport["metrics"]["oos"]["return_pct"]
    r = client.post(f"{BASE}/vault/{sid}/parity", headers=headers, json={"mt5_net_return": engine_net * 1.02})
    assert r.status_code == 200
    body = r.json()
    assert body["grade"] in "ABCDF" and body["engine_net_return"] == pytest.approx(engine_net)
    assert body["mt5_net_return"] == pytest.approx(engine_net * 1.02) and body["diff_pct"] <= 5.0
    assert client.get(f"{BASE}/vault", headers=headers).json()[0]["parity_grade"] == body["grade"]
    r = client.post(f"{BASE}/vault/{sid}/reassess", headers=headers)
    assert r.status_code == 200 and set(r.json()) == {"verdict", "trades_since", "score_delta", "expectancy"}
    assert r.json()["verdict"] in ("HOLDING", "WEAKENING", "REPLACE", "TOO_EARLY")
    assert client.get(f"{BASE}/vault/{sid}", headers=headers).json()["reassessments"]


def test_portfolio_deploy_and_incubation_endpoints(client: TestClient, headers, settings, m1_rows):
    import_m1(client, headers, m1_rows)
    sid, _ = make_strategy(settings, m1_rows)
    r = client.post(f"{BASE}/portfolios", headers=headers, json={"name": "p1", "strategy_ids": [sid], "target_heat_pct": 1.0, "symbol_lock": True, "sizing_mode": "heat"})
    assert r.status_code == 200, r.text
    p = r.json()
    assert {"portfolio_id", "name", "target_heat_pct", "symbol_lock", "sizing_mode", "heat", "members", "correlation_matrix", "health"} <= set(p)
    assert abs(p["heat"] - 1.0) < 1e-9 and p["members"][0]["strategy_id"] == sid
    pid = p["portfolio_id"]
    assert client.get(f"{BASE}/portfolios", headers=headers).json()[0]["portfolio_id"] == pid
    assert client.get(f"{BASE}/portfolios/{pid}", headers=headers).json()["name"] == "p1"
    r = client.post(f"{BASE}/portfolios/{pid}/deploy", headers=headers, json={"incubation": True})
    assert r.status_code == 200, r.text
    bots = r.json()["bots"]
    assert len(bots) == 1 and bots[0]["strategy_id"] == sid and bots[0]["magic"] >= 900001
    bot = bots[0]["bot_id"]
    assert bots[0]["effective_risk_pct"] == pytest.approx(0.25 * 1.0) and bots[0]["pilot_token_url"].endswith(f"/incubation/{bot}")
    lst = client.get(f"{BASE}/incubation", headers=headers).json()
    b = lst[0]
    assert {"bot_id", "strategy_id", "tier", "multiplier", "target_risk_pct", "effective_risk_pct", "auto", "paused", "frozen_reason", "health_word",
            "pending_graduation", "live_trades", "healthy_live_trades", "live_net_r", "checks", "pilot_state", "updated_at"} <= set(b)
    assert b["tier"] == "INCUBATION" and b["multiplier"] == 0.25 and b["pilot_state"] == "PILOT_OFFLINE" and b["frozen_reason"] == "PILOT_OFFLINE"
    assert len(b["checks"]) == 8 and {"id", "label", "pass", "value", "text"} <= set(b["checks"][0])
    one = client.get(f"{BASE}/incubation/{bot}", headers=headers).json()
    assert one["bot_id"] == bot and one["effective_risk_pct"] == pytest.approx(0.25)
    # bot token may read only its own rung
    bt = client.post(f"{BASE}/bots/{bot}/token", headers=headers).json()["bot_token"]
    assert client.get(f"{BASE}/incubation/{bot}", headers={"Authorization": f"Bearer {bt}"}).status_code == 200
    assert client.get(f"{BASE}/vault", headers={"Authorization": f"Bearer {bt}"}).status_code == 403
    r = client.post(f"{BASE}/incubation/{bot}/rung", headers=headers, json={"rung": "FULL", "reason": "operator"})
    assert r.status_code == 200 and r.json()["multiplier"] == 1.0 and r.json()["tier"] == "FULL"
    r = client.post(f"{BASE}/incubation/{bot}/auto", headers=headers, json={"auto": False})
    assert r.status_code == 200 and r.json()["auto"] is False
    r = client.post(f"{BASE}/incubation/pause-all", headers=headers, json={"paused": True, "reason": "news"})
    assert r.status_code == 200 and r.json()["paused"] is True
    after = client.get(f"{BASE}/incubation/{bot}", headers=headers).json()
    assert after["paused"] is True and after["multiplier"] == 1.0
    r = client.post(f"{BASE}/incubation/{bot}/pause", headers=headers, json={"paused": False})
    assert r.status_code == 200 and r.json()["paused"] is False
    r = client.post(f"{BASE}/incubation/{bot}/graduate", headers=headers)
    assert r.status_code == 200 and "tier" in r.json()
    assert client.get(f"{BASE}/incubation/ghost", headers=headers).status_code == 404
    assert client.get(f"{BASE}/alerts", headers=headers).status_code == 200
    assert client.get(f"{BASE}/alerts?active=1", headers=headers).status_code == 200


def test_pilot_ingest_duplicate_status_and_health(client: TestClient, headers, pilot_headers, settings, m1_rows):
    import_m1(client, headers, m1_rows)
    sid, _ = make_strategy(settings, m1_rows)
    pid = client.post(f"{BASE}/portfolios", headers=headers, json={"name": "p", "strategy_ids": [sid], "target_heat_pct": 1.0, "symbol_lock": True, "sizing_mode": "heat"}).json()["portfolio_id"]
    bots = client.post(f"{BASE}/portfolios/{pid}/deploy", headers=headers, json={"incubation": True}).json()["bots"]
    bot, magic = bots[0]["bot_id"], bots[0]["magic"]
    env = {
        "v": 1, "type": "heartbeat", "sent_at": "2026-11-27T07:00:00Z", "pilot_id": "12345678-FX",
        "account": {"login": 12345678, "server": "Broker-Demo", "balance": 10000.0, "equity": 10012.5, "currency": "USD"},
        "chart": {"symbol": "EURUSD", "period_minutes": 60, "chart_id": 1325417983171},
        "terminal": {"connected": True, "trade_allowed": True, "trade_allowed_expert": True},
        "bots": [{"magic": str(magic), "symbol": "EURUSD", "positions": 1, "last_deal_at": "2026-11-27T06:59:00Z"}],
    }
    r = client.post(f"{BASE}/pilot/ingest", headers=pilot_headers, json=env)
    assert r.status_code == 202 and r.json() == {"accepted": 1, "pilot_online": True}
    assert client.get(f"{BASE}/health").json()["pilot_online"] is True
    st = client.get(f"{BASE}/pilot/status", headers=headers).json()
    assert st["online"] is True and st["chart"]["symbol"] == "EURUSD" and st["account"]["login"] == 12345678
    assert [b["bot_id"] for b in st["bots"]] == [bot] and st["silent_bots"] == []
    b = client.get(f"{BASE}/incubation/{bot}", headers=headers).json()
    assert b["pilot_state"] == "ONLINE" and b["frozen_reason"] is None
    trade = dict(env, type="trade", trade={
        "ticket": 123456, "position_id": 123000, "magic": str(magic), "symbol": "EURUSD", "direction": "buy", "lots": 0.1,
        "open_time": "2026-11-27T06:00:00Z", "close_time": "2026-11-27T07:00:00Z", "open_price": 1.085, "close_price": 1.0875,
        "profit": 21.5, "commission": -0.7, "swap": 0.0, "sl": 1.08, "tp": 1.09, "reason": "tp", "equity_after": 10012.5,
    })
    r = client.post(f"{BASE}/pilot/ingest", headers=pilot_headers, json=trade)
    assert r.status_code == 202, r.text
    r = client.post(f"{BASE}/pilot/ingest", headers=pilot_headers, json=trade)
    assert r.status_code == 200 and r.json() == {"duplicate": True}
    b = client.get(f"{BASE}/incubation/{bot}", headers=headers).json()
    assert b["live_trades"] == 1 and b["live_net_r"] > 0
    r = client.post(f"{BASE}/pilot/ingest", headers=pilot_headers, json={"v": 1, "type": "status", "sent_at": "2026-11-27T07:00:31Z", "pilot_id": "12345678-FX",
        "account": {"login": 12345678, "server": "Broker-Demo", "balance": 10000.0, "equity": 10012.5, "currency": "USD"}, "note": "auto trading disabled"})
    assert r.status_code == 202
    r = client.post(f"{BASE}/pilot/ingest", headers=pilot_headers, json={"v": 1, "type": "heartbeat"})
    assert r.status_code == 422


def test_ws_rejects_bad_token_and_delivers_transition(client: TestClient, headers, settings, m1_rows):
    import_m1(client, headers, m1_rows)
    sid, _ = make_strategy(settings, m1_rows)
    pid = client.post(f"{BASE}/portfolios", headers=headers, json={"name": "p", "strategy_ids": [sid], "target_heat_pct": 1.0, "symbol_lock": True, "sizing_mode": "heat"}).json()["portfolio_id"]
    bot = client.post(f"{BASE}/portfolios/{pid}/deploy", headers=headers, json={"incubation": True}).json()["bots"][0]["bot_id"]
    with pytest.raises(WebSocketDisconnect) as ei:
        with client.websocket_connect(f"{BASE}/ws/live?token=bad") as ws:
            ws.receive_json()
    assert ei.value.code == 4401
    token = headers["Authorization"].split(" ", 1)[1]
    with client.websocket_connect(f"{BASE}/ws/live?token={token}") as ws:
        ws.send_json({"type": "subscribe", "topics": ["incubation.*"]})
        time.sleep(0.2)
        r = client.post(f"{BASE}/incubation/{bot}/rung", headers=headers, json={"rung": "PROVING", "reason": "ws test"})
        assert r.status_code == 200
        deadline = time.time() + 5
        msg = None
        while time.time() < deadline:
            m = ws.receive_json()
            if m["type"] == "incubation.transition":
                msg = m
                break
        assert msg is not None and msg["data"]["bot_id"] == bot and msg["data"]["to_tier"] == "PROVING"
        assert msg["data"]["multiplier_after"] == 0.5 and "ts" in msg


def test_rate_limit_429(settings: Settings):
    app = create_app(replace(settings, rate_limit_per_min=3))
    with TestClient(app) as c:
        for _ in range(3):
            assert c.get(f"{BASE}/health").status_code == 200
        r = c.get(f"{BASE}/health")
        assert r.status_code == 429 and r.json()["detail"] == "rate limited" and r.json()["retry_after"] >= 1
        assert int(r.headers["retry-after"]) >= 1


def test_cors_allowed_and_disallowed(client: TestClient, headers):
    r = client.options(f"{BASE}/vault", headers={"Origin": "https://dash.example.com", "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") == "https://dash.example.com"
    r = client.options(f"{BASE}/vault", headers={"Origin": "https://evil.example.com", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in r.headers
