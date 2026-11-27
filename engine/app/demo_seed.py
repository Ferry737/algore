"""Synthetic M1 data + tiny campaign for a manual smoke run. CLEAN-ROOM DESIGN (demo data only).

Usage: cd engine && .venv/bin/python -m app.demo_seed [--db PATH] [--minutes N]
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from . import vault
from .bars import Bars
from .breeder import CampaignData, CampaignParams, GateParams, run_campaign
from .config import ENGINE_DIR, Settings
from .db import connect, init_db, insert
from .parity_backtester import CostModel

START_TS = 1704153600  # 2024-01-02 00:00:00 UTC (a Monday)


def synthetic_m1(n_minutes: int = 5 * 24 * 60, seed: int = 1, start_ts: int | None = None, price: float = 1.10) -> list[dict]:
    """Regime-switching random walk on M1 (no weekend gaps — synthetic). Deterministic for a seed."""
    rng = np.random.default_rng(seed)
    n = int(n_minutes)
    ts = start_ts if start_ts is not None else START_TS
    regime_len = 2000
    drift = np.repeat(rng.normal(0.0, 0.00005, n // regime_len + 2), regime_len)[:n]
    hour = ((ts + np.arange(n) * 60) // 3600) % 24
    vol = np.where((hour < 6), 0.00015, np.where((hour >= 12) & (hour < 16), 0.00035, 0.00025))
    noise = rng.normal(0.0, 1.0, n) * vol
    close = price + np.cumsum(drift + noise)
    open_ = np.concatenate([[price], close[:-1]])
    wick = np.abs(rng.normal(0.0, 1.0, n)) * vol * 0.6
    high = np.maximum(open_, close) + wick
    low = np.minimum(open_, close) - np.abs(rng.normal(0.0, 1.0, n)) * vol * 0.6
    volume = 80.0 + rng.random(n) * 120.0
    return [{"ts": int(ts + i * 60), "open": float(open_[i]), "high": float(high[i]), "low": float(low[i]),
             "close": float(close[i]), "volume": float(volume[i])} for i in range(n)]


def import_rows(conn, symbol: str, rows: list[dict]) -> int:
    conn.executemany(
        "INSERT OR REPLACE INTO bars(symbol, timeframe, ts, open, high, low, close, volume) VALUES (?,?,?,?,?,?,?,?)",
        [(symbol, "M1", r["ts"], r["open"], r["high"], r["low"], r["close"], r.get("volume", 0.0)) for r in rows],
    )
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="AlgoRE demo seed")
    ap.add_argument("--db", default=None)
    ap.add_argument("--minutes", type=int, default=5 * 24 * 60)
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args(argv)
    settings = Settings.from_env()
    db_path = args.db or settings.db_path
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    init_db(conn)
    rows = synthetic_m1(args.minutes, args.seed)
    print(f"importing {len(rows)} M1 bars into {db_path}")
    import_rows(conn, args.symbol, rows)
    m1 = Bars.from_rows(rows, "M1", symbol=args.symbol)
    h1 = m1.resample(60)
    params = CampaignParams(name="demo", symbol=args.symbol, timeframe="H1", generations=3, population=40, breed_pop=20,
                            seed=args.seed, gates=GateParams(random_n=10, shuffle_n=100, nudge_n=5, min_oos_trades=2,
                                                             min_persistence=0), workers=settings.breed_workers)
    t0 = time.time()
    result = run_campaign(params, CampaignData(bars=h1, cost=CostModel.for_symbol(args.symbol), m1_bars=m1),
                          progress_cb=lambda p: print(f"[{p['stage']}] {p['tribe']} gen {p['generation']} best={p['best_fitness']}"))
    ids = [vault.add_strategy(conn, s, campaign_id=None, symbol=args.symbol, timeframe="H1", trained_until=int(h1.ts[-1])) for s in result.survivors]
    print(json.dumps({"survivors": ids, "rejected": result.rejected, "elapsed_s": round(time.time() - t0, 2)}, indent=1))
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
