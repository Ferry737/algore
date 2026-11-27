"""Thread-safe event bus: persists every event to the `events` outbox and fans out to asyncio WebSocket subscribers.

CLEAN-ROOM DESIGN (SPEC §4 WebSocket). The asyncio loop is captured at startup (lifespan); publish() may be called
from any thread and uses asyncio.run_coroutine_threadsafe. When no loop is attached, publish only persists.
"""
from __future__ import annotations

import asyncio
import json
import threading
from typing import Any, Iterable

from . import db


def topic_matches(pattern: str, topic: str) -> bool:
    """'*' matches everything, 'campaign.*' matches any campaign topic, otherwise exact."""
    if pattern == "*" or pattern == topic:
        return True
    return pattern.endswith(".*") and topic.startswith(pattern[:-1])


class EventBus:
    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subs: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}
        self._lock = threading.Lock()

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def detach_loop(self) -> None:
        self._loop = None

    def publish(self, topic: str, payload: dict[str, Any], persist: bool = True) -> dict[str, Any]:
        message = {"type": topic, "ts": db.utcnow_iso(), "data": payload}
        if persist:
            conn = None
            try:
                conn = db.connect(self._db_path)
                db.insert_event(conn, topic, payload)
            except Exception:  # noqa: BLE001 — telemetry must never break the caller
                pass
            finally:
                if conn is not None:
                    conn.close()
        with self._lock:
            queues = {q for pat, qs in self._subs.items() if topic_matches(pat, topic) for q in qs}
        if queues and self._loop is not None:
            try:
                asyncio.run_coroutine_threadsafe(self._deliver(queues, message), self._loop)
            except RuntimeError:  # loop closed during shutdown
                pass
        return message

    async def _deliver(self, queues: Iterable[asyncio.Queue[dict[str, Any]]], message: dict[str, Any]) -> None:
        for q in queues:
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                pass

    def subscribe(self, topics: Iterable[str]) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1000)
        with self._lock:
            for t in topics:
                self._subs.setdefault(t, set()).add(queue)
        return queue

    def unsubscribe(self, topics: Iterable[str], queue: asyncio.Queue[dict[str, Any]]) -> None:
        with self._lock:
            for t in topics:
                self._subs.get(t, set()).discard(queue)
                if t in self._subs and not self._subs[t]:
                    del self._subs[t]

    def subscriber_count(self) -> int:
        with self._lock:
            return len({q for qs in self._subs.values() for q in qs})


def dumps(message: dict[str, Any]) -> str:
    return json.dumps(message, separators=(",", ":"), default=str)
