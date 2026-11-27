<div align="center">

<img src="docs/assets/hero-banner.svg" alt="AlgoRE — clean-room quant breeder, incubation ladder and MT5 telemetry" width="100%">

[![License: MIT](https://img.shields.io/badge/license-MIT-10B981?style=flat-square)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?style=flat-square)](engine/requirements.txt)
[![Next.js 14+](https://img.shields.io/badge/Next.js-14%2B-000000?style=flat-square)](dashboard/package.json)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square)](engine/app/api.py)
[![MQL5](https://img.shields.io/badge/MQL5-MetaTrader%205-F59E0B?style=flat-square)](engine/mql5)
[![Tests](https://img.shields.io/badge/tests-44%2F44%20passing-10B981?style=flat-square)](engine/tests)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-3B82F6?style=flat-square)](CONTRIBUTING.md)

**Independent, clean-room research infrastructure for quantitative strategy breeding, staged incubation, and MetaTrader 5 telemetry.**

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https://github.com/Ferry737/algore&root-directory=dashboard)

</div>

## See the interface

<p align="center">
  <img src="docs/assets/dashboard-overview.svg" alt="Command overview dashboard" width="49%">
  <img src="docs/assets/incubation-and-vault.svg" alt="Incubation ladder and vault score panel" width="49%">
</p>

The dashboard runs in **Demo Mode** without a backend. Open Connection → **Demo mode** to switch instantly; no key, no server, no network needed.

## Four pillars

1. **Genetic strategy breeder & OOS vault** — bounded genome grammar, population crossover and mutation, walk-forward train/test/OOS split, anti-overfit gates, and a searchable strategy passport.
2. **Parity backtester + `.mq5` exporter** — event-driven bar simulation with spread, commission and slippage, plus generation of compilable MQL5 Expert Advisor source from a strategy genome.
3. **Dual-path incubation ladder** — `INCUBATION 25% → PROVING 50% → FULL 100%`, with a live-trade path and a post-training replay fast-track. Ladder changes alter sizing for *subsequent* entries only; open positions are never mutated.
4. **Mobile-first animated PWA** — Next.js App Router, TypeScript, framer-motion, iPhone-safe layout, runtime endpoint/key settings in localStorage, and standard WebSocket live updates.

## Architecture

```mermaid
flowchart LR
    B[Genetic Breeder] --> V[OOS Vault]
    V --> P[Portfolio Sizer]
    P --> I[Incubation Ladder]
    I <--> M[PilotBridge.mq5 in MT5]
    M -->|heartbeat + fills| A[FastAPI / Pilot Ingest]
    A --> W[REST + WS /ws/live]
    W --> D[Next.js PWA]
    A --> DB[(SQLite WAL)]
```

## Quickstart

### 1. Engine

Docker Compose:

```bash
cd deploy
cp .env.example .env
# edit .env: set ALGORE_JWT_SECRET and ALGORE_DASHBOARD_API_KEY
docker compose up -d --build
curl http://127.0.0.1:8000/api/v1/health
```

Or a local Python virtual environment:

```bash
cd engine
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export ALGORE_JWT_SECRET=$(openssl rand -hex 32)
export ALGORE_DASHBOARD_API_KEY=$(openssl rand -hex 32)
uvicorn app.api:app --host 127.0.0.1 --port 8000 --workers 1
```

Engine tests:

```bash
cd engine && pytest -v
```

### 2. Dashboard

```bash
cd dashboard
npm install
npm run dev
```

Open `http://localhost:3000`. The baked API default is `http://localhost:8000`; with no backend, tap **Connection → Demo mode** for a fully offline simulated feed.

Production build:

```bash
NODE_OPTIONS="--max-old-space-size=2048" npm run lint && npm run build
```

### 3. MT5 telemetry bridge

1. Copy `engine/mql5/PilotBridge.mq5` and `engine/mql5/EA_EXAMPLE.mq5` into your MetaTrader 5 `MQL5/Experts` folder.
2. In MetaEditor, compile both files. The source is provided but **not compiled here**.
3. Generate a pilot token through `/api/v1/pilot/token`, paste it into the EA inputs, and allow `WebRequest` for your API host in MT5 terminal settings.
4. Start on a **demo account** first. Heartbeats and fills land at `/api/v1/pilot/ingest` and drive the incubation ladder.

## Honest methodology & risk disclaimer

This is **research and infrastructure software, not financial advice**. It does not predict markets and does not guarantee returns. The breeder, scoring weights and incubation ladder are clean-room designs; where a published detail was not publicly verifiable it is labelled `inferred` in the UI and documentation rather than guessed.

Before risking capital: independently verify every strategy out of sample, model **all** transaction costs (spread, commission, slippage, funding, gas where relevant), check maximum drawdown and sample size, and validate the whole stack on a demo account. Treat every backtest as overfit until proven otherwise. You are responsible for compliance with your broker, jurisdiction, and tax rules; ask a qualified professional where needed.

## Layout

```text
engine/     FastAPI service, breeder, backtester, incubator, sizer, MQL5 exporter, tests
dashboard/  Next.js App Router PWA with runtime connection settings
deploy/     Docker Compose, Dockerfile, run script, example environment
docs/       Visual assets
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Issues and pull requests are welcome.

## License

MIT © 2026 Ferry737. See [LICENSE](LICENSE).
