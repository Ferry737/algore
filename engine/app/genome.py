"""Strategy genome grammar — SPEC §7, version 1. CLEAN-ROOM DESIGN.

expr  := {op: and|or, args:[expr,...]} | {op: not, arg:expr} | {op: >|<|>=|<=, left:term, right:term}
       | {op: cross_up|cross_down, left:term, right:term} | {op: rising|falling, arg:term, lookback:int>=2}
term  := {f: close|open|high|low|volume, shift>=1} | {f: rsi|atr|ema|sma|adx, n, shift?} | {f: bb_pos, n, k, shift?}
       | {f: ret, n, shift?} | {f: hour|dow, shift?} | {c: number}
Rules: depth <= 5, node count <= 25, 0 < n <= 200, shift >= 1 (closed bars only — no lookahead).
"""
from __future__ import annotations

import copy
import json
import math
import random
from typing import Any, Iterator

PRICE_FEATURES: tuple[str, ...] = ("close", "open", "high", "low", "volume")
INDICATOR_RANGES: dict[str, tuple[int, int]] = {
    "rsi": (2, 30), "atr": (5, 50), "ema": (5, 100), "sma": (5, 100), "bb_pos": (10, 50), "adx": (5, 30), "ret": (1, 20),
}
TIME_FEATURES: tuple[str, ...] = ("hour", "dow")
ALL_FEATURES: frozenset[str] = frozenset(PRICE_FEATURES) | frozenset(INDICATOR_RANGES) | frozenset(TIME_FEATURES)
CMP_OPS: tuple[str, ...] = (">", "<", ">=", "<=")
CROSS_OPS: tuple[str, ...] = ("cross_up", "cross_down")
SLOPE_OPS: tuple[str, ...] = ("rising", "falling")
ALL_OPS: frozenset[str] = frozenset(CMP_OPS + CROSS_OPS + SLOPE_OPS + ("and", "or", "not"))
MAX_DEPTH = 5
MAX_NODES = 25
MAX_N = 200
MAX_SHIFT = 50
ARCHETYPES: tuple[str, ...] = ("trend", "mean_reversion", "breakout", "momentum", "session")

Path = tuple[Any, ...]


class GenomeError(ValueError):
    """Raised when a genome violates the §7 grammar."""


# ----------------------------------------------------------------------------- tree utilities
def is_expr(node: Any) -> bool:
    return isinstance(node, dict) and "op" in node


def _children(expr: dict) -> list[tuple[Any, ...]]:
    op = expr["op"]
    if op in ("and", "or"):
        return [("args", i) for i in range(len(expr["args"]))]
    if op == "not":
        return [("arg",)]
    if op in SLOPE_OPS:
        return [("arg",)]
    return [("left",), ("right",)]


def _child(expr: dict, key: tuple[Any, ...]) -> Any:
    return expr[key[0]][key[1]] if key[0] == "args" else expr[key[0]]


def iter_exprs(expr: dict) -> Iterator[dict]:
    """Every expression node (dicts with an 'op'), pre-order."""
    yield expr
    for key in _children(expr):
        child = _child(expr, key)
        if is_expr(child):
            yield from iter_exprs(child)


def iter_terms(expr: dict) -> Iterator[dict]:
    for node in iter_exprs(expr):
        op = node["op"]
        if op in ("and", "or", "not"):
            continue
        if op in SLOPE_OPS:
            terms = [node["arg"]]
        else:
            terms = [node["left"], node["right"]]
        for t in terms:
            if isinstance(t, dict) and "op" not in t:
                yield t


def depth(expr: dict) -> int:
    children = [c for k in _children(expr) if is_expr(c := _child(expr, k))]
    return 1 + max((depth(c) for c in children), default=0)


def count_nodes(expr: dict) -> int:
    n = 1
    for key in _children(expr):
        child = _child(expr, key)
        n += count_nodes(child) if is_expr(child) else 1
    return n


def subtree_positions(expr: dict, prefix: Path = ()) -> list[Path]:
    out: list[Path] = [prefix]
    for key in _children(expr):
        child = _child(expr, key)
        if is_expr(child):
            out.extend(subtree_positions(child, prefix + (key,)))
    return out


def get(expr: dict, path: Path) -> Any:
    node: Any = expr
    for key in path:
        node = _child(node, key)
    return node


def set_inplace(expr: dict, path: Path, value: Any) -> dict:
    """Replace the subtree at `path`; returns the (possibly new) root."""
    if not path:
        return value
    parent = get(expr, path[:-1])
    key = path[-1]
    if key[0] == "args":
        parent["args"][key[1]] = value
    else:
        parent[key[0]] = value
    return expr


# ----------------------------------------------------------------------------- validation
def _check_term(t: dict, where: str) -> None:
    if "c" in t:
        if not isinstance(t["c"], (int, float)) or not math.isfinite(float(t["c"])):
            raise GenomeError(f"{where}: constant must be a finite number")
        return
    f = t.get("f")
    if f not in ALL_FEATURES:
        raise GenomeError(f"{where}: unknown feature {f!r}")
    s = int(t.get("shift", 1))
    if s < 1 or s > MAX_SHIFT:
        raise GenomeError(f"{where}: shift must be >= 1 (closed bars only)")
    if f in INDICATOR_RANGES:
        n = t.get("n")
        if not isinstance(n, (int, float)) or isinstance(n, bool) or not (0 < float(n) <= MAX_N):
            raise GenomeError(f"{where}: 0 < n <= {MAX_N} required for {f}")
        if f == "bb_pos":
            k = float(t.get("k", 2.0))
            if not (0 < k <= 10):
                raise GenomeError(f"{where}: bb_pos k must be in (0, 10]")


def _check_expr(expr: dict, where: str) -> None:
    if not is_expr(expr):
        raise GenomeError(f"{where}: expected an expression node")
    if depth(expr) > MAX_DEPTH:
        raise GenomeError(f"{where}: depth > {MAX_DEPTH}")
    if count_nodes(expr) > MAX_NODES:
        raise GenomeError(f"{where}: node count > {MAX_NODES}")
    for node in iter_exprs(expr):
        op = node["op"]
        if op not in ALL_OPS:
            raise GenomeError(f"{where}: unknown op {op!r}")
        if op in ("and", "or"):
            if not isinstance(node.get("args"), list) or len(node["args"]) < 2:
                raise GenomeError(f"{where}: {op} needs >= 2 args")
        elif op == "not":
            if not is_expr(node.get("arg")):
                raise GenomeError(f"{where}: not needs an expression arg")
        elif op in SLOPE_OPS:
            lb = node.get("lookback", 2)
            if not isinstance(lb, int) or isinstance(lb, bool) or not (1 <= lb <= 20):
                raise GenomeError(f"{where}: lookback must be an int in [1, 20]")
        else:
            _check_term(node["left"], where)
            _check_term(node["right"], where)


def validate(genome: dict) -> None:
    """Raise GenomeError unless the genome obeys every rule of SPEC §7."""
    if not isinstance(genome, dict) or genome.get("version") != 1:
        raise GenomeError("genome.version must be 1")
    for side in ("long", "short"):
        if side not in genome:
            raise GenomeError(f"missing {side}")
        _check_expr(genome[side], side)
    stops = genome.get("stops")
    if not isinstance(stops, dict):
        raise GenomeError("missing stops")
    for key in ("sl_atr_mult", "atr_period"):
        v = stops.get(key)
        if not isinstance(v, (int, float)) or not (v > 0):
            raise GenomeError(f"stops.{key} must be > 0")
    if not (0 < float(stops["atr_period"]) <= MAX_N):
        raise GenomeError("stops.atr_period out of range")
    for key in ("tp_atr_mult", "trail_atr_mult", "be_trigger_atr_mult"):
        v = stops.get(key)
        if v is not None and (not isinstance(v, (int, float)) or v <= 0):
            raise GenomeError(f"stops.{key} must be > 0 or null")
    sess = genome.get("session")
    if not isinstance(sess, dict) or not (0 <= int(sess.get("start_hour", 0)) <= 23) or not (1 <= int(sess.get("end_hour", 24)) <= 24):
        raise GenomeError("session hours out of range")
    if float(genome.get("max_spread_points", 0)) < 0:
        raise GenomeError("max_spread_points must be >= 0")
    risk = genome.get("risk") or {}
    if not (float(risk.get("risk_pct", 0)) > 0):
        raise GenomeError("risk.risk_pct must be > 0")


def is_valid(genome: dict) -> bool:
    try:
        validate(genome)
    except (GenomeError, TypeError, ValueError, KeyError):
        return False
    return True


def to_json(genome: dict) -> str:
    validate(genome)
    return json.dumps(genome, separators=(",", ":"), sort_keys=True)


def from_json(text: str) -> dict:
    genome = json.loads(text)
    validate(genome)
    return genome


def copy_genome(genome: dict) -> dict:
    return copy.deepcopy(genome)


# ----------------------------------------------------------------------------- random generation
def _random_constant(rng: random.Random, ref_price: float, kind: str | None) -> float:
    if kind == "rsi":
        return round(rng.uniform(20.0, 80.0), 1)
    if kind == "adx":
        return round(rng.uniform(10.0, 45.0), 1)
    if kind == "bb_pos":
        return round(rng.uniform(-1.5, 1.5), 2)
    if kind == "ret":
        return round(rng.uniform(-0.01, 0.01), 5)
    if kind == "hour":
        return float(rng.randint(0, 23))
    if kind == "dow":
        return float(rng.randint(0, 6))
    if kind == "atr":
        return round(ref_price * rng.uniform(0.0002, 0.004), 6)
    if kind == "volume":
        return float(rng.randint(50, 1000))
    return round(ref_price * rng.uniform(0.97, 1.03), 6)


def random_term(rng: random.Random, ref_price: float = 1.0, shift_max: int = 3) -> dict:
    r = rng.random()
    if r < 0.32:
        return {"f": rng.choice(PRICE_FEATURES), "shift": rng.randint(1, shift_max)}
    if r < 0.86:
        f = rng.choice(list(INDICATOR_RANGES))
        lo, hi = INDICATOR_RANGES[f]
        t: dict[str, Any] = {"f": f, "n": rng.randint(lo, hi), "shift": rng.randint(1, 2)}
        if f == "bb_pos":
            t["k"] = round(rng.uniform(1.0, 3.0), 1)
        return t
    if r < 0.94:
        return {"f": rng.choice(TIME_FEATURES), "shift": 1}
    return {"c": _random_constant(rng, ref_price, None)}


def random_comparison(rng: random.Random, ref_price: float = 1.0) -> dict:
    r = rng.random()
    if r < 0.55:
        left = random_term(rng, ref_price)
        kind = left.get("f") if "c" not in left else None
        right = {"c": _random_constant(rng, ref_price, kind)} if (kind and rng.random() < 0.35) else random_term(rng, ref_price)
        return {"op": rng.choice(CMP_OPS), "left": left, "right": right}
    if r < 0.82:
        return {"op": rng.choice(CROSS_OPS), "left": random_term(rng, ref_price, 2), "right": random_term(rng, ref_price, 2)}
    return {"op": rng.choice(SLOPE_OPS), "arg": random_term(rng, ref_price, 2), "lookback": rng.choice((2, 2, 3))}


def random_expr(rng: random.Random, depth: int, ref_price: float = 1.0) -> dict:
    if depth <= 0 or rng.random() > {1: 0.6, 2: 0.55, 3: 0.45, 4: 0.35}.get(depth, 0.3):
        return random_comparison(rng, ref_price)
    r = rng.random()
    if r < 0.75:
        return {"op": rng.choice(("and", "or")), "args": [random_expr(rng, depth - 1, ref_price) for _ in range(2)]}
    return {"op": "not", "arg": random_expr(rng, depth - 1, ref_price)}


def _finalize(genome: dict) -> dict:
    genome.setdefault("meta", {})
    genome["meta"]["archetype"] = archetype_of(genome)
    genome["meta"]["mechanism"] = mechanism_of(genome)
    return genome


def random_genome(rng: random.Random, depth: int = 3, ref_price: float = 1.0, timeframe: str = "H1") -> dict:
    """Random bounded genome (trees of depth 2..`depth`); retries until the grammar holds."""
    d = max(1, min(int(depth), MAX_DEPTH - 1))
    for _ in range(80):
        if rng.random() < 0.3:
            start = rng.randint(0, 12)
            session = {"start_hour": start, "end_hour": min(24, start + rng.randint(6, 14)), "timezone": "server"}
        else:
            session = {"start_hour": 0, "end_hour": 24, "timezone": "server"}
        genome = {
            "version": 1,
            "timeframe": timeframe,
            "long": random_expr(rng, rng.randint(2, d), ref_price),
            "short": random_expr(rng, rng.randint(2, d), ref_price),
            "stops": {
                "sl_atr_mult": round(rng.uniform(1.0, 2.5), 2),
                "tp_atr_mult": round(rng.uniform(1.5, 5.0), 2),
                "atr_period": rng.choice((7, 14, 21)),
                "trail_atr_mult": round(rng.uniform(1.5, 3.0), 2) if rng.random() < 0.3 else None,
                "be_trigger_atr_mult": round(rng.uniform(0.5, 1.5), 2) if rng.random() < 0.3 else None,
            },
            "session": session,
            "max_spread_points": rng.choice((20, 30, 50)),
            "risk": {"risk_pct": round(rng.uniform(0.25, 1.0), 2)},
        }
        if is_valid(genome):
            return _finalize(genome)
    raise GenomeError("could not generate a valid genome")


# ----------------------------------------------------------------------------- variation operators
_OP_SWAP = {"and": "or", "or": "and", ">": "<", "<": ">", ">=": "<=", "<=": ">=",
            "cross_up": "cross_down", "cross_down": "cross_up", "rising": "falling", "falling": "rising"}


def crossover(a: dict, b: dict, rng: random.Random) -> dict:
    """Subtree swap: replace a random expression subtree of `a` with one from the same side of `b`."""
    child = copy.deepcopy(a)
    side = rng.choice(("long", "short"))
    pos_a = subtree_positions(child[side])
    pos_b = subtree_positions(b[side])
    if pos_a and pos_b:
        sub = copy.deepcopy(get(b[side], rng.choice(pos_b)))
        child[side] = set_inplace(child[side], rng.choice(pos_a), sub)
    if is_valid(child):
        return _finalize(child)
    return mutate(child, rng)


def mutate(genome: dict, rng: random.Random, ref_price: float | None = None) -> dict:
    """One of: operator swap / constant jitter / feature swap / subtree regrow. Bounded by validate()."""
    ref = float(ref_price) if ref_price is not None else _ref_from(genome)
    for _ in range(12):
        g = copy.deepcopy(genome)
        kind = rng.choice(("operator", "constant", "feature", "regrow"))
        side = rng.choice(("long", "short"))
        expr = g[side]
        exprs = subtree_positions(expr)
        terms = list(iter_terms(expr))
        if kind == "operator" and exprs:
            node = get(expr, rng.choice(exprs))
            node["op"] = _OP_SWAP[node["op"]]
            if node["op"] in SLOPE_OPS and "lookback" not in node:
                node["lookback"] = 2
        elif kind == "constant" and terms:
            t = rng.choice(terms)
            if "c" in t:
                t["c"] = round(float(t["c"]) * rng.uniform(0.8, 1.2), 8)
            elif "n" in t:
                t["n"] = int(min(MAX_N, max(1, round(float(t["n"]) * rng.uniform(0.8, 1.2)))))
            elif "k" in t:
                t["k"] = round(float(t["k"]) * rng.uniform(0.8, 1.2), 2)
            else:
                t["shift"] = int(min(MAX_SHIFT, max(1, int(t.get("shift", 1)) + rng.choice((-1, 1)))))
        elif kind == "feature" and terms:
            t = rng.choice(terms)
            if "f" in t and t["f"] in INDICATOR_RANGES:
                f = rng.choice([k for k in INDICATOR_RANGES if k != t["f"]])
                lo, hi = INDICATOR_RANGES[f]
                t["f"], t["n"] = f, rng.randint(lo, hi)
                t.pop("k", None)
                if f == "bb_pos":
                    t["k"] = round(rng.uniform(1.0, 3.0), 1)
            elif "f" in t and t["f"] in PRICE_FEATURES:
                t["f"] = rng.choice([k for k in PRICE_FEATURES if k != t["f"]])
            elif "c" in t:
                t["c"] = _random_constant(rng, ref, None)
            else:
                continue
        elif kind == "regrow" and exprs:
            expr = set_inplace(expr, rng.choice(exprs), random_expr(rng, 2, ref))
            g[side] = expr
        else:
            continue
        if is_valid(g):
            return _finalize(g)
    return copy.deepcopy(genome)


def _ref_from(genome: dict) -> float:
    for side in ("long", "short"):
        for t in iter_terms(genome[side]):
            if "c" in t and abs(float(t["c"])) > 0.5:
                return float(t["c"])
    return 1.0


def nudge_numeric(genome: dict, rng: random.Random, frac: float = 0.10) -> dict:
    """Multiplicative ±frac on every numeric gene (n, k, c, stop multiples, atr_period, risk_pct)."""

    def jitter(v: float, integral: bool = False) -> float:
        nv = float(v) * (1.0 + rng.uniform(-frac, frac))
        return float(int(min(MAX_N, max(1, round(nv))))) if integral else nv

    g = copy.deepcopy(genome)
    for side in ("long", "short"):
        for t in iter_terms(g[side]):
            if "n" in t:
                t["n"] = int(jitter(t["n"], True))
            if "k" in t:
                t["k"] = round(jitter(t["k"]), 3)
            if "c" in t:
                t["c"] = jitter(t["c"])
    s = g["stops"]
    for key in ("sl_atr_mult", "tp_atr_mult", "trail_atr_mult", "be_trigger_atr_mult"):
        if s.get(key) is not None:
            s[key] = round(jitter(s[key]), 3)
    s["atr_period"] = int(jitter(s["atr_period"], True))
    g["risk"]["risk_pct"] = round(max(0.01, jitter(g["risk"]["risk_pct"])), 4)
    return _finalize(g) if is_valid(g) else copy.deepcopy(genome)


# ----------------------------------------------------------------------------- derived labels
def features_used(genome: dict) -> set[str]:
    return {t["f"] for side in ("long", "short") for t in iter_terms(genome[side]) if "f" in t}


def ops_used(genome: dict) -> set[str]:
    return {n["op"] for side in ("long", "short") for n in iter_exprs(genome[side])}


def archetype_of(genome: dict) -> str:
    """Rule-based archetype from dominant features/ops (five archetypes, CAM-21)."""
    score: dict[str, int] = {a: 0 for a in ARCHETYPES}
    for f in features_used(genome):
        if f in ("ema", "sma", "adx", "atr"):
            score["trend"] += 1
        if f in ("rsi", "bb_pos"):
            score["mean_reversion"] += 1
        if f in ("high", "low"):
            score["breakout"] += 1
        if f == "ret":
            score["momentum"] += 1
        if f in TIME_FEATURES:
            score["session"] += 1
    ops = ops_used(genome)
    if ops & set(CROSS_OPS):
        score["trend"] += 1
    if ops & set(SLOPE_OPS):
        score["momentum"] += 1
    best = max(score.items(), key=lambda kv: (kv[1], -ARCHETYPES.index(kv[0])))
    return best[0] if best[1] > 0 else "trend"


def mechanism_of(genome: dict) -> str:
    ops = sorted(ops_used(genome))
    feats = sorted(features_used(genome))
    return f"{'+'.join(ops)} on {', '.join(feats)}" if feats else "constant rules"
