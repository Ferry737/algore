"use client";

import { motion } from "framer-motion";
import type { GenerationPoint } from "@/lib/types";

const width = 640;
const height = 230;
const padX = 10;
const padTop = 16;
const padBottom = 26;

function buildLine(points: GenerationPoint[], key: "best_fitness" | "mean_fitness"): string {
  if (points.length === 0) {
    return "";
  }
  const values = points.map((point) => point[key]);
  const min = Math.min(...values, 40);
  const max = Math.max(...values, 100);
  const range = max - min || 1;
  return points
    .map((point, index) => {
      const x = padX + (index / Math.max(1, points.length - 1)) * (width - padX * 2);
      const y = padTop + (1 - (point[key] - min) / range) * (height - padTop - padBottom);
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

export function FitnessChart({
  points,
  tribe,
}: {
  points: GenerationPoint[];
  tribe: string;
}) {
  const filtered = points.filter((point) => point.tribe === tribe);
  const bestLine = buildLine(filtered, "best_fitness");
  const meanLine = buildLine(filtered, "mean_fitness");
  const generations = filtered.length;

  if (filtered.length === 0) {
    return (
      <div className="flex h-[230px] items-center justify-center rounded-xl border border-dashed border-line bg-canvas/40">
        <p className="text-[12px] text-subtle">No generations scored yet.</p>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-3 flex items-center justify-end gap-4 text-[11px] text-subtle">
        <span className="flex items-center gap-1.5">
          <span className="h-1.5 w-4 rounded-full bg-emerald" /> best
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-1.5 w-4 rounded-full bg-subtle" /> mean
        </span>
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="h-auto w-full"
        role="img"
        aria-label={`${tribe} fitness over ${generations} generations`}
      >
        {[0.25, 0.5, 0.75].map((ratio) => (
          <line
            key={ratio}
            x1={padX}
            x2={width - padX}
            y1={padTop + ratio * (height - padTop - padBottom)}
            y2={padTop + ratio * (height - padTop - padBottom)}
            stroke="rgba(255,255,255,0.05)"
            strokeWidth="1"
          />
        ))}
        <motion.path
          key={`${tribe}-mean`}
          d={meanLine}
          fill="none"
          stroke="rgba(161,161,170,0.55)"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 1.1, ease: [0.22, 1, 0.36, 1] }}
        />
        <motion.path
          key={`${tribe}-best`}
          d={bestLine}
          fill="none"
          stroke="#10B981"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 1.2, ease: [0.22, 1, 0.36, 1] }}
        />
        <text x={padX} y={height - 6} fill="#71717a" fontSize="10">
          gen 1
        </text>
        <text x={width - padX} y={height - 6} fill="#71717a" fontSize="10" textAnchor="end">
          gen {filtered[filtered.length - 1]?.generation ?? 1}
        </text>
      </svg>
    </div>
  );
}
