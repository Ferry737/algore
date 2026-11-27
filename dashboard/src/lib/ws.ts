import type { WsEvent, WsEventName } from "./types";
import { WS_EVENT_NAMES } from "./types";

export type SocketStatus = "idle" | "connecting" | "open" | "closed";

interface LiveSocketOptions {
  url: string;
  getToken: () => Promise<string>;
  onEvent: (event: WsEvent) => void;
  onStatus?: (status: SocketStatus) => void;
  topics?: string[];
}

function isWsEvent(value: unknown): value is WsEvent {
  if (!value || typeof value !== "object") {
    return false;
  }
  const type = (value as { type?: unknown }).type;
  return (
    typeof type === "string" &&
    (WS_EVENT_NAMES as readonly string[]).includes(type as WsEventName)
  );
}

export function openLiveSocket(options: LiveSocketOptions): () => void {
  if (typeof window === "undefined" || !options.url) {
    return () => undefined;
  }

  let socket: WebSocket | null = null;
  let stopped = false;
  let attempts = 0;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  const setStatus = (status: SocketStatus) => options.onStatus?.(status);

  const scheduleReconnect = () => {
    if (stopped) {
      return;
    }
    attempts += 1;
    const delay = Math.min(12_000, 800 * 2 ** Math.min(attempts, 4));
    setStatus("closed");
    reconnectTimer = setTimeout(() => {
      void connect();
    }, delay);
  };

  const connect = async () => {
    if (stopped) {
      return;
    }
    setStatus("connecting");
    let token: string;
    try {
      token = await options.getToken();
    } catch {
      scheduleReconnect();
      return;
    }
    if (stopped) {
      return;
    }

    const topics = options.topics ?? [
      "campaign.*",
      "incubation.*",
      "pilot.*",
      "alerts",
    ];
    const separator = options.url.includes("?") ? "&" : "?";
    const ws = new WebSocket(
      `${options.url}${separator}token=${encodeURIComponent(token)}`,
    );
    socket = ws;

    ws.onopen = () => {
      attempts = 0;
      setStatus("open");
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "subscribe", topics }));
      }
    };

    ws.onmessage = (message) => {
      if (typeof message.data !== "string") {
        return;
      }
      try {
        const parsed: unknown = JSON.parse(message.data);
        if (isWsEvent(parsed)) {
          options.onEvent(parsed);
        }
      } catch {
        // Ignore malformed frames; the next event will re-sync the view.
      }
    };

    ws.onerror = () => {
      // onclose owns the reconnect path.
    };

    ws.onclose = () => {
      if (stopped) {
        return;
      }
      scheduleReconnect();
    };
  };

  void connect();

  return () => {
    stopped = true;
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
    }
    if (socket) {
      socket.onclose = null;
      socket.close(1000, "client shutdown");
    }
    setStatus("idle");
  };
}
