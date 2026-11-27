"""Test-only compatibility shim (loaded before engine/tests/conftest.py).

The installed httpx `Client.get()` does not accept a `json=` keyword, while the HTTP
contract tests call `client.get(..., json=None)`. Accept that no-op keyword so the endpoint
contract can be tested unchanged; a non-None JSON body is forwarded through request().
"""
from __future__ import annotations

try:  # pragma: no cover - compatibility only
    import httpx

    _orig_get = httpx.Client.get

    def _get(self, url, **kwargs):  # type: ignore[no-untyped-def]
        payload = kwargs.pop("json", None)
        if payload is None:
            return _orig_get(self, url, **kwargs)
        return self.request("GET", url, json=payload, **kwargs)

    httpx.Client.get = _get
except Exception:  # noqa: BLE001
    pass
