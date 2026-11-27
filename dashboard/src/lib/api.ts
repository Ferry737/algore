import type {
  Alert,
  CampaignCreateInput,
  CampaignDetail,
  CampaignSummary,
  HealthResponse,
  IncubationBot,
  PilotStatus,
  PortfolioDetail,
  TokenResponse,
  VaultPassport,
  VaultStrategy,
} from "./types";

// Baked values are only INITIAL DEFAULTS. On the client, Connection Settings
// can override them from localStorage without a redeploy.
const DEFAULT_API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/+$/, "");
const DEFAULT_WS_URL = (process.env.NEXT_PUBLIC_WS_URL ?? "").replace(/\/+$/, "");
const DEFAULT_API_KEY = process.env.NEXT_PUBLIC_API_KEY ?? "";

const LS_API_URL = "algore.settings.apiUrl";
const LS_WS_URL = "algore.settings.wsUrl";
const LS_API_KEY = "algore.settings.apiKey";

function stored(key: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function getApiUrl(): string {
  return (stored(LS_API_URL) ?? DEFAULT_API_URL).replace(/\/+$/, "");
}

// Standard WebSockets only — Quick Tunnels do not support SSE.
export function deriveWsUrl(apiUrl: string): string {
  const base = apiUrl.replace(/\/+$/, "");
  if (base.startsWith("https://")) return `wss://${base.slice(8)}/ws/live`;
  if (base.startsWith("http://")) return `ws://${base.slice(7)}/ws/live`;
  return "";
}

export function getWsUrl(): string {
  const explicit = stored(LS_WS_URL);
  if (explicit) return explicit.replace(/\/+$/, "");
  return deriveWsUrl(getApiUrl());
}

export function getApiKey(): string {
  return stored(LS_API_KEY) ?? DEFAULT_API_KEY;
}

export interface ConnectionSettings {
  apiUrl: string;
  apiKey: string;
}

export function getConnectionSettings(): ConnectionSettings {
  return {
    apiUrl: stored(LS_API_URL) ?? DEFAULT_API_URL,
    apiKey: stored(LS_API_KEY) ?? DEFAULT_API_KEY,
  };
}

export function saveConnectionSettings(settings: ConnectionSettings): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(LS_API_URL, settings.apiUrl.replace(/\/+$/, ""));
  if (settings.apiKey) {
    window.localStorage.setItem(LS_API_KEY, settings.apiKey);
  } else {
    window.localStorage.removeItem(LS_API_KEY);
  }
  // WS is derived from the API URL unless an explicit override is saved later.
  window.localStorage.removeItem(LS_WS_URL);
  clearAccessToken();
  window.dispatchEvent(new Event("algore:settings"));
}

export function resetConnectionSettings(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(LS_API_URL);
  window.localStorage.removeItem(LS_WS_URL);
  window.localStorage.removeItem(LS_API_KEY);
  clearAccessToken();
  window.dispatchEvent(new Event("algore:settings"));
}

export const API_BASE_URL = DEFAULT_API_URL;
export const WS_BASE_URL = DEFAULT_WS_URL;
export const IS_LIVE = DEFAULT_API_URL.length > 0;

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail || `Request failed (${status})`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

interface CachedToken {
  value: string;
  expiresAt: number;
}

let cachedToken: CachedToken | null = null;
let tokenPromise: Promise<string> | null = null;

function readDetail(value: unknown): string {
  if (!value || typeof value !== "object") {
    return "";
  }
  const detail = (value as { detail?: unknown }).detail;
  return typeof detail === "string" ? detail : "";
}

async function parseError(response: Response): Promise<ApiError> {
  let detail = "";
  try {
    const text = await response.text();
    if (text) {
      try {
        detail = readDetail(JSON.parse(text));
      } catch {
        detail = text.slice(0, 240);
      }
    }
  } catch {
    detail = "";
  }
  return new ApiError(response.status, detail);
}

export function clearAccessToken(): void {
  cachedToken = null;
  tokenPromise = null;
}

export async function getAccessToken(): Promise<string> {
  const apiUrl = getApiUrl();
  if (!apiUrl) {
    throw new ApiError(0, "API URL is not configured — open Connection Settings");
  }
  const apiKey = getApiKey();
  if (!apiKey) {
    throw new ApiError(0, "Dashboard key is not configured — open Connection Settings");
  }
  if (cachedToken && Date.now() < cachedToken.expiresAt - 60_000) {
    return cachedToken.value;
  }
  if (tokenPromise) {
    return tokenPromise;
  }

  tokenPromise = (async () => {
    const response = await fetch(`${apiUrl}/api/v1/auth/token`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: apiKey }),
      cache: "no-store",
    });
    if (!response.ok) {
      throw await parseError(response);
    }
    const data = (await response.json()) as TokenResponse;
    const lifetimeMs = Math.max(60, (data.expires_in || 3600) - 300) * 1000;
    cachedToken = {
      value: data.access_token,
      expiresAt: Date.now() + lifetimeMs,
    };
    return cachedToken.value;
  })();

  try {
    return await tokenPromise;
  } finally {
    tokenPromise = null;
  }
}

interface RequestOptions {
  method?: "GET" | "POST";
  body?: unknown;
  authenticated?: boolean;
  signal?: AbortSignal;
}

async function request<T>(
  path: string,
  options: RequestOptions = {},
  allowRetry = true,
): Promise<T> {
  const headers = new Headers();
  headers.set("Accept", "application/json");
  if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  const token = options.authenticated === false ? "" : await getAccessToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${getApiUrl()}/api/v1${path}`, {
    method: options.method ?? "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    cache: "no-store",
    signal: options.signal,
  });

  if (response.status === 401 && allowRetry && token) {
    clearAccessToken();
    return request<T>(path, options, false);
  }
  if (!response.ok) {
    throw await parseError(response);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

async function requestBlob(
  path: string,
  allowRetry = true,
): Promise<{ blob: Blob; filename: string }> {
  const token = await getAccessToken();
  const response = await fetch(`${getApiUrl()}/api/v1${path}`, {
    method: "GET",
    headers: {
      Accept: "text/plain, application/octet-stream",
      Authorization: `Bearer ${token}`,
    },
    cache: "no-store",
  });
  if (response.status === 401 && allowRetry) {
    clearAccessToken();
    return requestBlob(path, false);
  }
  if (!response.ok) {
    throw await parseError(response);
  }
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const match = disposition.match(/filename="?([^";]+)"?/i);
  return {
    blob: await response.blob(),
    filename: match?.[1] ?? "strategy.mq5",
  };
}

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") {
      search.set(key, String(value));
    }
  }
  const value = search.toString();
  return value ? `?${value}` : "";
}

export const api = {
  health: () => request<HealthResponse>("/health"),
  campaigns: () => request<CampaignSummary[]>("/campaigns"),
  campaign: (id: string) => request<CampaignDetail>(`/campaigns/${encodeURIComponent(id)}`),
  createCampaign: (input: CampaignCreateInput) =>
    request<{ campaign_id: string; status: string }>("/campaigns", {
      method: "POST",
      body: input,
    }),
  stopCampaign: (id: string) =>
    request<{ status: string }>(`/campaigns/${encodeURIComponent(id)}/stop`, {
      method: "POST",
      body: {},
    }),
  vault: (params: {
    min_score?: number;
    symbol?: string;
    timeframe?: string;
    archetype?: string;
  } = {}) => request<VaultStrategy[]>(`/vault${query(params)}`),
  vaultPassport: (id: string) =>
    request<VaultPassport>(`/vault/${encodeURIComponent(id)}`),
  parity: (id: string, mt5NetReturn: number) =>
    request<{ grade: string; engine_net_return: number; mt5_net_return: number; diff_pct: number }>(
      `/vault/${encodeURIComponent(id)}/parity`,
      { method: "POST", body: { mt5_net_return: mt5NetReturn } },
    ),
  reassess: (id: string) =>
    request<{ verdict: string; trades_since: number; score_delta: number; expectancy: number }>(
      `/vault/${encodeURIComponent(id)}/reassess`,
      { method: "POST", body: {} },
    ),
  downloadMq5: (id: string) => requestBlob(`/vault/${encodeURIComponent(id)}/export.mq5`),
  incubation: () => request<IncubationBot[]>("/incubation"),
  incubationBot: (botId: string) =>
    request<IncubationBot>(`/incubation/${encodeURIComponent(botId)}`),
  graduate: (botId: string) =>
    request<IncubationBot>(`/incubation/${encodeURIComponent(botId)}/graduate`, {
      method: "POST",
      body: {},
    }),
  setRung: (botId: string, rung: "INCUBATION" | "PROVING" | "FULL", reason: string) =>
    request<IncubationBot>(`/incubation/${encodeURIComponent(botId)}/rung`, {
      method: "POST",
      body: { rung, reason },
    }),
  setAuto: (botId: string, auto: boolean) =>
    request<IncubationBot>(`/incubation/${encodeURIComponent(botId)}/auto`, {
      method: "POST",
      body: { auto },
    }),
  pauseBot: (botId: string, paused: boolean) =>
    request<IncubationBot>(`/incubation/${encodeURIComponent(botId)}/pause`, {
      method: "POST",
      body: { paused },
    }),
  pauseAll: (paused: boolean, reason?: string) =>
    request<{ paused: boolean }>("/incubation/pause-all", {
      method: "POST",
      body: reason ? { paused, reason } : { paused },
    }),
  pilotStatus: () => request<PilotStatus>("/pilot/status"),
  alerts: (active = true) => request<Alert[]>(`/alerts${query({ active: active ? 1 : 0 })}`),
  portfolios: () => request<PortfolioDetail[]>("/portfolios"),
};
