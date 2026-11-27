"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown } from "lucide-react";
import type { VaultStrategy } from "@/lib/types";
import { INFERRED_DESCRIPTION, INFERRED_LABEL, SCORE_PARTS, readScoreParts } from "@/lib/scoring";
import { cn } from "@/lib/cn";

export function ScoreParts({
  strategy,
  className,
}: {
  strategy: VaultStrategy;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const parts = readScoreParts(strategy);

  return (
    <div className={cn("border-t border-line", className)}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex min-h-11 w-full items-center justify-between gap-3 py-2 text-left text-[12px] font-medium text-muted transition hover:text-ink"
      >
        <span>Score parts</span>
        <span className="flex items-center gap-2">
          <span className="num text-[11px] text-subtle">{strategy.score} composite</span>
          <ChevronDown
            className={cn("h-4 w-4 transition-transform duration-200", open && "rotate-180")}
          />
        </span>
      </button>
      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
            className="overflow-hidden"
          >
            <div className="pb-1">
              {SCORE_PARTS.map((part) => (
                <div
                  key={part.key}
                  className="flex items-center justify-between gap-3 border-t border-line py-[7px] first:border-t-0"
                >
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="truncate text-[12px] text-ink/90">{part.label}</span>
                    {part.published ? (
                      <span className="rounded-full border border-emerald/20 bg-emerald/[0.07] px-1.5 py-[1px] text-[10px] font-medium leading-[14px] text-emerald">
                        published
                      </span>
                    ) : (
                      <span
                        title={INFERRED_DESCRIPTION}
                        aria-label={INFERRED_DESCRIPTION}
                        className="rounded-full border border-amber/25 bg-amber/[0.08] px-1.5 py-[1px] text-[10px] font-medium leading-[14px] text-amber"
                      >
                        {INFERRED_LABEL}
                      </span>
                    )}
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span className="num text-[11px] text-subtle">{part.weight}%</span>
                    <span className="num w-7 text-right text-[12px] text-ink/90">
                      {parts[part.key]}
                    </span>
                  </div>
                </div>
              ))}
              <p className="mt-1 text-[11px] leading-4 text-subtle">
                The seven published weights sum to 88. Robustness carries the inferred 12.
              </p>
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
