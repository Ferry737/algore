"""Campaign breeder — SPEC §2.1 (multi-objective GP, two tribes, Final War, OOS gates). CLEAN-ROOM DESIGN.

CONFIRMED (CAM-01..07): 20 generations × 2 tribes, Final War merge, judged on the last 30 %, gates (random field,
1000 shuffles / 40 % DD, 50 % nudges, ≥ 15 OOS trades, persistence ≥ 55), 3000 starting candidates.
Hard cap: ProcessPoolExecutor(max_workers <= MAX_WORKERS = 2) — asserted in tests.
"""
from __future__ import annotations

import random
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from . import gates as G
from .bars import Bars
from .evaluator import SeriesCache
from .fitness import score, tribe_weights
from .genome import archetype_of, copy_genome, crossover, is_valid, mechanism_of, mutate, nudge_numeric, random_genome, to_json
from .parity_backtester import CostModel, evaluate_genome, run_backtest, split_results

MAX_WORKERS = 2  # host cap (2 vCPU, no swap)
ELITES = 5
TOURNAMENT_K = 3
CROSSOVER_P = 0.7
MUTATION_P = 0.3


def executor_workers(requested: int | None) -> int:
    """Clamp any request to [1, MAX_WORKERS]."""
    if requested is None:
        return MAX_WORKERS
    return max(1, min(MAX_WORKERS, int(requested)))


@dataclass(frozen=True)
class GateParams:
    random_n: int = 100
    random_beat_pct: float = 95.0
    shuffle_n: int = 1000
    max_dd_pct: float = 40.0
    nudge_n: int = 20
    nudge_pass_pct: float = 50.0
    min_oos_trades: int = 15
    min_persistence: float = 55.0


@dataclass(frozen=True)
class CampaignParams:
    name: str
    symbol: str
    timeframe: str = "H1"
    generations: int = 20
    population: int = 3000
    breed_pop: int = 300
    seed: int = 0
    tribes: tuple[str, ...] = ("Consistency", "Growth")
    gates: GateParams = field(default_factory=GateParams)
    workers: int = MAX_WORKERS
    max_survivors: int = 20
    final_pool: int = 50

    def __post_init__(self) -> None:
        object.__setattr__(self, "workers", executor_workers(self.workers))
        object.__setattr__(self, "tribes", tuple(self.tribes) or ("Consistency",))


@dataclass(frozen=True)
class CampaignData:
    bars: Bars
    cost: CostModel
    m1_bars: Bars | None = None
    split: float = 0.7
    start_equity: float = 10000.0


@dataclass
class CampaignResult:
    survivors: list[dict[str, Any]]
    rejected: dict[str, int]
    generations: list[dict[str, Any]]
    best_fitness: float
    elapsed_s: float
    stopped: bool
    random_field: list[float]
    gate_log: list[dict[str, Any]]


# ----------------------------------------------------------------------------- worker side (top-level, picklable)
_W: dict[str, Any] = {}


def _init_worker(data: CampaignData) -> None:
    _W["data"] = data
    _W["sc"] = SeriesCache(data.bars)


def _eval_chunk(genomes: list[dict]) -> list[dict[str, Any]]:
    data: CampaignData = _W["data"]
    sc: SeriesCache = _W.get("sc") or SeriesCache(data.bars)
    _W["sc"] = sc
    return [evaluate_genome(data.bars, g, data.cost, data.m1_bars, data.split, sc) for g in genomes]


class Evaluator:
    """Maps genomes → evaluation dicts, in-process when workers == 1, else through a capped ProcessPool."""

    def __init__(self, data: CampaignData, workers: int | None = None) -> None:
        self.data = data
        self.workers = executor_workers(workers)
        self._pool: ProcessPoolExecutor | None = None
        self._sc: SeriesCache | None = None

    def map(self, genomes: list[dict]) -> list[dict[str, Any]]:
        if not genomes:
            return []
        if self.workers <= 1:
            if self._sc is None:
                self._sc = SeriesCache(self.data.bars)
            return [evaluate_genome(self.data.bars, g, self.data.cost, self.data.m1_bars, self.data.split, self._sc) for g in genomes]
        if self._pool is None:
            self._pool = ProcessPoolExecutor(max_workers=self.workers, initializer=_init_worker, initargs=(self.data,))
        size = max(1, (len(genomes) + self.workers * 2 - 1) // (self.workers * 2))
        chunks = [genomes[i:i + size] for i in range(0, len(genomes), size)]
        out: list[dict[str, Any]] = []
        for part in self._pool.map(_eval_chunk, chunks):
            out.extend(part)
        return out

    def close(self) -> None:
        if self._pool is not None:
            self._pool.shutdown(cancel_futures=True)
            self._pool = None


# ----------------------------------------------------------------------------- gates pipeline
def apply_gates(genome: dict, result: dict[str, Any], data: CampaignData, rng: random.Random, gate_params: GateParams,
                random_nets: list[float], evaluate: Evaluator | None = None, oos_bars: int | None = None) -> tuple[bool, dict[str, dict[str, Any]]]:
    """Run the OOS gates in order (short-circuit on the first failure; later gates are reported as skipped)."""
    oos = result["oos"]
    bars_n = int(oos_bars if oos_bars is not None else oos.get("oos_bars", 0))
    out: dict[str, dict[str, Any]] = {}
    out["trades"] = G.trades_gate(oos.get("trades", 0), gate_params.min_oos_trades)
    out["persistence"] = G.persistence_gate(oos.get("persistence", 0.0), gate_params.min_persistence)
    out["random_gate"] = G.random_gate(oos.get("net", 0.0), random_nets, bars_n, gate_params.random_beat_pct)
    if not all(g["passed"] for g in out.values()):
        for name in ("nudge", "shuffle"):
            out[name] = {"passed": False, "value": None, "threshold": None, "skipped": True}
        return False, out
    nudged = [nudge_numeric(genome, rng) for _ in range(max(1, gate_params.nudge_n))]
    if evaluate is None:
        sc = SeriesCache(data.bars)
        nudged_results = [evaluate_genome(data.bars, g, data.cost, data.m1_bars, data.split, sc) for g in nudged]
    else:
        nudged_results = evaluate.map(nudged)
    profitable = sum(1 for r in nudged_results if r["oos"]["net"] > 0)
    out["nudge"] = G.nudge_gate(profitable, len(nudged), gate_params.nudge_pass_pct)
    out["shuffle"] = G.shuffle_gate(result.get("oos_nets", []), data.start_equity, gate_params.max_dd_pct, gate_params.shuffle_n,
                                    seed=rng.randint(0, 2**31 - 1))
    return all(g["passed"] for g in out.values()), out


# ----------------------------------------------------------------------------- campaign
def _tournament(eligible: list[int], fits: list[float], rng: random.Random) -> int:
    best = eligible[rng.randrange(len(eligible))]
    for _ in range(TOURNAMENT_K - 1):
        cand = eligible[rng.randrange(len(eligible))]
        if fits[cand] > fits[best]:
            best = cand
    return best


def run_campaign(params: CampaignParams, data: CampaignData, progress_cb: Callable[[dict[str, Any]], None] | None = None,
                 should_stop: Callable[[], bool] | None = None) -> CampaignResult:
    """Deterministic (seeded) breeding run. progress_cb receives the SPEC §4 `campaign.progress` payload."""
    t0 = time.time()
    if len(data.bars) < 50:
        raise ValueError("campaign needs at least 50 bars")
    rng = random.Random(int(params.seed))
    ref_price = float(np.median(data.bars.close))
    gp = params.gates
    tribes = params.tribes
    total_units = len(tribes) * params.generations + 1
    done_units = 0
    records: list[dict[str, Any]] = []

    def report(tribe: str | None, generation: int, best: float, mean: float, survivors: int, stage: str) -> None:
        nonlocal done_units
        elapsed = time.time() - t0
        eta = (elapsed / done_units * (total_units - done_units)) if done_units > 0 else 0.0
        p = {"tribe": tribe, "generation": int(generation), "generations_total": int(params.generations),
             "best_fitness": round(float(best), 4), "mean_fitness": round(float(mean), 4), "survivors": int(survivors),
             "stage": stage, "elapsed_s": round(elapsed, 3), "eta_s": round(max(0.0, eta), 3)}
        records.append(p)
        if progress_cb:
            progress_cb(p)

    ev = Evaluator(data, params.workers)
    try:
        # ---- init: random population, screened by neutral IS fitness down to breed_pop
        population: list[dict] = []
        seen: set[str] = set()
        attempts = 0
        while len(population) < params.population and attempts < params.population * 20:
            attempts += 1
            g = random_genome(rng, rng.randint(2, 4), ref_price, params.timeframe)
            key = to_json(g)
            if key not in seen:
                seen.add(key)
                population.append(g)
        results = ev.map(population)
        init_fits = [score(r["is"])[0] for r in results]
        order = sorted(range(len(population)), key=lambda i: -init_fits[i])
        breed_pop = max(4, min(int(params.breed_pop), len(population)))
        screened = [(population[i], results[i]) for i in order[:breed_pop]]
        genomes = [g for g, _ in screened]
        tribe_results = [r for _, r in screened]
        report(None, 0, init_fits[order[0]], float(np.mean(init_fits)), 0, "init")

        # ---- tribes
        tribe_top: list[tuple[dict, dict[str, Any]]] = []
        for tribe in tribes:
            if tribe_top:  # every tribe starts from the same screened population
                genomes = [g for g, _ in screened]
                tribe_results = [r for _, r in screened]
            weights = tribe_weights(tribe)
            fits = [score(r["is"], weights)[0] for r in tribe_results]
            for gen in range(1, params.generations + 1):
                if should_stop is not None and should_stop():
                    return _finish(records, [], _empty_rejected(), ev, t0, True, [], [], "stopped")
                order = sorted(range(len(genomes)), key=lambda i: -fits[i])
                eligible = [i for i in order if tribe_results[i]["is"]["trades"] >= 1] or order  # CAM-02 analogue
                report(tribe, gen, fits[order[0]], float(np.mean(fits)), len(eligible), "breeding")
                done_units += 1
                next_g = [genomes[i] for i in order[:ELITES]]
                next_r = [tribe_results[i] for i in order[:ELITES]]
                children: list[dict] = []
                while len(next_g) + len(children) < breed_pop:
                    p1, p2 = _tournament(eligible, fits, rng), _tournament(eligible, fits, rng)
                    child = crossover(genomes[p1], genomes[p2], rng) if rng.random() < CROSSOVER_P else copy_genome(genomes[p1])
                    if rng.random() < MUTATION_P:
                        child = mutate(child, rng, ref_price)
                    if not is_valid(child):
                        child = copy_genome(genomes[p1])
                    children.append(child)
                genomes = next_g + children
                tribe_results = next_r + ev.map(children)
                fits = [score(r["is"], weights)[0] for r in tribe_results]
            order = sorted(range(len(genomes)), key=lambda i: -fits[i])
            keep = max(2 * ELITES, breed_pop // 2)
            tribe_top.extend((genomes[i], tribe_results[i]) for i in order[:keep])

        # ---- Final War: merge tribes, rank on OOS, apply gates
        if should_stop is not None and should_stop():
            return _finish(records, [], _empty_rejected(), ev, t0, True, [], [], "stopped")
        cand: list[tuple[dict, dict[str, Any]]] = []
        cand_keys: set[str] = set()
        for g, r in tribe_top:
            k = to_json(g)
            if k not in cand_keys:
                cand_keys.add(k)
                cand.append((g, r))
        cand_results = ev.map([g for g, _ in cand])
        ranked = sorted(range(len(cand)), key=lambda i: -score(cand_results[i]["oos"])[0])[: params.final_pool]
        oos_bars = int(cand_results[0]["oos"].get("oos_bars", 0)) if cand_results else 0
        random_genomes = [random_genome(rng, rng.randint(2, 4), ref_price, params.timeframe) for _ in range(max(1, gp.random_n))]
        random_field = [float(r["oos"]["net"]) for r in ev.map(random_genomes)]
        report("FinalWar", params.generations, 0.0, 0.0, 0, "final_war")
        ev.close()
        ev = Evaluator(data, 1)  # gates run in-process; no more heavy parallel work
        survivors: list[dict[str, Any]] = []
        rejected = _empty_rejected()
        gate_log: list[dict[str, Any]] = []
        for i in ranked:
            if len(survivors) >= params.max_survivors:
                break
            g, r = cand[i][0], cand_results[i]
            ok, gate_results = apply_gates(g, r, data, rng, gp, random_field, ev, oos_bars)
            for name, gres in gate_results.items():
                if not gres["passed"] and not gres.get("skipped"):
                    rejected[name] += 1
            gate_log.append({"genome_hash": str(hash(to_json(g)) % (10**12)), "passed": ok, "gates": gate_results})
            if ok:
                res = run_backtest(data.bars, g, data.cost, data.m1_bars)
                is_m, oos_m = split_results(res, data.split)
                oos_m["r_series"] = [round(float(t["r_multiple"]), 4) for t in res.trades if int(t["open_ts"]) >= int(res.oos_start_ts or 0)][:30]
                oos_m["oos_days"] = round((int(res.bars_ts[-1]) - int(res.oos_start_ts or res.bars_ts[-1])) / 86400.0, 3)
                total, parts = score(oos_m, robustness=float(gate_results["nudge"]["value"]) / 100.0)
                survivors.append({
                    "genome": g, "score": total, "parts": parts, "metrics": {"is": is_m, "oos": oos_m},
                    "equity": res.equity_with_oos(), "archetype": archetype_of(g), "mechanism": mechanism_of(g),
                    "gates": gate_results, "symbol": params.symbol, "timeframe": params.timeframe,
                })
        best = max((s["score"] for s in survivors), default=0.0)
        report("FinalWar", params.generations, best, best, len(survivors), "done")
        return _finish(records, survivors, rejected, ev, t0, False, random_field, gate_log, "done")
    finally:
        ev.close()


def _empty_rejected() -> dict[str, int]:
    return {"random_gate": 0, "shuffle": 0, "nudge": 0, "trades": 0, "persistence": 0}


def _finish(records: list[dict[str, Any]], survivors: list[dict[str, Any]], rejected: dict[str, int], ev: Evaluator, t0: float,
            stopped: bool, random_field: list[float], gate_log: list[dict[str, Any]], stage: str) -> CampaignResult:
    best = max((p["best_fitness"] for p in records if p["stage"] == "breeding"), default=0.0)
    return CampaignResult(survivors=survivors, rejected=rejected, generations=records, best_fitness=float(best),
                          elapsed_s=round(time.time() - t0, 3), stopped=stopped, random_field=random_field, gate_log=gate_log)


__all__ = ["MAX_WORKERS", "ELITES", "CampaignParams", "GateParams", "CampaignData", "CampaignResult", "Evaluator",
           "apply_gates", "executor_workers", "run_campaign"]
