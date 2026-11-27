# AlgoRE on Windows 11

Native Windows 11 support for the engine, dashboard and MT5 telemetry bridge. Nothing here needs WSL, Docker or a Unix shell.

## Requirements

- Windows 11 (64-bit)
- Python 3.11 or newer — install from python.org and tick **Add Python to PATH**
- Node.js 20 or newer with npm
- MetaTrader 5 only if you want live telemetry

## Fastest start

1. Open PowerShell in this folder.
2. Run:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\setup.ps1
   ```

   This creates `engine\.venv`, installs Python and npm dependencies, and generates a private `.env` with fresh random keys. It never prints the keys. The file is restricted to your Windows account.

3. Double-click **`start.bat`** and choose:

   - `1` — run setup again
   - `2` — start the API (port 8000)
   - `3` — start the dashboard (port 3000)
   - `4` — stop both
   - `5` — open this guide

   Or start them in two separate PowerShell windows:

   ```powershell
   .\start-api.ps1
   .\start-dashboard.ps1
   ```

4. Open **http://localhost:3000**. The dashboard starts in Demo Mode if no API is reachable; with the API running it uses `http://localhost:8000` automatically. Connection → **Demo mode** switches offline at any time.

## What the scripts do

| Script | Purpose |
| --- | --- |
| `setup.ps1` | Creates the Python venv, installs dependencies, generates `.env` with random keys |
| `start-api.ps1` | Starts Uvicorn with one worker on `127.0.0.1:8000`, restarts it if it exits |
| `start-dashboard.ps1` | Starts `npm run dev` on port 3000 (or `-Build` for a production build) |
| `stop.ps1` | Stops the API and dashboard PIDs recorded under `windows\run\` |
| `start.ps1` | Small interactive menu that wraps the above |
| `start.bat` | Double-click launcher for the menu |

## Docker Desktop alternative

If you prefer containers, install Docker Desktop with the **WSL 2** backend, then from the repository root:

```powershell
cd deploy
copy .env.example .env
# edit .env with your own random keys
docker compose up -d --build
```

The dashboard still runs with `npm run dev` on the host.

## Exposing it over HTTPS

Localhost is enough for development. For an iPhone or an MT5 terminal on another machine, expose the API with an HTTPS tunnel, then put that URL in the dashboard's **Connection** drawer. A Cloudflare Tunnel is one option; install `cloudflared` from its official release page and run it against `http://127.0.0.1:8000`.

This repository deliberately contains **no live tunnel URL**. Add your own domain to your Cloudflare account if you want a permanent hostname.

## MT5

See [MT5-SETUP.md](MT5-SETUP.md). Compile the `.mq5` files in MetaEditor — they are provided as source and are not precompiled.

## Troubleshooting

- **"running scripts is disabled"** — use `powershell -ExecutionPolicy Bypass -File .\setup.ps1`, or change the policy for the current user only.
- **Python not found** — reinstall Python with **Add Python to PATH**, then reopen PowerShell.
- **Port 8000 already in use** — run `.\stop.ps1`, or pass another port: `.\start-api.ps1 -Port 8010` and set the matching API URL in the dashboard.
- **Dashboard shows DEMO** — tap **Connection** and confirm the API URL points at the running engine.
- **401 from the API** — paste the `ALGORE_DASHBOARD_API_KEY` value from `.env` into the Connection drawer's Dashboard key field.

## Research notice

This is research infrastructure, not financial advice. Validate strategies out of sample, model all costs, and test on a demo account before using real capital.
