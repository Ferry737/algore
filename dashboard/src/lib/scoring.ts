import type { ScorePart, ScoreParts, VaultStrategy } from "./types";

export interface ScorePartMeta {
  key: keyof ScoreParts;
  label: string;
  weight: number;
  published: boolean;
}

export const SCORE_PARTS: ScorePartMeta[] = [
  { key: "persistence", label: "Persistence", weight: 20, published: true },
  { key: "recovery", label: "Recovery", weight: 15, published: true },
  { key: "sharpe", label: "Sharpe", weight: 15, published: true },
  { key: "trades", label: "Trades", weight: 15, published: true },
  { key: "max_drawdown", label: "Max drawdown", weight: 10, published: true },
  { key: "profit_factor", label: "Profit factor", weight: 10, published: true },
  { key: "is_linearity", label: "IS linearity", weight: 3, published: true },
  { key: "robustness", label: "Robustness", weight: 12, published: false },
];

export const INFERRED_LABEL = "inferred";
export const INFERRED_DESCRIPTION =
  "Custom metric — not published by the reference product; the eighth published weight is unknown";

const SCORE_KEYS = [
  "persistence",
  "recovery",
  "sharpe",
  "trades",
  "max_drawdown",
  "profit_factor",
  "is_linearity",
  "robustness",
] as const;

function isScoreParts(value: unknown): value is ScoreParts {
  if (!value || typeof value !== "object") {
    return false;
  }
  return SCORE_KEYS.every((key) => typeof (value as Record<string, unknown>)[key] === "number");
}

function fromArray(parts: ScorePart[]): ScoreParts {
  const value = Object.fromEntries(parts.map((part) => [part.key, part.value]));
  return fromRecord(value);
}

function fromRecord(value: Record<string, number>): ScoreParts {
  return {
    persistence: value.persistence ?? 0,
    recovery: value.recovery ?? 0,
    sharpe: value.sharpe ?? 0,
    trades: value.trades ?? 0,
    max_drawdown: value.max_drawdown ?? 0,
    profit_factor: value.profit_factor ?? 0,
    is_linearity: value.is_linearity ?? 0,
    robustness: value.robustness ?? 0,
  };
}

export function readScoreParts(strategy: VaultStrategy): ScoreParts {
  const parts = strategy.score_parts;
  if (isScoreParts(parts)) {
    return parts;
  }
  if (Array.isArray(parts)) {
    return fromArray(parts);
  }
  return fromRecord(parts);
}

export function scorePartsTotal(strategy: VaultStrategy): number {
  return Math.round(
    SCORE_PARTS.reduce((total, part) => total + readScoreParts(strategy)[part.key] * part.weight, 0) /
      100,
  );
}
