# MetaTrader 5 telemetry bridge on Windows 11

The MQL5 files are source code. They must be compiled in MetaEditor before MT5 can use them.

## Files

- `engine/mql5/PilotBridge.mq5` — sends heartbeats and fills to the engine.
- `engine/mql5/EA_EXAMPLE.mq5` — minimal Expert Advisor showing how to include the bridge.

## Steps

1. Open MetaTrader 5 and choose **File → Open Data Folder**.
2. Copy both `.mq5` files into `MQL5/Experts`.
3. Open **MetaEditor** (F4 in MT5), then compile each file (F7). Fix any compiler messages before continuing.
4. In the MT5 terminal, open **Tools → Options → Expert Advisors** and enable **Allow WebRequest for listed URLs**. Add your API host (for local testing: `http://127.0.0.1:8000`).
5. Start the engine with `windows/start-api.ps1`.
6. Ask the engine for a pilot token through `/api/v1/pilot/token`, then paste it into the EA's `PilotToken` input.
7. Attach the EA to a chart on a **demo account** first. Watch the AlgoRE dashboard's Connection → Pilot status for heartbeats.

## Safety

- Never put your main account password or a withdrawal-enabled credential into the EA.
- Use a small demo account or a dedicated trade-only environment while testing.
- Heartbeats and fills contain account, chart and trade data. Only point the bridge at an API you control.
- A green compile is not a green strategy: verify out-of-sample behaviour and full transaction costs before considering real capital.

## Troubleshooting

- **WebRequest error 406** — the API host is missing from the allowed URL list in MT5.
- **No heartbeats** — check the pilot token, the EA's `Enabled` input, and that the engine is listening on the URL you configured.
- **401 from the engine** — the pilot token is wrong or expired; issue a new one.
