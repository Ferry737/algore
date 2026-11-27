"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import type { ReactNode } from "react";
import { useAlgoData } from "@/lib/data-provider";
import { cn } from "@/lib/cn";
import { NAV_ITEMS } from "./nav-items";
import { Wordmark, LogoMark } from "./logo";
import { Badge, Dot } from "@/components/ui/badge";
import { ConnectionSettings } from "./connection-settings";

function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

function pageLabel(pathname: string): string {
  return NAV_ITEMS.find((item) => isActive(pathname, item.href))?.label ?? "Overview";
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { mode, data, socketStatus } = useAlgoData();
  const pilotOnline = data.pilot?.online ?? false;

  return (
    <>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[200] focus:rounded-xl focus:border focus:border-line-strong focus:bg-panel focus:px-4 focus:py-3 focus:text-sm focus:text-ink"
      >
        Skip to content
      </a>

      <aside className="fixed inset-y-0 left-0 z-50 hidden w-[248px] flex-col border-r border-line bg-canvas lg:flex">
        <div className="px-5 pb-6 pt-[calc(22px+env(safe-area-inset-top,0px))]">
          <Link href="/" aria-label="AlgoRE overview" className="inline-flex">
            <Wordmark />
          </Link>
        </div>
        <nav aria-label="Primary" className="flex-1 px-3">
          <p className="mb-2 px-3 text-[10px] font-medium uppercase tracking-[0.18em] text-faint">
            Command
          </p>
          <ul className="space-y-1">
            {NAV_ITEMS.map((item) => {
              const active = isActive(pathname, item.href);
              const Icon = item.icon;
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "group relative flex min-h-11 items-center gap-3 rounded-xl px-3 py-2.5 text-[13px] font-medium transition",
                      active
                        ? "bg-panel text-ink"
                        : "text-muted hover:bg-white/[0.025] hover:text-ink",
                    )}
                  >
                    <Icon
                      className={cn(
                        "h-[18px] w-[18px] shrink-0 transition-colors",
                        active ? "text-emerald" : "text-subtle group-hover:text-muted",
                      )}
                      strokeWidth={1.8}
                    />
                    <span>{item.label}</span>
                    {active ? (
                      <motion.span
                        layoutId="sidebar-active-dot"
                        className="absolute right-3 h-1.5 w-1.5 rounded-full bg-emerald"
                      />
                    ) : null}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
        <div className="border-t border-line p-5">
          <div className="flex items-center justify-between gap-2">
            <Badge tone={mode === "demo" ? "amber" : "emerald"} dot>
              {mode === "demo" ? "DEMO" : "LIVE"}
            </Badge>
            <span className="flex items-center gap-1.5 text-[11px] text-subtle">
              <Dot tone={pilotOnline ? "emerald" : "amber"} pulse={pilotOnline} />
              {pilotOnline ? "pilot online" : "pilot offline"}
            </span>
          </div>
          <p className="mt-3 text-[11px] leading-4 text-subtle">
            Open Connection to change endpoint or key
          </p>
          <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.08em] text-faint">
            {mode === "demo" ? "simulated feed" : `socket ${socketStatus}`}
          </p>
        </div>
      </aside>

      <div className="min-h-dvh lg:pl-[248px]">
        <header className="sticky top-0 z-40 border-b border-line bg-canvas">
          <div
            className="mx-auto flex h-16 w-full max-w-[1440px] items-center justify-between gap-3 px-4 sm:px-6 lg:px-8"
            style={{ paddingTop: "env(safe-area-inset-top, 0px)" }}
          >
            <div className="flex min-w-0 items-center gap-3">
              <Link href="/" aria-label="AlgoRE overview" className="lg:hidden">
                <span className="flex items-center gap-2">
                  <LogoMark className="h-8 w-8" />
                  <span className="text-[12px] font-semibold tracking-[0.2em] text-ink">ALGORE</span>
                </span>
              </Link>
              <p className="hidden items-center gap-2 text-[11px] font-medium uppercase tracking-[0.16em] text-subtle lg:flex">
                <span>AlgoRE</span>
                <span className="text-faint">/</span>
                <span className="text-muted">{pageLabel(pathname)}</span>
              </p>
            </div>
            <div className="flex items-center gap-3">
              <Badge tone={mode === "demo" ? "amber" : "emerald"} dot>
                {mode === "demo" ? "DEMO" : "LIVE"}
              </Badge>
              <span className="flex items-center gap-1.5 text-[11px] text-subtle">
                <Dot tone={pilotOnline ? "emerald" : "amber"} pulse={pilotOnline} />
                <span className="hidden sm:inline">
                  {pilotOnline ? "pilot online" : "pilot offline"}
                </span>
              </span>
              <ConnectionSettings />
            </div>
          </div>
          {mode === "demo" ? (
            <div className="border-t border-line/60 px-4 py-1.5 sm:px-6 lg:hidden">
              <p className="text-[11px] leading-4 text-subtle">Open Connection to change endpoint or key</p>
            </div>
          ) : null}
        </header>

        <main
          id="main"
          className="mx-auto w-full max-w-[1280px] px-4 pb-[calc(96px+env(safe-area-inset-bottom,0px))] pt-5 sm:px-6 sm:pt-6 lg:px-8 lg:pb-10 lg:pt-7"
        >
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={pathname}
              initial={{ opacity: 0, y: 5 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -3 }}
              transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
            >
              {children}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>

      <nav
        aria-label="Primary mobile"
        className="fixed inset-x-0 bottom-0 z-50 border-t border-line bg-canvas lg:hidden"
        style={{ paddingBottom: "env(safe-area-inset-bottom, 0px)" }}
      >
        <div className="mx-auto grid max-w-[560px] grid-cols-5">
          {NAV_ITEMS.map((item) => {
            const active = isActive(pathname, item.href);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "relative flex min-h-[62px] flex-col items-center justify-center gap-1 px-1 transition",
                  active ? "text-ink" : "text-subtle hover:text-muted",
                )}
              >
                {active ? (
                  <motion.span
                    layoutId="mobile-active-bar"
                    className="absolute left-1/2 top-0 h-[2px] w-8 -translate-x-1/2 rounded-full bg-emerald"
                  />
                ) : null}
                <Icon
                  className={cn("h-[19px] w-[19px]", active ? "text-emerald" : "text-subtle")}
                  strokeWidth={1.9}
                />
                <span className="text-[11px] font-medium leading-none">{item.label}</span>
              </Link>
            );
          })}
        </div>
      </nav>
    </>
  );
}
