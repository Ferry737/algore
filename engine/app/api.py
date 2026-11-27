"""AlgoRE FastAPI application — SPEC §4/§5 HTTP + WebSocket contract.

All endpoints live under ``/api/v1``. Authentication is Bearer JWT (HS256); scopes are
``dashboard``, ``pilot`` and ``bot:<bot_id>``. ``create_app(settings)`` builds an isolated
app (its own DB connections, event bus and rate limiters) so tests can run in parallel.
"""
from __future__ import annotations

import asyncio
import csv as _csv
import io
import json
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import jwt
from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import ValidationError

from . import auth, db, events, incubation as inc, portfolio as pf, vault
from .bars import Bars, timeframe_minutes
from .breeder import CampaignData, CampaignParams, GateParams, run_campaign
from .config import Settings
from .demo_seed import synthetic_m1
from .genome import iter_terms
from .mql5_exporter import export_ea
from .parity_backtester import CostModel
from .ratelimit import RateLimiter
from .schemas import (
    AutoRequest, CampaignCreate, DataImportRequest, ParityRequest, PauseAllRequest, PauseRequest,
    PilotEnvelope, PilotTokenRequest, PortfolioCreate, PortfolioDeploy, RungRequest, TokenRequest,
)

BASE = "/api/v1"
_INVALID = "invalid or missing token"


# ----------------------------------------------------------------------------- small helpers
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(str(text).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None


def _age_s(text: str | None) -> float:
    at = _parse_iso(text)
    return (_now() - at).total_seconds() if at is not None else 1e18


def _rowdict(row: Any) -> dict[str, Any]:
    return dict(row) if row is not None else {}


def _json(text: str | None, default: Any) -> Any:
    try:
        return json.loads(text) if text else default
    except (TypeError, ValueError):
        return default


# ----------------------------------------------------------------------------- app factory
def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    bus = events.EventBus(settings.db_path)
    general_bucket = RateLimiter(settings.rate_limit_per_min)
    ingest_bucket = RateLimiter(settings.ingest_rate_limit_per_min)

    def conn() -> Any:
        return db.connect(settings.db_path)

    # ------------------------------------------------------------------ auth dependencies
    def _payload(request: Request, needed: str | None, bot_id: str | None = None) -> dict[str, Any]:
        header = request.headers.get("authorization", "")
        parts = header.split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
            raise HTTPException(status_code=401, detail=_INVALID)
        try:
            payload = auth.decode_token(parts[1], settings.jwt_secret)
        except (auth.AuthError, jwt.PyJWTError):
            raise HTTPException(status_code=401, detail=_INVALID)
        if bot_id is not None:
            allowed = auth.grants(payload, "dashboard") or payload.get("scope") == auth.bot_scope(bot_id)
        elif needed == auth.SCOPE_PILOT:
            # Pilot ingress is a device credential: a dashboard token is deliberately NOT accepted.
            allowed = payload.get("scope") == auth.SCOPE_PILOT
        else:
            allowed = auth.grants(payload, needed or "dashboard")
        if not allowed:
            raise HTTPException(status_code=403, detail="scope")
        return payload

    def dashboard(request: Request) -> dict[str, Any]:
        return _payload(request, "dashboard")

    def pilot(request: Request) -> dict[str, Any]:
        return _payload(request, auth.SCOPE_PILOT)

    def bot_or_dashboard(request: Request, bot_id: str) -> dict[str, Any]:
        return _payload(request, None, bot_id=bot_id)

    # ------------------------------------------------------------------ lifespan
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        c = conn()
        try:
            db.init_db(c)
        finally:
            c.close()
        bus.attach_loop(asyncio.get_running_loop())
        try:
            yield
        finally:
            bus.detach_loop()

    app = FastAPI(title="AlgoRE engine", version=settings.version, lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.bus = bus

    # ------------------------------------------------------------------ middleware
    @app.middleware("http")
    async def _rate_limit(request: Request, call_next: Callable):
        path = request.url.path
        bucket = ingest_bucket if path.endswith("/pilot/ingest") else general_bucket
        key = request.headers.get("authorization") or (request.client.host if request.client else "unknown")
        allowed, retry = bucket.allow(key)
        if not allowed:
            return JSONResponse({"detail": "rate limited", "retry_after": retry}, status_code=429,
                                headers={"Retry-After": str(retry)})
        return await call_next(request)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------ pilot state helpers
    def _hb_rows(c: Any, limit: int = 200) -> list[dict[str, Any]]:
        rows = db.fetchall(c, "SELECT * FROM pilot_heartbeats ORDER BY received_at DESC, sent_at DESC LIMIT ?", (limit,))
        return [_rowdict(r) for r in rows]

    def _pilot_online(c: Any) -> bool:
        rows = _hb_rows(c, 1)
        return bool(rows) and _age_s(rows[0]["received_at"]) <= settings.pilot_offline_s

    def _last_hb(c: Any) -> dict[str, Any] | None:
        rows = _hb_rows(c, 1)
        return rows[0] if rows else None

    def _hb_bot_magics(row: dict[str, Any] | None) -> set[str]:
        if not row:
            return set()
        bots = _json(row.get("bots_json"), []) or []
        return {str(b.get("magic")) for b in bots if isinstance(b, dict) and b.get("magic") is not None}

    def _pilot_state(c: Any, bot_row: dict[str, Any]) -> str:
        if not _pilot_online(c):
            return "PILOT_OFFLINE"
        magic = str(bot_row.get("magic"))
        rows = _hb_rows(c, 50)
        recent = [r for r in rows if _age_s(r.get("received_at")) <= settings.ea_silent_s]
        if any(magic in _hb_bot_magics(r) for r in recent):
            return "ONLINE"
        return "EA_SILENT"

    # ------------------------------------------------------------------ incubation context/view
    def _ctx(c: Any, bot_row: dict[str, Any], state: inc.BotState,
             pstate: str | None = None) -> inc.IncubationContext:
        pstate = pstate or _pilot_state(c, bot_row)
        strategy = db.fetchone(c, "SELECT metrics_json FROM strategies WHERE id = ?", (bot_row["strategy_id"],))
        metrics = _json(strategy["metrics_json"] if strategy else None, {}) or {}
        oos = metrics.get("oos") or {}
        try:
            bt_mean_r = float(oos.get("expectancy_r") or 0.5)
        except (TypeError, ValueError):
            bt_mean_r = 0.5
        if bt_mean_r <= 0:
            bt_mean_r = 0.5
        try:
            bt_dd = abs(float(oos.get("max_dd_pct") or 0.0))
        except (TypeError, ValueError):
            bt_dd = 0.0
        verdict = vault.latest_verdict(c, bot_row["strategy_id"])
        trades = db.fetchall(c, "SELECT r_multiple FROM pilot_trades WHERE bot_id = ? ORDER BY ingested_at DESC LIMIT 40",
                             (bot_row["bot_id"],))
        rs = [float(t["r_multiple"]) for t in trades]
        streak = 0
        for r in rs:
            if r < 0:
                streak += 1
            else:
                break
        deployed = _parse_iso(bot_row.get("deployed_at"))
        deployed_days = (_now() - deployed).total_seconds() / 86400.0 if deployed else 0.0
        period_start = (_now() - timedelta(days=settings.silence_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        live_recent = db.scalar(c, "SELECT COUNT(*) FROM pilot_trades WHERE bot_id = ? AND close_time >= ?",
                                (bot_row["bot_id"], period_start)) or 0
        expected = max(1.0, float(oos.get("trades") or 10.0) * min(1.0, max(0.05, deployed_days / 30.0)))
        return inc.IncubationContext(
            pilot_online=pstate != "PILOT_OFFLINE",
            sim_ok=False,
            decay_verdict=verdict if verdict in ("WEAKENING", "REPLACE") else None,
            backtest_max_dd_pct=bt_dd,
            backtest_mean_r=bt_mean_r,
            consecutive_losses=streak,
            live_trades_last_period=float(live_recent),
            expected_trades_last_period=expected,
            deployed_days=max(0.0, deployed_days),
            hot_trades=settings.hot_trades, hot_wins=settings.hot_wins,
            silence_days=settings.silence_days, silence_ratio=settings.silence_ratio,
        )

    def _bot(row: Any) -> dict[str, Any]:
        """Normalise a `bots` row (`id` column) into the API's `bot_id` shape."""
        out = _rowdict(row)
        if "bot_id" not in out and "id" in out:
            out["bot_id"] = out["id"]
        return out

    def _bot_row(c: Any, bot_id: str) -> dict[str, Any] | None:
        row = db.fetchone(c, "SELECT * FROM bots WHERE id = ?", (bot_id,))
        return _bot(row) if row is not None else None

    def _state(c: Any, bot_id: str) -> inc.BotState:
        row = db.fetchone(c, "SELECT * FROM incubation_states WHERE bot_id = ?", (bot_id,))
        if row is None:
            return inc.initial_state(bot_id)
        return inc.BotState.from_row(row)

    def _save(c: Any, state: inc.BotState) -> None:
        db.upsert(c, "incubation_states", **state.to_row())

    def _view(c: Any, bot_row: dict[str, Any], state: inc.BotState | None = None,
              pstate: str | None = None) -> dict[str, Any]:
        state = state or _state(c, bot_row["bot_id"])
        pstate = pstate or _pilot_state(c, bot_row)
        ctx = _ctx(c, bot_row, state, pstate)
        ev = inc.evaluate(state, ctx)
        effective = ev.state
        try:
            target = float(bot_row["target_risk_pct"])
        except (TypeError, ValueError):
            target = 0.0
        return {
            "bot_id": bot_row["bot_id"], "strategy_id": bot_row["strategy_id"],
            "tier": effective.tier, "multiplier": round(float(effective.multiplier), 6),
            "target_risk_pct": target,
            "effective_risk_pct": round(target * float(effective.multiplier), 6),
            "auto": bool(effective.auto), "paused": bool(effective.paused),
            "frozen_reason": effective.frozen_reason, "health_word": effective.health_word,
            "pending_graduation": bool(effective.pending_graduation),
            "live_trades": int(effective.live_trades),
            "healthy_live_trades": int(effective.healthy_live_trades),
            "live_net_r": round(float(effective.live_net_r), 6),
            "checks": ev.checks, "pilot_state": pstate, "updated_at": effective.updated_at,
        }

    def _publish_transitions(transitions: list[dict[str, Any]]) -> None:
        for tr in transitions or []:
            bus.publish("incubation.transition", dict(tr))

    # ------------------------------------------------------------------ auth / health
    @app.post(BASE + "/auth/token")
    def token(body: TokenRequest):
        tok = auth.issue_dashboard(body.api_key, settings.jwt_secret, settings.dashboard_api_key)
        if tok is None:
            raise HTTPException(status_code=401, detail=_INVALID)
        return {"access_token": tok, "token_type": "Bearer", "expires_in": auth.DASHBOARD_TTL_S}

    @app.get(BASE + "/health")
    def health():
        c = conn()
        try:
            try:
                db.scalar(c, "SELECT 1")
                db_ok = "ok"
            except Exception:
                db_ok = "error"
            active = db.scalar(c, "SELECT COUNT(*) FROM campaigns WHERE status IN ('queued','running')") or 0
            n_bots = db.scalar(c, "SELECT COUNT(*) FROM bots") or 0
            return {"status": "ok", "version": settings.version, "time": db.utcnow_iso(), "db": db_ok,
                    "campaigns_active": int(active), "pilot_online": bool(_pilot_online(c)), "bots": int(n_bots)}
        finally:
            c.close()

    # ------------------------------------------------------------------ bars
    def _csv_rows(text: str) -> list[dict[str, Any]]:
        reader = _csv.DictReader(io.StringIO(text))
        rows: list[dict[str, Any]] = []
        for r in reader:
            rows.append({
                "ts": int(r["ts"]), "open": float(r["open"]), "high": float(r["high"]),
                "low": float(r["low"]), "close": float(r["close"]),
                "volume": float(r.get("volume") or 0.0),
            })
        return rows

    @app.post(BASE + "/data/import")
    def data_import(body: DataImportRequest, _=Depends(dashboard)):
        raw = body.bars if body.bars is not None else _csv_rows(body.csv or "")
        rows = [r if isinstance(r, dict) else r.model_dump() for r in raw]
        values = [(body.symbol, body.timeframe.upper(), int(r["ts"]), float(r["open"]), float(r["high"]),
                   float(r["low"]), float(r["close"]), float(r.get("volume") or 0.0)) for r in rows]
        c = conn()
        try:
            c.executemany(
                "INSERT OR REPLACE INTO bars(symbol,timeframe,ts,open,high,low,close,volume) VALUES (?,?,?,?,?,?,?,?)",
                values,
            )
        finally:
            c.close()
        ts = [int(r["ts"]) for r in rows]
        return {"symbol": body.symbol, "timeframe": body.timeframe.upper(), "inserted": len(rows),
                "first_ts": min(ts) if ts else None, "last_ts": max(ts) if ts else None}

    @app.get(BASE + "/data")
    def data_list(_=Depends(dashboard)):
        c = conn()
        try:
            rows = db.fetchall(c, "SELECT symbol,timeframe,COUNT(*) AS n,MIN(ts) AS first_ts,MAX(ts) AS last_ts "
                                   "FROM bars GROUP BY symbol,timeframe ORDER BY symbol,timeframe")
            return [{"symbol": r["symbol"], "timeframe": r["timeframe"], "bars": int(r["n"]),
                     "first_ts": int(r["first_ts"]), "last_ts": int(r["last_ts"])} for r in rows]
        finally:
            c.close()

    def _load_bars(c: Any, symbol: str, timeframe: str) -> tuple[Bars, Bars | None]:
        rows = db.fetchall(c, "SELECT ts,open,high,low,close,volume FROM bars WHERE symbol = ? AND timeframe = 'M1' ORDER BY ts",
                           (symbol,))
        m1 = Bars.from_rows([dict(r) for r in rows], "M1", symbol=symbol) if rows else Bars.empty("M1", symbol)
        minutes = timeframe_minutes(timeframe)
        if minutes <= 1 or len(m1) == 0:
            return m1, (m1 if len(m1) else None)
        return m1.resample(minutes), m1

    # ------------------------------------------------------------------ campaigns
    def _campaign_row(c: Any, cid: str) -> dict[str, Any] | None:
        row = db.fetchone(c, "SELECT * FROM campaigns WHERE id = ?", (cid,))
        return _rowdict(row)

    def _campaign_progress(c: Any, cid: str) -> dict[str, Any]:
        rows = db.fetchall(c, "SELECT topic,payload_json FROM events WHERE topic = 'campaign.progress' ORDER BY id")
        for row in reversed(rows):
            payload = _json(row["payload_json"], {}) or {}
            if payload.get("campaign_id") == cid:
                return payload
        return {"campaign_id": cid, "tribe": None, "generation": 0, "generations_total": 0,
                "best_fitness": 0.0, "mean_fitness": 0.0, "survivors": 0, "stage": "queued",
                "elapsed_s": 0.0, "eta_s": 0.0}

    def _campaign_summary(c: Any, row: dict[str, Any]) -> dict[str, Any]:
        params = _json(row.get("params_json"), {}) or {}
        gens = db.fetchall(c, "SELECT tribe,generation,best_fitness FROM campaign_generations WHERE campaign_id = ?",
                           (row["id"],))
        progress = _campaign_progress(c, row["id"])
        vaulted = [r["id"] for r in db.fetchall(c, "SELECT id FROM strategies WHERE campaign_id = ?", (row["id"],))]
        return {
            "campaign_id": row["id"], "name": row["name"], "symbol": row["symbol"],
            "timeframe": row["timeframe"], "status": row["status"],
            "generation": int(max((g["generation"] for g in gens), default=0)),
            "generations_total": int(params.get("generations", 0)),
            "best_fitness": round(max((float(g["best_fitness"] or 0.0) for g in gens), default=0.0), 4),
            "stage": progress.get("stage", row["status"]),
            "elapsed_s": progress.get("elapsed_s", 0.0), "eta_s": progress.get("eta_s", 0.0),
            "vaulted": vaulted,
        }

    def _run_campaign(cid: str, params: CampaignParams) -> None:
        c = conn()
        try:
            bars, m1_bars = _load_bars(c, params.symbol, params.timeframe)
            db.update(c, "campaigns", {"id": cid}, {"status": "running", "started_at": db.utcnow_iso()})
            if len(bars) < 50:
                raise ValueError("campaign needs at least 50 bars")
            data = CampaignData(bars=bars, m1_bars=m1_bars, cost=CostModel.for_symbol(params.symbol))

            def progress(p: dict[str, Any]) -> None:
                payload = {"campaign_id": cid, **p}
                try:
                    db.upsert(c, "campaign_generations", campaign_id=cid, tribe=p.get("tribe") or "init",
                              generation=int(p.get("generation", 0)), best_fitness=p.get("best_fitness"),
                              mean_fitness=p.get("mean_fitness"), survivors=p.get("survivors"), elapsed_s=p.get("elapsed_s"))
                except Exception:
                    pass
                bus.publish("campaign.progress", payload)
                if p.get("stage") == "breeding":
                    time.sleep(0.15)  # observable progress window so /stop can be exercised

            def should_stop() -> bool:
                try:
                    return db.scalar(c, "SELECT status FROM campaigns WHERE id = ?", (cid,)) == "stopped"
                except Exception:
                    return False

            result = run_campaign(params, data, progress_cb=progress, should_stop=should_stop)
            if should_stop():
                db.update(c, "campaigns", {"id": cid}, {"finished_at": db.utcnow_iso()})
                return
            ids = []
            trained_until = int(bars.ts[-1]) if len(bars) else None
            for s in result.survivors:
                ids.append(vault.add_strategy(c, s, campaign_id=cid, symbol=params.symbol,
                                              timeframe=params.timeframe, trained_until=trained_until))
                bus.publish("vault.added", {"strategy_id": ids[-1], "name": s.get("archetype", "strategy"),
                                            "symbol": params.symbol, "timeframe": params.timeframe,
                                            "score": s.get("score", 0.0)})
            db.update(c, "campaigns", {"id": cid}, {
                "status": "done", "finished_at": db.utcnow_iso(),
                "stats_json": json.dumps({"vaulted": ids, "rejected": result.rejected,
                                          "best_fitness": result.best_fitness, "elapsed_s": result.elapsed_s}),
            })
            bus.publish("campaign.done", {"campaign_id": cid, "vaulted": ids, "rejected": result.rejected})
        except Exception as exc:  # noqa: BLE001 — surface as a failed campaign row
            try:
                db.update(c, "campaigns", {"id": cid},
                          {"status": "stopped" if db.scalar(c, "SELECT status FROM campaigns WHERE id = ?", (cid,)) == "stopped" else "failed",
                           "finished_at": db.utcnow_iso(), "error": str(exc)[:500]})
            except Exception:
                pass
        finally:
            c.close()

    @app.post(BASE + "/campaigns", status_code=202)
    def campaign_create(body: CampaignCreate, _=Depends(dashboard)):
        cid = uuid.uuid4().hex[:12]
        gates = GateParams(
            random_n=body.gates.random_n, random_beat_pct=body.gates.random_beat_pct,
            shuffle_n=body.gates.shuffle_n, max_dd_pct=body.gates.max_dd_pct,
            nudge_n=body.gates.nudge_n, nudge_pass_pct=body.gates.nudge_pass_pct,
            min_oos_trades=body.gates.min_oos_trades, min_persistence=body.gates.min_persistence,
        )
        params = CampaignParams(name=body.name, symbol=body.symbol, timeframe=body.timeframe,
                                generations=body.generations, population=body.population,
                                breed_pop=body.breed_pop, seed=body.seed, tribes=tuple(body.tribes),
                                gates=gates, workers=settings.breed_workers)
        c = conn()
        try:
            db.insert(c, "campaigns", id=cid, name=body.name, symbol=body.symbol, timeframe=body.timeframe,
                      status="queued", params_json=body.model_dump_json(), created_at=db.utcnow_iso())
        finally:
            c.close()
        threading.Thread(target=_run_campaign, args=(cid, params), daemon=True,
                         name=f"campaign-{cid}").start()
        return {"campaign_id": cid, "status": "queued"}

    @app.get(BASE + "/campaigns")
    def campaign_list(_=Depends(dashboard)):
        c = conn()
        try:
            rows = db.fetchall(c, "SELECT * FROM campaigns ORDER BY created_at DESC, rowid DESC")
            return [_campaign_summary(c, _rowdict(r)) for r in rows]
        finally:
            c.close()

    @app.get(BASE + "/campaigns/{cid}")
    def campaign_get(cid: str, _=Depends(dashboard)):
        c = conn()
        try:
            row = _campaign_row(c, cid)
            if row is None:
                raise HTTPException(status_code=404, detail="not found")
            out = dict(row)
            out.pop("params_json", None)
            out["progress"] = _campaign_progress(c, cid)
            gens = db.fetchall(c, "SELECT tribe,generation,best_fitness,mean_fitness,survivors,elapsed_s "
                                  "FROM campaign_generations WHERE campaign_id = ? ORDER BY tribe,generation", (cid,))
            out["generations"] = [_rowdict(g) for g in gens]
            stats = _json(row.get("stats_json"), {}) or {}
            rejected = stats.get("rejected", {}) or {}
            out["gates"] = {"passed": bool(stats.get("vaulted")), "rejected_by": rejected,
                            "vaulted": stats.get("vaulted", [])}
            return out
        finally:
            c.close()

    @app.post(BASE + "/campaigns/{cid}/stop")
    def campaign_stop(cid: str, _=Depends(dashboard)):
        c = conn()
        try:
            if _campaign_row(c, cid) is None:
                raise HTTPException(status_code=404, detail="not found")
            db.update(c, "campaigns", {"id": cid}, {"status": "stopped", "finished_at": db.utcnow_iso()})
            return {"status": "stopped"}
        finally:
            c.close()

    # ------------------------------------------------------------------ vault
    @app.get(BASE + "/vault")
    def vault_list(min_score: float | None = None, symbol: str | None = None, timeframe: str | None = None,
                   archetype: str | None = None, _=Depends(dashboard)):
        c = conn()
        try:
            return vault.list_vault(c, min_score=min_score, symbol=symbol, timeframe=timeframe, archetype=archetype)
        finally:
            c.close()

    def _strategy_or_404(c: Any, sid: str) -> dict[str, Any]:
        row = db.fetchone(c, "SELECT * FROM strategies WHERE id = ?", (sid,))
        if row is None:
            raise HTTPException(status_code=404, detail="not found")
        return _rowdict(row)

    @app.get(BASE + "/vault/{sid}")
    def vault_get(sid: str, _=Depends(dashboard)):
        c = conn()
        try:
            p = vault.passport(c, sid)
            if p is None:
                raise HTTPException(status_code=404, detail="not found")
            return p
        finally:
            c.close()

    @app.get(BASE + "/vault/{sid}/export.mq5")
    def vault_export(sid: str, _=Depends(dashboard)):
        c = conn()
        try:
            row = _strategy_or_404(c, sid)
            genome = _json(row["genome_json"], None)
            name = row.get("name") or sid
            src = export_ea(genome, name=str(name), bot_id=sid, magic=900001,
                            api_base=settings.public_url, bot_token="<bot JWT>")
            return PlainTextResponse(src, media_type="text/plain; charset=utf-8",
                                     headers={"Content-Disposition": f'attachment; filename="{name}.mq5"'})
        finally:
            c.close()

    @app.post(BASE + "/vault/{sid}/parity")
    def vault_parity(sid: str, body: ParityRequest, _=Depends(dashboard)):
        c = conn()
        try:
            row = _strategy_or_404(c, sid)
            metrics = _json(row.get("metrics_json"), {}) or {}
            engine_net = float((metrics.get("oos") or {}).get("return_pct", 0.0))
            return vault.record_parity(c, sid, body.mt5_net_return, engine_net)
        finally:
            c.close()

    @app.post(BASE + "/vault/{sid}/reassess")
    def vault_reassess(sid: str, _=Depends(dashboard)):
        c = conn()
        try:
            row = _strategy_or_404(c, sid)
            bars, m1_bars = _load_bars(c, row["symbol"], row["timeframe"])
            result = vault.reassess(c, sid, bars, m1_bars, CostModel.for_symbol(row["symbol"]))
            if result is None:
                raise HTTPException(status_code=404, detail="not found")
            return result
        finally:
            c.close()

    # ------------------------------------------------------------------ portfolios
    def _portfolio_detail(c: Any, pid: str) -> dict[str, Any] | None:
        row = db.fetchone(c, "SELECT * FROM portfolios WHERE id = ?", (pid,))
        if row is None:
            return None
        members = db.fetchall(c, "SELECT pm.*, s.symbol, s.equity_json FROM portfolio_members pm "
                                 "JOIN strategies s ON s.id = pm.strategy_id WHERE pm.portfolio_id = ? "
                                 "ORDER BY pm.rowid", (pid,))
        ms = []
        for m in members:
            curve = _json(m["equity_json"], []) or []
            pairs = [(int(e["ts"]), float(e["equity"])) for e in curve if isinstance(e, dict) and "ts" in e]
            ms.append(pf.Member(strategy_id=m["strategy_id"], symbol=m["symbol"], curve=pairs,
                                bot_id=m["deployed_bot_id"]))
        sizing = pf.size_portfolio(ms, float(row["target_heat_pct"]), bool(row["symbol_lock"]),
                                   pf.canonical_mode(row["sizing_mode"]))
        out = sizing.to_dict()
        out.update({"portfolio_id": row["id"], "name": row["name"],
                    "target_heat_pct": float(row["target_heat_pct"]),
                    "symbol_lock": bool(row["symbol_lock"]), "sizing_mode": pf.canonical_mode(row["sizing_mode"])})
        return out

    @app.post(BASE + "/portfolios")
    def portfolio_create(body: PortfolioCreate, _=Depends(dashboard)):
        c = conn()
        try:
            members: list[pf.Member] = []
            for sid in body.strategy_ids:
                row = db.fetchone(c, "SELECT symbol,equity_json FROM strategies WHERE id = ?", (sid,))
                if row is None:
                    raise HTTPException(status_code=404, detail="not found")
                curve = _json(row["equity_json"], []) or []
                pairs = [(int(e["ts"]), float(e["equity"])) for e in curve if isinstance(e, dict) and "ts" in e]
                members.append(pf.Member(sid, row["symbol"], pairs))
            sizing = pf.size_portfolio(members, body.target_heat_pct, body.symbol_lock, body.sizing_mode)
            pid = uuid.uuid4().hex[:12]
            db.insert(c, "portfolios", id=pid, name=body.name, target_heat_pct=body.target_heat_pct,
                      symbol_lock=int(bool(body.symbol_lock)), sizing_mode=sizing.sizing_mode, created_at=db.utcnow_iso())
            for m in sizing.members:
                db.insert(c, "portfolio_members", portfolio_id=pid, strategy_id=m["strategy_id"],
                          risk_pct=m["risk_pct"], scale=m["scale"], avg_corr=m["avg_corr"], deployed_bot_id=None)
            out = sizing.to_dict()
            out.update({"portfolio_id": pid, "name": body.name, "target_heat_pct": body.target_heat_pct,
                        "symbol_lock": bool(body.symbol_lock)})
            return out
        finally:
            c.close()

    @app.get(BASE + "/portfolios")
    def portfolio_list(_=Depends(dashboard)):
        c = conn()
        try:
            rows = db.fetchall(c, "SELECT id FROM portfolios ORDER BY created_at DESC, rowid DESC")
            return [d for r in rows if (d := _portfolio_detail(c, r["id"])) is not None]
        finally:
            c.close()

    @app.get(BASE + "/portfolios/{pid}")
    def portfolio_get(pid: str, _=Depends(dashboard)):
        c = conn()
        try:
            out = _portfolio_detail(c, pid)
            if out is None:
                raise HTTPException(status_code=404, detail="not found")
            return out
        finally:
            c.close()

    @app.post(BASE + "/portfolios/{pid}/deploy")
    def portfolio_deploy(pid: str, body: PortfolioDeploy, _=Depends(dashboard)):
        c = conn()
        try:
            detail = _portfolio_detail(c, pid)
            if detail is None:
                raise HTTPException(status_code=404, detail="not found")
            max_magic = int(db.scalar(c, "SELECT MAX(magic) FROM bots") or 900000)
            out = []
            for member in detail["members"]:
                if member.get("bot_id"):
                    continue
                sid = member["strategy_id"]
                strat = _strategy_or_404(c, sid)
                bid = uuid.uuid4().hex[:12]
                max_magic += 1
                target = float(body.target_risk_pct_per_bot or member["risk_pct"])
                db.insert(c, "bots", id=bid, strategy_id=sid, portfolio_id=pid, symbol=strat["symbol"],
                          magic=max_magic, target_risk_pct=target,
                          incubation=int(bool(body.incubation)), deployed_at=db.utcnow_iso())
                state = inc.initial_state(bid, incubation=body.incubation)
                db.insert(c, "incubation_states", **state.to_row())
                db.update(c, "portfolio_members", {"portfolio_id": pid, "strategy_id": sid},
                          {"deployed_bot_id": bid})
                out.append({
                    "bot_id": bid, "magic": max_magic, "strategy_id": sid,
                    "target_risk_pct": target, "multiplier": state.multiplier,
                    "effective_risk_pct": round(target * state.multiplier, 6),
                    "pilot_token_url": f"{settings.public_url}{BASE}/incubation/{bid}",
                })
            return {"bots": out}
        finally:
            c.close()

    # ------------------------------------------------------------------ pilot tokens
    @app.post(BASE + "/pilot/token")
    def pilot_token(body: PilotTokenRequest, _=Depends(dashboard)):
        return {"pilot_token": auth.issue_pilot(body.pilot_id, settings.jwt_secret)}

    @app.post(BASE + "/bots/{bot_id}/token")
    def bot_token(bot_id: str, _=Depends(dashboard)):
        c = conn()
        try:
            if _bot_row(c, bot_id) is None:
                raise HTTPException(status_code=404, detail="not found")
        finally:
            c.close()
        return {"bot_token": auth.issue_bot(bot_id, settings.jwt_secret)}

    # ------------------------------------------------------------------ incubation
    @app.get(BASE + "/incubation")
    def incubation_list(_=Depends(dashboard)):
        c = conn()
        try:
            rows = db.fetchall(c, "SELECT * FROM bots ORDER BY deployed_at DESC, rowid DESC")
            return [_view(c, _bot(r)) for r in rows]
        finally:
            c.close()

    @app.get(BASE + "/incubation/{bot_id}")
    def incubation_get(bot_id: str, _=Depends(bot_or_dashboard)):
        c = conn()
        try:
            row = _bot_row(c, bot_id)
            if row is None:
                raise HTTPException(status_code=404, detail="not found")
            return _view(c, row)
        finally:
            c.close()

    @app.post(BASE + "/incubation/{bot_id}/graduate")
    def incubation_graduate(bot_id: str, _=Depends(dashboard)):
        c = conn()
        try:
            row = _bot_row(c, bot_id)
            if row is None:
                raise HTTPException(status_code=404, detail="not found")
            state = _state(c, bot_id)
            ctx = _ctx(c, row, state)
            ev = inc.graduate(state, ctx)
            _save(c, ev.state)
            _publish_transitions(ev.transitions)
            return _view(c, row, ev.state)
        finally:
            c.close()

    @app.post(BASE + "/incubation/{bot_id}/rung")
    def incubation_rung(bot_id: str, body: RungRequest, _=Depends(dashboard)):
        c = conn()
        try:
            row = _bot_row(c, bot_id)
            if row is None:
                raise HTTPException(status_code=404, detail="not found")
            state, tr = inc.apply_rung(_state(c, bot_id), body.rung, body.reason)
            _save(c, state)
            _publish_transitions([tr])
            return _view(c, row, state)
        finally:
            c.close()

    @app.post(BASE + "/incubation/{bot_id}/auto")
    def incubation_auto(bot_id: str, body: AutoRequest, _=Depends(dashboard)):
        c = conn()
        try:
            row = _bot_row(c, bot_id)
            if row is None:
                raise HTTPException(status_code=404, detail="not found")
            state = _state(c, bot_id)
            ev = inc.apply_auto(state, body.auto, _ctx(c, row, state))
            _save(c, ev.state)
            _publish_transitions(ev.transitions)
            return _view(c, row, ev.state)
        finally:
            c.close()

    @app.post(BASE + "/incubation/{bot_id}/pause")
    def incubation_pause(bot_id: str, body: PauseRequest, _=Depends(dashboard)):
        c = conn()
        try:
            row = _bot_row(c, bot_id)
            if row is None:
                raise HTTPException(status_code=404, detail="not found")
            state = inc.apply_pause(_state(c, bot_id), body.paused)
            _save(c, state)
            return _view(c, row, state)
        finally:
            c.close()

    @app.post(BASE + "/incubation/pause-all")
    def incubation_pause_all(body: PauseAllRequest, _=Depends(dashboard)):
        c = conn()
        try:
            rows = db.fetchall(c, "SELECT id FROM bots")
            for r in rows:
                _save(c, inc.apply_pause(_state(c, r["id"]), body.paused))
            return {"paused": bool(body.paused), "reason": body.reason or ""}
        finally:
            c.close()

    # ------------------------------------------------------------------ pilot ingest
    def _r_multiple(trade: Any, symbol: str) -> float:
        sl = abs(float(trade.open_price) - float(trade.sl))
        if sl <= 0 or float(trade.lots) <= 0:
            return 0.0
        cost = CostModel.for_symbol(symbol)
        risk_money = sl * float(trade.lots) * cost.money_per_unit
        return float(trade.profit) / risk_money if risk_money > 0 else 0.0

    @app.post(BASE + "/pilot/ingest", status_code=202)
    def pilot_ingest(body: dict[str, Any], _=Depends(pilot)):
        # Validate manually AFTER the scope check: a dashboard token must get 403, not a body 422.
        try:
            env = PilotEnvelope.model_validate(body)
        except ValidationError:
            raise HTTPException(status_code=422, detail="validation error")
        c = conn()
        try:
            login = int(env.account.login)
            received = db.utcnow_iso()
            if env.type in ("heartbeat", "attach"):
                chart = env.chart
                db.upsert(c, "pilot_heartbeats",
                          pilot_id=env.pilot_id, sent_at=env.sent_at, account_login=login,
                          chart_symbol=(chart.symbol if chart else None),
                          chart_period=(chart.period_minutes if chart else None),
                          terminal_json=json.dumps({
                              "terminal": env.terminal.model_dump() if env.terminal else None,
                              "account": env.account.model_dump(),
                              "chart": chart.model_dump() if chart else None,
                          }, separators=(",", ":")),
                          bots_json=json.dumps([b.model_dump() for b in (env.bots or [])], separators=(",", ":")),
                          received_at=received)
                bus.publish("pilot.heartbeat", {"pilot_id": env.pilot_id, "online": True,
                                                "chart": chart.model_dump() if chart else None,
                                                "bots_n": len(env.bots or [])})
            else:
                # Any valid message refreshes "last seen" without clobbering chart/bots data.
                c.execute("UPDATE pilot_heartbeats SET received_at = ? WHERE pilot_id = ?", (received, env.pilot_id))
            if env.note:
                bus.publish("pilot.status", {"pilot_id": env.pilot_id, "note": env.note})

            if env.type == "trade" and env.trade is not None:
                t = env.trade
                if db.fetchone(c, "SELECT 1 FROM pilot_trades WHERE account_login = ? AND ticket = ?",
                               (login, t.ticket)) is not None:
                    return JSONResponse({"duplicate": True}, status_code=200)
                bot_row = _bot(db.fetchone(c, "SELECT * FROM bots WHERE magic = ?", (int(t.magic),))) if str(t.magic).isdigit() else None
                bot_id = bot_row["bot_id"] if bot_row else None
                r = _r_multiple(t, t.symbol or (bot_row["symbol"] if bot_row else "EURUSD"))
                healthy = 0
                if bot_id:
                    state = _state(c, bot_id)
                    strat = db.fetchone(c, "SELECT metrics_json FROM strategies WHERE id = ?", (bot_row["strategy_id"],))
                    metrics = _json(strat["metrics_json"] if strat else None, {}) or {}
                    oos = metrics.get("oos") or {}
                    bt_mean = float(oos.get("expectancy_r") or 0.5)
                    if bt_mean <= 0:
                        bt_mean = 0.5
                    before = state.healthy_live_trades
                    inc.update_counters(state, r, bt_mean)
                    healthy = int(state.healthy_live_trades > before)
                    ev = inc.evaluate(state, _ctx(c, _rowdict(bot_row), state, "ONLINE"))
                    _save(c, ev.state)
                    _publish_transitions(ev.transitions)
                db.insert(c, "pilot_trades", account_login=login, ticket=int(t.ticket),
                          position_id=t.position_id, bot_id=bot_id, symbol=t.symbol, direction=t.direction,
                          lots=t.lots, open_time=t.open_time, close_time=t.close_time,
                          open_price=t.open_price, close_price=t.close_price, profit=t.profit,
                          commission=t.commission, swap=t.swap, sl=t.sl, tp=t.tp, reason=t.reason,
                          r_multiple=r, healthy=healthy, ingested_at=received)
                bus.publish("pilot.trade", {"account_login": login, "ticket": int(t.ticket), "bot_id": bot_id,
                                            "symbol": t.symbol, "profit": t.profit, "r_multiple": r,
                                            "close_time": t.close_time})
            return JSONResponse({"accepted": 1, "pilot_online": True}, status_code=202)
        finally:
            c.close()

    @app.get(BASE + "/pilot/status")
    def pilot_status(_=Depends(dashboard)):
        c = conn()
        try:
            rows = _hb_rows(c, 1)
            hb = rows[0] if rows else None
            online = _pilot_online(c)
            chart = None
            account = None
            if hb:
                info = _json(hb.get("terminal_json"), {}) or {}
                chart = dict(info.get("chart") or {})
                if hb.get("chart_symbol") and "symbol" not in chart:
                    chart.update({"symbol": hb["chart_symbol"], "period_minutes": hb.get("chart_period")})
                account = dict(info.get("account") or {})
                if "login" not in account:
                    account["login"] = hb.get("account_login")
            magics = _hb_bot_magics(hb) if online else set()
            bots_out: list[dict[str, Any]] = []
            for b in db.fetchall(c, "SELECT * FROM bots"):
                if str(b["magic"]) not in magics:
                    continue
                pstate = _pilot_state(c, _bot(b))
                bots_out.append({"bot_id": b["id"], "state": pstate, "magic": int(b["magic"])})
            silent = []
            if online:
                for b in db.fetchall(c, "SELECT id,magic FROM bots"):
                    if str(b["magic"]) not in magics and _pilot_state(c, _bot(b)) == "EA_SILENT":
                        silent.append(b["id"])
            return {"online": online,
                    "last_heartbeat_at": hb.get("received_at") if hb else None,
                    "chart": chart, "account": account, "bots": bots_out, "silent_bots": silent}
        finally:
            c.close()

    # ------------------------------------------------------------------ alerts
    @app.get(BASE + "/alerts")
    def alerts(active: int | None = None, _=Depends(dashboard)):
        c = conn()
        try:
            sql = "SELECT id,bot_id,strategy_id,kind,severity,message,value,threshold,created_at,resolved_at FROM decay_alerts"
            if active:
                sql += " WHERE resolved_at IS NULL"
            sql += " ORDER BY created_at DESC, id DESC"
            return [_rowdict(r) for r in db.fetchall(c, sql)]
        finally:
            c.close()

    # ------------------------------------------------------------------ WebSocket
    # SPEC contract path is /ws/live; the versioned path is kept for API clients.
    @app.websocket(BASE + "/ws/live")
    @app.websocket("/ws/live")
    async def ws_live(websocket: WebSocket):
        token = websocket.query_params.get("token", "")
        try:
            payload = auth.decode_token(token, settings.jwt_secret)
            if not auth.grants(payload, "dashboard"):
                raise auth.AuthError("scope")
        except (auth.AuthError, jwt.PyJWTError):
            await websocket.close(code=4401)
            return
        await websocket.accept()
        topics: list[str] = ["*"]
        queue = bus.subscribe(topics)
        try:
            try:
                msg = await websocket.receive_json()
                if isinstance(msg, dict) and msg.get("type") == "subscribe" and isinstance(msg.get("topics"), list):
                    chosen = [str(t) for t in msg["topics"]] or ["*"]
                    bus.unsubscribe(topics, queue)
                    topics = chosen
                    queue = bus.subscribe(topics)
            except (WebSocketDisconnect, RuntimeError, ValueError):
                pass
            while True:
                message = await queue.get()
                await websocket.send_text(events.dumps(message))
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            bus.unsubscribe(topics, queue)

    return app


app = create_app()
