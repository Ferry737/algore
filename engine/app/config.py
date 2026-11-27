"""Env-driven settings for the AlgoRE engine. CLEAN-ROOM DESIGN (SPEC §9)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB = ENGINE_DIR / "data" / "algore.db"


def _int(env, key: str, default: int) -> int:
    try:
        return int(env.get(key, "") or default)
    except ValueError:
        return default


def _float(env, key: str, default: float) -> float:
    try:
        return float(env.get(key, "") or default)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """All runtime tunables. Tests override via env vars or by constructing Settings directly."""

    jwt_secret: str = "algore-dev-secret-change-me"
    dashboard_api_key: str = "algore-dev-api-key"
    db_path: str = str(DEFAULT_DB)
    cors_origins: tuple[str, ...] = ("http://localhost:3000",)
    host: str = "127.0.0.1"
    port: int = 8000
    rate_limit_per_min: int = 120
    ingest_rate_limit_per_min: int = 600
    # incubation tunables (SPEC §2.5; numbers ours unless a claim id is given)
    hot_trades: int = 5
    hot_wins: int = 4
    silence_days: int = 30
    silence_ratio: float = 0.25
    pilot_offline_s: int = 90
    ea_silent_s: int = 300
    breed_workers: int = 2
    public_url: str = "http://127.0.0.1:8000"
    version: str = "1.0.0"

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Settings":
        env = dict(os.environ if env is None else env)
        cors_env = env.get("ALGORE_CORS_ORIGINS") or env.get("ALLOWED_ORIGINS") or "http://localhost:3000"
        cors = tuple(o.strip() for o in cors_env.split(",") if o.strip())
        return cls(
            jwt_secret=env.get("ALGORE_JWT_SECRET") or "algore-dev-secret-change-me",
            dashboard_api_key=env.get("ALGORE_DASHBOARD_API_KEY") or "algore-dev-api-key",
            db_path=env.get("ALGORE_DB_PATH") or str(DEFAULT_DB),
            cors_origins=cors,
            host=env.get("ALGORE_HOST", "127.0.0.1"),
            port=_int(env, "ALGORE_PORT", 8000),
            rate_limit_per_min=_int(env, "ALGORE_RATE_LIMIT_PER_MIN", 120),
            ingest_rate_limit_per_min=_int(env, "ALGORE_INGEST_RATE_LIMIT_PER_MIN", 600),
            hot_trades=_int(env, "ALGORE_HOT_TRADES", 5),
            hot_wins=_int(env, "ALGORE_HOT_WINS", 4),
            silence_days=_int(env, "ALGORE_SILENCE_DAYS", 30),
            silence_ratio=_float(env, "ALGORE_SILENCE_RATIO", 0.25),
            pilot_offline_s=_int(env, "ALGORE_PILOT_OFFLINE_S", 90),
            ea_silent_s=_int(env, "ALGORE_EA_SILENT_S", 300),
            breed_workers=max(1, min(2, _int(env, "ALGORE_BREED_WORKERS", 2))),
            public_url=env.get("ALGORE_PUBLIC_URL", "http://127.0.0.1:8000"),
        )


_CACHE: Settings | None = None


def get_settings() -> Settings:
    """Process-wide settings built once from the environment."""
    global _CACHE
    if _CACHE is None:
        _CACHE = Settings.from_env()
    return _CACHE


def reset_settings() -> None:
    """Drop the cached settings (used by tests that change env vars)."""
    global _CACHE
    _CACHE = None
