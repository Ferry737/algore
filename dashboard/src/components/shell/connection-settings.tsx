"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { RotateCcw, Settings2, X } from "lucide-react";
import {
  deriveWsUrl,
  getConnectionSettings,
  resetConnectionSettings,
  saveConnectionSettings,
} from "@/lib/api";

export function ConnectionSettings() {
  const [open, setOpen] = useState(false);
  const [apiUrl, setApiUrl] = useState(() => getConnectionSettings().apiUrl);
  const [apiKey, setApiKey] = useState("");

  const openDrawer = () => {
    const current = getConnectionSettings();
    setApiUrl(current.apiUrl);
    // The key is never rendered back into an input; leave it blank on reopen.
    setApiKey("");
    setOpen(true);
  };

  const wsUrl = deriveWsUrl(apiUrl);

  const enableDemo = () => {
    saveConnectionSettings({ apiUrl: "", apiKey: "" });
    setApiUrl("");
    setApiKey("");
    setOpen(false);
  };

  return (
    <>
      <button
        type="button"
        onClick={openDrawer}
        aria-label="Connection settings"
        className="flex min-h-10 items-center gap-2 rounded-xl border border-line bg-panel px-3 text-[12px] font-medium text-muted transition hover:text-ink"
      >
        <Settings2 className="h-4 w-4" strokeWidth={1.8} />
        <span className="hidden sm:inline">Connection</span>
      </button>

      <AnimatePresence>
        {open ? (
          <motion.div
            className="fixed inset-0 z-[100] flex items-end justify-center bg-black/60 sm:items-center"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={(event) => {
              if (event.target === event.currentTarget) setOpen(false);
            }}
          >
            <motion.div
              role="dialog"
              aria-modal="true"
              aria-label="Connection settings"
              initial={{ y: 24, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: 16, opacity: 0 }}
              transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
              className="w-full max-w-lg rounded-t-2xl border border-line bg-canvas p-5 shadow-2xl sm:rounded-2xl sm:p-6"
              style={{ paddingBottom: "calc(20px + env(safe-area-inset-bottom, 0px))" }}
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h2 className="text-base font-semibold text-ink">Connection settings</h2>
                  <p className="mt-1 text-[12px] leading-5 text-subtle">
                    Saved on this device only. No redeploy needed.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  aria-label="Close connection settings"
                  className="rounded-lg p-2 text-subtle hover:bg-white/5 hover:text-ink"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <div className="mt-5 space-y-4">
                <label className="block">
                  <span className="text-[12px] font-medium text-muted">API URL</span>
                  <input
                    type="url"
                    inputMode="url"
                    autoCapitalize="none"
                    autoCorrect="off"
                    spellCheck={false}
                    value={apiUrl}
                    onChange={(event) => setApiUrl(event.target.value)}
                    placeholder="http://localhost:8000"
                    className="mt-2 w-full rounded-xl border border-line bg-panel px-3 py-3 font-mono text-[12px] text-ink outline-none placeholder:text-faint focus:border-emerald/50"
                  />
                </label>

                <label className="block">
                  <span className="text-[12px] font-medium text-muted">
                    Dashboard key
                  </span>
                  <input
                    type="password"
                    autoComplete="off"
                    value={apiKey}
                    onChange={(event) => setApiKey(event.target.value)}
                    placeholder="Paste key to connect; leave blank to keep the saved one"
                    className="mt-2 w-full rounded-xl border border-line bg-panel px-3 py-3 font-mono text-[12px] text-ink outline-none placeholder:text-faint focus:border-emerald/50"
                  />
                  <span className="mt-1.5 block text-[11px] leading-4 text-faint">
                    Masked here and in localStorage. Never baked into Vercel.
                  </span>
                </label>

                <div className="rounded-xl border border-line/70 bg-panel/60 px-3 py-2.5">
                  <p className="text-[11px] text-subtle">Live socket (auto-derived)</p>
                  <p className="mt-1 break-all font-mono text-[11px] text-ink">
                    {wsUrl || "wss://<host>/ws/live"}
                  </p>
                </div>
              </div>

              <div className="mt-6 flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    saveConnectionSettings({ apiUrl, apiKey });
                    setOpen(false);
                  }}
                  className="min-h-11 min-w-[180px] flex-1 rounded-xl bg-emerald px-4 text-[13px] font-semibold text-canvas transition hover:opacity-90"
                >
                  Save on this device
                </button>
                <button
                  type="button"
                  onClick={() => {
                    resetConnectionSettings();
                    setApiUrl("");
                    setApiKey("");
                    setOpen(false);
                  }}
                  aria-label="Reset to baked defaults"
                  title="Reset to baked defaults"
                  className="flex min-h-11 items-center gap-2 rounded-xl border border-line px-3 text-[12px] text-muted hover:text-ink"
                >
                  <RotateCcw className="h-4 w-4" />
                  Reset
                </button>
                <button
                  type="button"
                  onClick={enableDemo}
                  className="min-h-11 rounded-xl border border-line px-3 text-[12px] text-muted hover:text-ink"
                >
                  Demo mode
                </button>
              </div>
              <p className="mt-3 text-[11px] leading-4 text-faint">
                Uses standard WebSockets or polling — never SSE.
              </p>
            </motion.div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </>
  );
}
