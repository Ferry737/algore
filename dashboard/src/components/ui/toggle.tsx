"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/cn";

export function Toggle({
  checked,
  onChange,
  label,
  disabled = false,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative h-11 w-14 shrink-0 rounded-full transition-colors duration-200 disabled:opacity-40",
        checked ? "bg-emerald/20" : "bg-white/[0.06]",
      )}
    >
      <span
        className={cn(
          "absolute inset-x-0 top-1/2 h-7 -translate-y-1/2 rounded-full border transition-colors",
          checked ? "border-emerald/40 bg-emerald/15" : "border-line-strong bg-white/[0.04]",
        )}
      />
      <motion.span
        layout
        transition={{ type: "spring", stiffness: 520, damping: 34 }}
        className={cn(
          "absolute top-1/2 h-6 w-6 -translate-y-1/2 rounded-full shadow-sm",
          checked ? "left-[26px] bg-emerald" : "left-1 bg-muted",
        )}
      />
    </button>
  );
}
