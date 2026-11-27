import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export function EmptyState({
  icon,
  title,
  description,
  className,
}: {
  icon: ReactNode;
  title: string;
  description: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex min-h-[160px] flex-col items-center justify-center rounded-2xl border border-dashed border-line bg-canvas/30 px-5 py-8 text-center",
        className,
      )}
    >
      <span className="flex h-10 w-10 items-center justify-center rounded-xl border border-line bg-panel text-subtle">
        {icon}
      </span>
      <p className="mt-3 text-sm font-medium text-ink">{title}</p>
      <p className="mt-1 max-w-[36ch] text-[12px] leading-5 text-subtle">{description}</p>
    </div>
  );
}
