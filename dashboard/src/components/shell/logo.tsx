import { cn } from "@/lib/cn";

export function LogoMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      className={cn("h-9 w-9", className)}
      aria-hidden="true"
    >
      <rect
        x="0.5"
        y="0.5"
        width="31"
        height="31"
        rx="9"
        fill="#111114"
        stroke="rgba(255,255,255,0.12)"
      />
      <circle
        cx="16"
        cy="16"
        r="9"
        fill="none"
        stroke="#10B981"
        strokeWidth="1.4"
        opacity="0.9"
      />
      <path
        d="M10.5 19.2l3.6-4.2 2.7 2.2 4.2-5.2"
        fill="none"
        stroke="#F4F4F5"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="21" cy="12" r="1.2" fill="#10B981" />
    </svg>
  );
}

export function Wordmark({ compact = false }: { compact?: boolean }) {
  return (
    <span className="flex items-center gap-2.5">
      <LogoMark className={compact ? "h-8 w-8" : "h-9 w-9"} />
      <span className="flex flex-col">
        <span className="text-[13px] font-semibold leading-none tracking-[0.22em] text-ink">
          ALGORE
        </span>
        {!compact ? (
          <span className="mt-1 text-[10px] font-medium uppercase leading-none tracking-[0.16em] text-subtle">
            strategy engine
          </span>
        ) : null}
      </span>
    </span>
  );
}
