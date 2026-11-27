"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import type { ReactNode } from "react";
import {
  api,
  clearAccessToken,
  getAccessToken,
  getApiUrl,
  getWsUrl,
} from "./api";
import {
  advanceDemoSnapshot,
  buildDemoSnapshot,
  createDemoCampaign,
  demoMq5,
} from "./demo";
import { openLiveSocket, type SocketStatus } from "./ws";
import type {
  AlgoSnapshot,
  CampaignCreateInput,
  CampaignDetail,
  CampaignSummary,
  EquityPoint,
  Mode,
  Tier,
  VaultStrategy,
  WsEvent,
} from "./types";

const EMPTY_SNAPSHOT: AlgoSnapshot = {
  health: null,
  equity: [],
  campaigns: [],
  campaignDetails: {},
  vault: [],
  bots: [],
  alerts: [],
  pilot: null,
  portfolios: [],
};

export interface DownloadResult {
  filename: string;
  demo: boolean;
}

export interface AlgoActions {
  startCampaign: (input: CampaignCreateInput) => Promise<string>;
  stopCampaign: (campaignId: string) => Promise<void>;
  graduate: (botId: string) => Promise<void>;
  setAuto: (botId: string, auto: boolean) => Promise<void>;
  setRung: (
    botId: string,
    rung: Exclude<Tier, null>,
    reason: string,
  ) => Promise<void>;
  pauseBot: (botId: string, paused: boolean) => Promise<void>;
  pauseAll: (paused: boolean, reason?: string) => Promise<void>;
  downloadMq5: (strategy: VaultStrategy) => Promise<DownloadResult>;
}

interface AlgoDataValue {
  mode: Mode;
  data: AlgoSnapshot;
  loading: boolean;
  error: string | null;
  socketStatus: SocketStatus;
  actions: AlgoActions;
}

const AlgoDataContext = createContext<AlgoDataValue | null>(null);

function multiplierFor(tier: Tier | null): number {
  if (tier === "FULL") return 1;
  if (tier === "PROVING") return 0.5;
  if (tier === "INCUBATION") return 0.25;
  return 0;
}

function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}

function slugify(value: string): string {
  return (
    value
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "") || "strategy"
  );
}

function appendEquity(equity: EquityPoint[], point: EquityPoint): EquityPoint[] {
  const last = equity[equity.length - 1];
  if (last && last.ts >= point.ts) {
    return equity;
  }
  return [...equity.slice(-89), point];
}

function applyWsEvent(snapshot: AlgoSnapshot, event: WsEvent): AlgoSnapshot {
  switch (event.type) {
    case "campaign.progress": {
      const data = event.data;
      const summary = snapshot.campaigns.find(
        (campaign) => campaign.campaign_id === data.campaign_id,
      );
      if (!summary) {
        return snapshot;
      }
      const updatedSummary: CampaignSummary = {
        ...summary,
        generation: data.generation,
        generations_total: data.generations_total,
        best_fitness: data.best_fitness,
        stage: data.stage,
        elapsed_s: data.elapsed_s,
        eta_s: data.eta_s,
        status: "running",
      };
      const detail = snapshot.campaignDetails[data.campaign_id];
      const point = {
        tribe: data.tribe,
        generation: data.generation,
        best_fitness: data.best_fitness,
        mean_fitness: data.mean_fitness,
        survivors: data.survivors,
        elapsed_s: data.elapsed_s,
      };
      const generations = detail
        ? [
            ...detail.generations.filter(
              (item) =>
                !(
                  item.tribe === data.tribe &&
                  item.generation === data.generation
                ),
            ),
            point,
          ].sort((a, b) => a.generation - b.generation)
        : [point];
      const updatedDetail: CampaignDetail = detail
        ? {
            ...detail,
            ...updatedSummary,
            progress: data,
            generations,
          }
        : {
            ...updatedSummary,
            progress: data,
            generations,
            gates: { passed: false, rejected_by: {} },
          };
      return {
        ...snapshot,
        campaigns: snapshot.campaigns.map((campaign) =>
          campaign.campaign_id === updatedSummary.campaign_id
            ? updatedSummary
            : campaign,
        ),
        campaignDetails: {
          ...snapshot.campaignDetails,
          [data.campaign_id]: updatedDetail,
        },
      };
    }
    case "campaign.done": {
      const data = event.data;
      const updateSummary = (campaign: CampaignSummary): CampaignSummary =>
        campaign.campaign_id === data.campaign_id
          ? {
              ...campaign,
              status: "done",
              stage: "done",
              eta_s: 0,
              vaulted: data.vaulted.length,
            }
          : campaign;
      const detail = snapshot.campaignDetails[data.campaign_id];
      return {
        ...snapshot,
        campaigns: snapshot.campaigns.map(updateSummary),
        campaignDetails: detail
          ? {
              ...snapshot.campaignDetails,
              [data.campaign_id]: {
                ...detail,
                ...updateSummary(detail),
                gates: { passed: true, rejected_by: data.rejected },
              },
            }
          : snapshot.campaignDetails,
      };
    }
    case "vault.added":
      return snapshot;
    case "equity.update":
      return {
        ...snapshot,
        equity: appendEquity(snapshot.equity, {
          account_login: event.data.account_login,
          equity: event.data.equity,
          balance: event.data.balance,
          ts: event.data.ts,
        }),
      };
    case "incubation.transition": {
      const data = event.data;
      return {
        ...snapshot,
        bots: snapshot.bots.map((bot) =>
          bot.bot_id === data.bot_id
            ? {
                ...bot,
                tier: data.to_tier,
                multiplier: data.multiplier_after,
                effective_risk_pct: bot.target_risk_pct * data.multiplier_after,
                pending_graduation: false,
              }
            : bot,
        ),
      };
    }
    case "pilot.heartbeat": {
      const data = event.data;
      const chart = data.chart
        ? {
            symbol: data.chart.symbol ?? "EURUSD",
            period_minutes: data.chart.period_minutes ?? 60,
            chart_id: data.chart.chart_id,
          }
        : null;
      return {
        ...snapshot,
        pilot: snapshot.pilot
          ? {
              ...snapshot.pilot,
              online: data.online,
              last_heartbeat_at:
                event.ts ?? new Date().toISOString(),
              chart: chart ?? snapshot.pilot.chart,
            }
          : {
              online: data.online,
              last_heartbeat_at: event.ts ?? new Date().toISOString(),
              chart,
              account: null,
              bots: [],
              silent_bots: [],
            },
      };
    }
    case "pilot.trade":
      return snapshot;
    case "alert": {
      const data = event.data;
      return {
        ...snapshot,
        alerts: [
          {
            id: `ws_alert_${Date.now()}_${data.kind}`,
            bot_id: data.bot_id,
            kind: data.kind,
            severity: data.severity,
            message: data.message,
            value: null,
            threshold: null,
            created_at: event.ts ?? new Date().toISOString(),
            resolved_at: null,
          },
          ...snapshot.alerts,
        ].slice(0, 12),
      };
    }
    default:
      return snapshot;
  }
}

export function AlgoDataProvider({ children }: { children: ReactNode }) {
  const [endpoint, setEndpoint] = useState(() => ({
    apiUrl: getApiUrl(),
    wsUrl: getWsUrl(),
  }));
  const hasEndpoint = endpoint.apiUrl.length > 0;
  const mode: Mode = hasEndpoint ? "live" : "demo";
  const [snapshot, setSnapshot] = useState<AlgoSnapshot>(() =>
    hasEndpoint ? EMPTY_SNAPSHOT : buildDemoSnapshot(),
  );
  const [loading, setLoading] = useState(hasEndpoint);
  const [error, setError] = useState<string | null>(null);
  const [socketStatus, setSocketStatus] = useState<SocketStatus>("idle");
  const tickRef = useRef(0);
  const snapshotRef = useRef(snapshot);

  useEffect(() => {
    snapshotRef.current = snapshot;
  }, [snapshot]);

  // Connection Settings can change endpoint/key from localStorage at any time.
  useEffect(() => {
    const onSettings = () => {
      clearAccessToken();
      setEndpoint({ apiUrl: getApiUrl(), wsUrl: getWsUrl() });
      setError(null);
    };
    window.addEventListener("algore:settings", onSettings);
    window.addEventListener("storage", onSettings);
    return () => {
      window.removeEventListener("algore:settings", onSettings);
      window.removeEventListener("storage", onSettings);
    };
  }, []);

  useEffect(() => {
    if (mode !== "demo") {
      return;
    }
    const interval = setInterval(() => {
      tickRef.current += 1;
      const tick = tickRef.current;
      setSnapshot((previous) => advanceDemoSnapshot(previous, tick));
    }, 1000);
    return () => clearInterval(interval);
  }, [mode]);

  const fetchSnapshot = useCallback(async () => {
    const [
      healthResult,
      campaignsResult,
      vaultResult,
      botsResult,
      alertsResult,
      pilotResult,
      portfoliosResult,
    ] = await Promise.allSettled([
      api.health(),
      api.campaigns(),
      api.vault(),
      api.incubation(),
      api.alerts(true),
      api.pilotStatus(),
      api.portfolios(),
    ]);

    const campaigns =
      campaignsResult.status === "fulfilled" ? campaignsResult.value : null;
    let details: Record<string, CampaignDetail> = {};
    if (campaigns) {
      const settled = await Promise.allSettled(
        campaigns.map((campaign) => api.campaign(campaign.campaign_id)),
      );
      details = Object.fromEntries(
        settled.flatMap((result) =>
          result.status === "fulfilled"
            ? [[result.value.campaign_id, result.value] as const]
            : [],
        ),
      );
    }

    const failures = [
      healthResult,
      campaignsResult,
      vaultResult,
      botsResult,
      alertsResult,
      pilotResult,
      portfoliosResult,
    ].flatMap((result) => (result.status === "rejected" ? [result.reason] : []));
    setError(failures.length ? String(failures[0]) : null);

    setSnapshot((previous) => {
      const portfolios =
        portfoliosResult.status === "fulfilled" ? portfoliosResult.value : previous.portfolios;
      const avgCorr = new Map<string, number>();
      portfolios.forEach((portfolio) => {
        portfolio.members.forEach((member) => {
          avgCorr.set(member.strategy_id, member.avg_corr);
        });
      });
      const vault = (vaultResult.status === "fulfilled"
        ? vaultResult.value
        : previous.vault
      ).map((strategy) => ({
        ...strategy,
        avg_corr: strategy.avg_corr ?? avgCorr.get(strategy.strategy_id),
      }));

      return {
        health:
          healthResult.status === "fulfilled" ? healthResult.value : previous.health,
        equity: previous.equity,
        campaigns: campaigns ?? previous.campaigns,
        campaignDetails: Object.keys(details).length ? details : previous.campaignDetails,
        vault,
        bots: botsResult.status === "fulfilled" ? botsResult.value : previous.bots,
        alerts: alertsResult.status === "fulfilled" ? alertsResult.value : previous.alerts,
        pilot: pilotResult.status === "fulfilled" ? pilotResult.value : previous.pilot,
        portfolios,
      };
    });
    setLoading(false);
  }, []);

  useEffect(() => {
    if (mode !== "live") {
      return;
    }
    const timer = window.setTimeout(() => {
      void fetchSnapshot();
    }, 0);
    const interval = setInterval(() => {
      void fetchSnapshot();
    }, 15_000);
    return () => {
      window.clearTimeout(timer);
      clearInterval(interval);
    };
  }, [mode, fetchSnapshot]);

  useEffect(() => {
    if (mode !== "live" || !endpoint.wsUrl) {
      return;
    }
    return openLiveSocket({
      url: endpoint.wsUrl,
      getToken: getAccessToken,
      onEvent: (event) => {
        setSnapshot((previous) => applyWsEvent(previous, event));
        if (event.type === "campaign.done" || event.type === "vault.added") {
          void fetchSnapshot();
        }
      },
      onStatus: (status) => {
        setSocketStatus(status);
        if (status === "open") {
          void fetchSnapshot();
        }
      },
    });
  }, [mode, fetchSnapshot, endpoint.wsUrl]);

  const startCampaign = useCallback(
    async (input: CampaignCreateInput): Promise<string> => {
      if (mode === "demo") {
        const next = createDemoCampaign(snapshotRef.current, input);
        setSnapshot(next.snapshot);
        return next.campaignId;
      }
      const result = await api.createCampaign(input);
      await fetchSnapshot();
      return result.campaign_id;
    },
    [mode, fetchSnapshot],
  );

  const stopCampaign = useCallback(
    async (campaignId: string): Promise<void> => {
      if (mode === "demo") {
        setSnapshot((previous) => ({
          ...previous,
          campaigns: previous.campaigns.map((campaign) =>
            campaign.campaign_id === campaignId
              ? { ...campaign, status: "stopped", stage: "done", eta_s: 0 }
              : campaign,
          ),
          campaignDetails: {
            ...previous.campaignDetails,
            [campaignId]: previous.campaignDetails[campaignId]
              ? {
                  ...previous.campaignDetails[campaignId],
                  status: "stopped",
                  stage: "done",
                  eta_s: 0,
                }
              : previous.campaignDetails[campaignId],
          },
        }));
        return;
      }
      await api.stopCampaign(campaignId);
      await fetchSnapshot();
    },
    [mode, fetchSnapshot],
  );

  const graduate = useCallback(
    async (botId: string): Promise<void> => {
      if (mode === "demo") {
        setSnapshot((previous) => ({
          ...previous,
          bots: previous.bots.map((bot) => {
            if (bot.bot_id !== botId) {
              return bot;
            }
            const tier: Tier | null =
              bot.tier === "INCUBATION" ? "PROVING" : bot.tier === "PROVING" ? "FULL" : bot.tier;
            const multiplier = multiplierFor(tier);
            return {
              ...bot,
              tier,
              multiplier,
              effective_risk_pct: bot.target_risk_pct * multiplier,
              pending_graduation: false,
            };
          }),
        }));
        return;
      }
      const bot = await api.graduate(botId);
      setSnapshot((previous) => ({
        ...previous,
        bots: previous.bots.map((item) => (item.bot_id === botId ? bot : item)),
      }));
    },
    [mode],
  );

  const setAuto = useCallback(
    async (botId: string, auto: boolean): Promise<void> => {
      if (mode === "demo") {
        setSnapshot((previous) => ({
          ...previous,
          bots: previous.bots.map((bot) =>
            bot.bot_id === botId
              ? { ...bot, auto, pending_graduation: auto ? false : bot.pending_graduation }
              : bot,
          ),
        }));
        return;
      }
      const bot = await api.setAuto(botId, auto);
      setSnapshot((previous) => ({
        ...previous,
        bots: previous.bots.map((item) => (item.bot_id === botId ? bot : item)),
      }));
    },
    [mode],
  );

  const setRung = useCallback(
    async (botId: string, rung: Exclude<Tier, null>, reason: string): Promise<void> => {
      if (mode === "demo") {
        setSnapshot((previous) => ({
          ...previous,
          bots: previous.bots.map((bot) =>
            bot.bot_id === botId
              ? {
                  ...bot,
                  tier: rung,
                  multiplier: multiplierFor(rung),
                  effective_risk_pct: bot.target_risk_pct * multiplierFor(rung),
                  pending_graduation: false,
                }
              : bot,
          ),
        }));
        return;
      }
      const bot = await api.setRung(botId, rung, reason);
      setSnapshot((previous) => ({
        ...previous,
        bots: previous.bots.map((item) => (item.bot_id === botId ? bot : item)),
      }));
    },
    [mode],
  );

  const pauseBot = useCallback(
    async (botId: string, paused: boolean): Promise<void> => {
      if (mode === "demo") {
        setSnapshot((previous) => ({
          ...previous,
          bots: previous.bots.map((bot) =>
            bot.bot_id === botId ? { ...bot, paused } : bot,
          ),
        }));
        return;
      }
      const bot = await api.pauseBot(botId, paused);
      setSnapshot((previous) => ({
        ...previous,
        bots: previous.bots.map((item) => (item.bot_id === botId ? bot : item)),
      }));
    },
    [mode],
  );

  const pauseAll = useCallback(
    async (paused: boolean, reason?: string): Promise<void> => {
      if (mode === "demo") {
        setSnapshot((previous) => ({
          ...previous,
          bots: previous.bots.map((bot) => ({ ...bot, paused })),
        }));
        return;
      }
      await api.pauseAll(paused, reason);
      setSnapshot((previous) => ({
        ...previous,
        bots: previous.bots.map((bot) => ({ ...bot, paused })),
      }));
    },
    [mode],
  );

  const downloadMq5 = useCallback(
    async (strategy: VaultStrategy): Promise<DownloadResult> => {
      if (mode === "demo") {
        const blob = new Blob([demoMq5(strategy)], {
          type: "text/plain;charset=utf-8",
        });
        const filename = `${slugify(strategy.name)}.mq5`;
        saveBlob(blob, filename);
        return { filename, demo: true };
      }
      const download = await api.downloadMq5(strategy.strategy_id);
      saveBlob(download.blob, download.filename);
      return { filename: download.filename, demo: false };
    },
    [mode],
  );

  const actions: AlgoActions = {
    startCampaign,
    stopCampaign,
    graduate,
    setAuto,
    setRung,
    pauseBot,
    pauseAll,
    downloadMq5,
  };

  return (
    <AlgoDataContext.Provider
      value={{ mode, data: snapshot, loading, error, socketStatus, actions }}
    >
      {children}
    </AlgoDataContext.Provider>
  );
}

export function useAlgoData(): AlgoDataValue {
  const value = useContext(AlgoDataContext);
  if (!value) {
    throw new Error("useAlgoData must be used inside AlgoDataProvider");
  }
  return value;
}
