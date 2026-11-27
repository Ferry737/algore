import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export type BadgeTone = "neutral" | "emerald" | "amber" | "rose" | "ink";

const toneClasses: Record<BadgeTone, string> = {
  neutral: "border-line bg-white/[0.03] text-muted",
  emerald: "border-emerald/20 bg-emerald/[0.08] text-emerald",
  amber: "border-amber/25 bg-amber/[0.08] text-amber",
  rose: "border-rose/25 bg-rose/[0.08] text-rose",
  ink: "border-line-strong bg-white/[0.06] text-ink",
};

export function Badge({
  children,
  tone = "neutral",
  className,
  dot = false,
}: {
  children: ReactNode;
  tone?: BadgeTone;
  className?: string;
  dot?: boolean;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-[3px] text-[11px] font-medium leading-4 tracking-[0.04em]",
        toneClasses[tone],
        className,
      )}
    >
      {dot ? (
        <span
          className={cn(
            "h-1.5 w-1.5 rounded-full",
            tone === "emerald" && "bg-emerald",
            tone === "amber" && "bg-amber",
            tone === "rose" && "bg-rose",
            tone === "ink" && "bg-ink",
            tone === "neutral" && "bg-muted",
          )}
        />
      ) : null}
      {children}
    </span>
  );
}

export function Dot({
  tone = "neutral",
  className,
  pulse = false,
}: {
  tone?: BadgeTone;
  className?: string;
  pulse?: boolean;
}) {
  return (
    <span className={cn("relative inline-flex h-2 w-2 shrink-0", className)}>
      {pulse ? (
        <span
          className={cn(
            "absolute inline-flex h-full w-full rounded-full opacity-60",
            tone === "emerald" && "bg-emerald",
            tone === "amber" && "bg-amber",
            tone === "rose" && "bg-rose",
            tone === "ink" && "bg-ink",
            tone === "neutral" && "bg-muted",
            "animate-ping",
          )}
        />
      ) : null}
      <span
        className={cn(
          "relative inline-flex h-2 w-2 rounded-full",
          tone === "emerald" && "bg-emerald",
          tone === "amber" && "bg-amber",
          tone === "rose" && "bg-rose",
          tone === "ink" && "bg-ink",
          tone === "neutral" && "bg-muted",
        )}
      />
    </span>
  );
}
