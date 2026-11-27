"""Breeder (SPEC §2.1 / §8 test_breeder)."""
from __future__ import annotations

import json
import random

import pytest

from app.bars import Bars
from app.breeder import MAX_WORKERS, CampaignData, CampaignParams, GateParams, apply_gates, executor_workers, run_campaign
from app.genome import count_nodes, crossover, depth, from_json, mutate, nudge_numeric, random_genome, to_json, validate
from app.parity_backtester import CostModel, run_backtest, split_results
from tests.conftest import h1_bars


def test_executor_cap_is_two():
    assert MAX_WORKERS == 2
    assert executor_workers(8) <= 2
    assert executor_workers(None) == 2
    assert executor_workers(1) == 1


def test_genomes_are_bounded_and_json_serialisable():
    rng = random.Random(1)
    for _ in range(200):
        g = random_genome(rng, depth=rng.choice([2, 3, 4]), ref_price=1.1)
        validate(g)
        for side in ("long", "short"):
            assert depth(g[side]) <= 5 and count_nodes(g[side]) <= 25
        assert from_json(to_json(g)) == g
        assert json.loads(to_json(g))["version"] == 1


def test_crossover_mutate_and_nudge_keep_genomes_valid():
    rng = random.Random(2)
    for _ in range(50):
        a = random_genome(rng, 3, 1.1)
        b = random_genome(rng, 3, 1.1)
        child = crossover(a, b, rng)
        validate(child)
        m = mutate(child, rng, 1.1)
        validate(m)
        n = nudge_numeric(child, rng)
        validate(n)
        assert n["stops"] != child["stops"] or n["long"] != child["long"] or n["short"] != child["short"]


def small_params(**over) -> CampaignParams:
    base = dict(
        name="t", symbol="EURUSD", timeframe="H1", generations=4, population=24, breed_pop=12, seed=7,
        tribes=("Consistency",), workers=1,
        gates=GateParams(random_n=8, shuffle_n=100, nudge_n=4, min_oos_trades=1, min_persistence=0),
    )
    base.update(over)
    return CampaignParams(**base)


def test_population_improves_and_progress_is_reported(m1_rows):
    data = CampaignData(bars=h1_bars(m1_rows), m1_bars=Bars.from_rows(m1_rows, "M1"), cost=CostModel())
    progress = []
    res = run_campaign(small_params(), data, progress_cb=progress.append)
    gens = [p for p in progress if p["stage"] == "breeding"]
    assert gens and gens[0]["generation"] == 1
    assert gens[-1]["generation"] == 4
    assert gens[-1]["best_fitness"] > gens[0]["best_fitness"], [p["best_fitness"] for p in gens]
    for p in progress:
        assert {"tribe", "generation", "generations_total", "best_fitness", "mean_fitness", "survivors", "stage", "elapsed_s", "eta_s"} <= set(p)
    assert progress[-1]["stage"] == "done"
    assert set(res.rejected) == {"random_gate", "shuffle", "nudge", "trades", "persistence"}


def test_deterministic_with_seed(m1_rows):
    data = CampaignData(bars=h1_bars(m1_rows), m1_bars=None, cost=CostModel())
    a = run_campaign(small_params(generations=2, population=12, breed_pop=6), data)
    b = run_campaign(small_params(generations=2, population=12, breed_pop=6), data)
    assert [to_json(s["genome"]) for s in a.survivors] == [to_json(s["genome"]) for s in b.survivors]
    assert a.best_fitness == pytest.approx(b.best_fitness)


def test_random_genome_fails_the_gates(m1_rows):
    bars = h1_bars(m1_rows)
    data = CampaignData(bars=bars, m1_bars=None, cost=CostModel())
    rng = random.Random(5)
    gates = GateParams(random_n=6, shuffle_n=50, nudge_n=3, min_oos_trades=15, min_persistence=55)
    random_nets = [-50.0, 0.0, 50.0]
    passed = 0
    for _ in range(6):
        g = random_genome(rng, 3, float(bars.close.mean()))
        res = run_backtest(bars, g, data.cost)
        is_m, oos_m = split_results(res)
        ok, _parts = apply_gates(g, {"is": is_m, "oos": oos_m, "oos_nets": [t["net"] for t in res.trades if t["open_ts"] >= res.oos_start_ts]}, data, rng, gates, random_nets, evaluate=None)
        passed += int(ok)
    assert passed < 6
