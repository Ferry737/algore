"use client";

import { motion, useReducedMotion } from "framer-motion";
import { cn } from "@/lib/cn";

export function LadderRing({
  multiplier,
  frozen = false,
  size = 108,
  strokeWidth = 6,
  className,
}: {
  multiplier: number;
  frozen?: boolean;
  size?: number;
  strokeWidth?: number;
  className?: string;
}) {
  const reduceMotion = useReducedMotion();
  const radius = (size - strokeWidth * 2) / 2;
  const circumference = 2 * Math.PI * radius;
  const progress = Math.min(1, Math.max(0, multiplier));
  const color = frozen ? "var(--color-amber)" : "var(--color-emerald)";

  return (
    <div
      className={cn("relative shrink-0", className)}
      style={{ width: size, height: size }}
      role="img"
      aria-label={`${Math.round(progress * 100)}% of target risk deployed`}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="rgba(255,255,255,0.07)"
          strokeWidth={strokeWidth}
        />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: circumference * (1 - progress) }}
          transition={
            reduceMotion
              ? { duration: 0 }
              : { type: "spring", stiffness: 52, damping: 16, mass: 0.9 }
          }
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="num text-[26px] font-medium leading-none tracking-[-0.04em] text-ink">
          {Math.round(progress * 100)}%
        </span>
        <span className="mt-1 text-[10px] font-medium uppercase tracking-[0.16em] text-subtle">
          risk
        </span>
      </div>
    </div>
  );
}
