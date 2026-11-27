#!/usr/bin/env bash
# Start the AlgoRE engine on 127.0.0.1:8000 behind the existing Cloudflare tunnel.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p data
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created deploy/.env — set ALGORE_JWT_SECRET and ALGORE_DASHBOARD_API_KEY before restarting." >&2
fi
docker compose up -d --build
docker compose ps
