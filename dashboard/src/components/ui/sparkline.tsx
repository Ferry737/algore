"use client";

import { useId } from "react";
import { motion } from "framer-motion";
import type { EquityPoint } from "@/lib/types";
import { cn } from "@/lib/cn";

interface Point {
  x: number;
  y: number;
}

function buildPoints(values: number[], width: number, height: number, pad: number): Point[] {
  if (values.length === 0) {
    return [];
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const innerWidth = width - pad * 2;
  const innerHeight = height - pad * 2;
  return values.map((value, index) => ({
    x: pad + (index / Math.max(1, values.length - 1)) * innerWidth,
    y: pad + (1 - (value - min) / range) * innerHeight,
  }));
}

function smoothPath(points: Point[]): string {
  if (points.length === 0) {
    return "";
  }
  if (points.length === 1) {
    return `M ${points[0].x} ${points[0].y}`;
  }
  let path = `M ${points[0].x.toFixed(2)} ${points[0].y.toFixed(2)}`;
  for (let index = 0; index < points.length - 1; index += 1) {
    const p0 = points[index - 1] ?? points[index];
    const p1 = points[index];
    const p2 = points[index + 1];
    const p3 = points[index + 2] ?? p2;
    const cp1x = p1.x + (p2.x - p0.x) / 6;
    const cp1y = p1.y + (p2.y - p0.y) / 6;
    const cp2x = p2.x - (p3.x - p1.x) / 6;
    const cp2y = p2.y - (p3.y - p1.y) / 6;
    path += ` C ${cp1x.toFixed(2)} ${cp1y.toFixed(2)}, ${cp2x.toFixed(2)} ${cp2y.toFixed(2)}, ${p2.x.toFixed(2)} ${p2.y.toFixed(2)}`;
  }
  return path;
}

export function Sparkline({
  points,
  className,
  height = 190,
}: {
  points: EquityPoint[];
  className?: string;
  height?: number;
}) {
  const rawId = useId();
  const gradientId = `equity-fill-${rawId.replace(/:/g, "")}`;
  const width = 640;
  const pad = 8;
  const values = points.map((point) => point.equity);
  const coords = buildPoints(values, width, height, pad);
  const line = smoothPath(coords);
  const area =
    coords.length > 1
      ? `${line} L ${coords[coords.length - 1].x.toFixed(2)} ${height} L ${coords[0].x.toFixed(2)} ${height} Z`
      : "";

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className={cn("h-auto w-full overflow-visible", className)}
      role="img"
      aria-label="Live equity curve"
      preserveAspectRatio="xMidYMid meet"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#10B981" stopOpacity="0.16" />
          <stop offset="100%" stopColor="#10B981" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${gradientId})`} />
      <motion.path
        d={line}
        fill="none"
        stroke="#10B981"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
        initial={{ pathLength: 0, opacity: 0 }}
        animate={{ pathLength: 1, opacity: 1 }}
        transition={{ duration: 1.4, ease: [0.22, 1, 0.36, 1] }}
      />
      {coords.length > 0 ? (
        <circle
          cx={coords[coords.length - 1].x}
          cy={coords[coords.length - 1].y}
          r="4"
          fill="#10B981"
          stroke="#09090B"
          strokeWidth="2"
        />
      ) : null}
    </svg>
  );
}
