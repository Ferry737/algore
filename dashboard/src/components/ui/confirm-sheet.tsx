"use client";

import { useEffect, useId, useRef } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle } from "lucide-react";
import { Button } from "./button";

export function ConfirmSheet({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel = "Cancel",
  tone = "amber",
  onConfirm,
  onClose,
}: {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  cancelLabel?: string;
  tone?: "amber" | "rose" | "emerald";
  onConfirm: () => void;
  onClose: () => void;
}) {
  const titleId = useId();
  const descriptionId = useId();
  const confirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const timer = setTimeout(() => confirmRef.current?.focus(), 80);
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
      clearTimeout(timer);
    };
  }, [open, onClose]);

  const iconClass =
    tone === "amber"
      ? "bg-amber/10 text-amber"
      : tone === "rose"
        ? "bg-rose/10 text-rose"
        : "bg-emerald/10 text-emerald";

  return (
    <AnimatePresence>
      {open ? (
        <div className="fixed inset-0 z-[100] flex items-end justify-center sm:items-center">
          <motion.button
            type="button"
            aria-label="Close confirmation"
            onClick={onClose}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="absolute inset-0 cursor-default bg-black/70"
          />
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            aria-describedby={descriptionId}
            initial={{ opacity: 0, y: 28, scale: 0.99 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 18, scale: 0.99 }}
            transition={{ type: "spring", stiffness: 360, damping: 32 }}
            className="relative w-full max-w-[520px] rounded-t-3xl border border-line-strong bg-panel p-5 pb-[calc(20px+env(safe-area-inset-bottom,0px))] sm:rounded-3xl sm:border sm:p-6"
          >
            <div className="mx-auto mb-4 h-1 w-9 rounded-full bg-white/15 sm:hidden" />
            <div className="flex items-start gap-3">
              <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${iconClass}`}>
                <AlertTriangle className="h-5 w-5" strokeWidth={1.8} />
              </span>
              <div className="min-w-0">
                <h2 id={titleId} className="text-lg font-medium tracking-[-0.02em] text-ink">
                  {title}
                </h2>
                <p id={descriptionId} className="mt-1.5 text-[13px] leading-5 text-muted">
                  {description}
                </p>
              </div>
            </div>
            <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <Button variant="ghost" onClick={onClose} className="sm:min-w-[100px]">
                {cancelLabel}
              </Button>
              <Button
                ref={confirmRef}
                variant={tone === "rose" ? "rose" : tone === "emerald" ? "primary" : "amber"}
                onClick={onConfirm}
                className="sm:min-w-[140px]"
              >
                {confirmLabel}
              </Button>
            </div>
          </motion.div>
        </div>
      ) : null}
    </AnimatePresence>
  );
}
