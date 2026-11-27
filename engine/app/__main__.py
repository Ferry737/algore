"""uvicorn entry point: cd engine && .venv/bin/python -m app"""
from __future__ import annotations

import uvicorn

from .api import create_app
from .config import Settings


def main() -> None:
    settings = Settings.from_env()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port,
                workers=1, log_level="info")


if __name__ == "__main__":
    main()
