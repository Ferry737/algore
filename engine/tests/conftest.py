"""Shared fixtures: temp DB via Settings, TestClient against create_app(), synthetic data."""
from __future__ import annotations

import os
import random
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("ALGORE_JWT_SECRET", "test-secret")
os.environ.setdefault("ALGORE_DASHBOARD_API_KEY", "test-api-key")
os.environ.setdefault("ALGORE_BREED_WORKERS", "1")

from fastapi.testclient import TestClient  # noqa: E402

from app.api import create_app  # noqa: E402
from app.bars import Bars  # noqa: E402
from app.config import Settings  # noqa: E402
from app.demo_seed import synthetic_m1  # noqa: E402
from app.genome import random_genome  # noqa: E402
from app.parity_backtester import run_backtest, split_results  # noqa: E402

TEST_KEY = "test-api-key"
SYMBOL = "EURUSD"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        jwt_secret="test-secret",
        dashboard_api_key=TEST_KEY,
        db_path=str(tmp_path / "algore_test.db"),
        cors_origins=("https://dash.example.com",),
        breed_workers=1,
        rate_limit_per_min=5000,
        ingest_rate_limit_per_min=5000,
    )


@pytest.fixture
def client(settings: Settings):
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture
def headers(client: TestClient) -> dict[str, str]:
    tok = client.post("/api/v1/auth/token", json={"api_key": TEST_KEY}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def pilot_headers(client: TestClient, headers: dict[str, str]) -> dict[str, str]:
    tok = client.post("/api/v1/pilot/token", headers=headers, json={"pilot_id": "12345678-FX"}).json()["pilot_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def m1_rows() -> list[dict]:
    return synthetic_m1(n_minutes=10 * 24 * 60, seed=11)


def import_m1(client: TestClient, headers: dict[str, str], rows: list[dict], symbol: str = SYMBOL) -> dict:
    r = client.post("/api/v1/data/import", headers=headers, json={"symbol": symbol, "timeframe": "M1", "bars": rows})
    assert r.status_code == 200, r.text
    return r.json()


def h1_bars(rows: list[dict]) -> Bars:
    return Bars.from_rows(rows, "M1").resample(60)


def make_strategy(settings: Settings, rows: list[dict], seed: int = 5, symbol: str = SYMBOL) -> tuple[str, dict]:
    """Run a real backtest on synthetic H1 bars and insert the survivor into the vault. Returns (id, survivor)."""
    from app import vault
    from app.db import connect
    from app.fitness import score

    rng = random.Random(seed)
    bars = h1_bars(rows)
    ref = float(np.median(bars.close))
    best = None
    for _ in range(30):
        g = random_genome(rng, depth=3, ref_price=ref)
        res = run_backtest(bars, g)
        is_m, oos_m = split_results(res)
        if oos_m["trades"] >= 2 and (best is None or oos_m["net"] > best[1]):
            best = (g, oos_m["net"], res, is_m, oos_m)
    assert best is not None, "no random genome traded on the synthetic series"
    g, _, res, is_m, oos_m = best
    total, parts = score(oos_m)
    survivor = {
        "genome": g,
        "score": total,
        "parts": parts,
        "metrics": {"is": is_m, "oos": oos_m},
        "equity": res.equity,
    }
    conn = connect(settings.db_path)
    sid = vault.add_strategy(conn, survivor, campaign_id=None, symbol=symbol, timeframe="H1", trained_until=int(bars.ts[-1]))
    conn.close()
    return sid, survivor


def small_campaign(**over) -> dict:
    body = {
        "name": "t",
        "symbol": SYMBOL,
        "timeframe": "H1",
        "generations": 2,
        "population": 12,
        "breed_pop": 8,
        "seed": 3,
        "gates": {"random_n": 6, "shuffle_n": 50, "nudge_n": 4, "min_oos_trades": 1, "min_persistence": 0},
    }
    body.update(over)
    return body


def wait_status(client: TestClient, headers: dict[str, str], cid: str, timeout: float = 90.0) -> dict:
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        row = client.get(f"/api/v1/campaigns/{cid}", headers=headers).json()
        if row["status"] in ("done", "failed", "stopped"):
            return row
        time.sleep(0.2)
    raise AssertionError("campaign did not finish")


__all__ = ["replace", "import_m1", "h1_bars", "make_strategy", "small_campaign", "wait_status", "SYMBOL", "TEST_KEY"]
