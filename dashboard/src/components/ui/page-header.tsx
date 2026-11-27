import type { ReactNode } from "react";

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string;
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-col gap-4 sm:mb-7 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.22em] text-subtle">
          {eyebrow}
        </p>
        <h1 className="text-[28px] font-medium leading-none tracking-[-0.035em] text-ink sm:text-[34px]">
          {title}
        </h1>
        <p className="mt-2 max-w-[62ch] text-[13px] leading-5 text-muted sm:text-sm">
          {description}
        </p>
      </div>
      {actions ? (
        <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
      ) : null}
    </header>
  );
}
