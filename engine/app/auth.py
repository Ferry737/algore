"""Bearer JWT auth (HS256, PyJWT). CLEAN-ROOM DESIGN (SPEC §2.8).

Scopes: `dashboard` (everything), `pilot` (POST /pilot/ingest only), `bot:<bot_id>` (GET /incubation/{bot_id} only).
Algorithm `none` is rejected explicitly; the dashboard API key is compared in constant time.
"""
from __future__ import annotations

import hmac
import time
from typing import Any

import jwt

ALGORITHM = "HS256"
DASHBOARD_TTL_S = 3600
PILOT_TTL_S = 365 * 24 * 3600
SCOPE_DASHBOARD = "dashboard"
SCOPE_PILOT = "pilot"


class AuthError(Exception):
    """Invalid or missing token."""


def bot_scope(bot_id: str) -> str:
    return f"bot:{bot_id}"


def issue_token(subject: str, scope: str, secret: str, ttl_s: int) -> str:
    now = int(time.time())
    return jwt.encode({"sub": subject, "scope": scope, "iat": now, "exp": now + int(ttl_s)}, secret, algorithm=ALGORITHM)


def api_key_ok(candidate: str, expected: str) -> bool:
    return hmac.compare_digest(str(candidate or "").encode("utf-8"), str(expected or "").encode("utf-8"))


def issue_dashboard(api_key: str, secret: str, expected_key: str) -> str | None:
    if not api_key_ok(api_key, expected_key):
        return None
    return issue_token("dashboard", SCOPE_DASHBOARD, secret, DASHBOARD_TTL_S)


def issue_pilot(pilot_id: str, secret: str) -> str:
    return issue_token(pilot_id, SCOPE_PILOT, secret, PILOT_TTL_S)


def issue_bot(bot_id: str, secret: str) -> str:
    return issue_token(bot_id, bot_scope(bot_id), secret, PILOT_TTL_S)


def decode_token(token: str, secret: str) -> dict[str, Any]:
    """Verify signature, algorithm and expiry. Raises AuthError on any problem."""
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") != ALGORITHM:
            raise AuthError("algorithm not allowed")
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM], options={"require": ["exp", "sub", "scope"]})
        if not isinstance(payload.get("scope"), str):
            raise AuthError("scope missing")
        return payload
    except jwt.PyJWTError as exc:
        raise AuthError(str(exc)) from exc


def grants(payload: dict[str, Any], needed: str) -> bool:
    """dashboard grants everything; otherwise the scope must match exactly."""
    scope = payload.get("scope")
    return scope == SCOPE_DASHBOARD or scope == needed


__all__ = ["ALGORITHM", "AuthError", "bot_scope", "issue_token", "issue_dashboard", "issue_pilot", "issue_bot",
           "decode_token", "grants", "api_key_ok"]
