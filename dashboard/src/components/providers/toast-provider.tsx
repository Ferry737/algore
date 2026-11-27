"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import type { ReactNode } from "react";

export type ToastTone = "emerald" | "amber" | "rose";

export interface ToastInput {
  title: string;
  message?: string;
  tone?: ToastTone;
}

interface ToastItem extends ToastInput {
  id: number;
}

interface ToastContextValue {
  toast: (input: ToastInput) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

let toastId = 0;

const toneStyles: Record<ToastTone, { icon: typeof Info; iconClass: string; bar: string }> = {
  emerald: { icon: CheckCircle2, iconClass: "text-emerald", bar: "bg-emerald" },
  amber: { icon: AlertTriangle, iconClass: "text-amber", bar: "bg-amber" },
  rose: { icon: AlertTriangle, iconClass: "text-rose", bar: "bg-rose" },
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const timers = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());

  const dismiss = useCallback((id: number) => {
    setToasts((items) => items.filter((item) => item.id !== id));
    const timer = timers.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
  }, []);

  const toast = useCallback(
    (input: ToastInput) => {
      const id = ++toastId;
      setToasts((items) => [...items.slice(-2), { ...input, id }]);
      const timer = setTimeout(() => dismiss(id), 4500);
      timers.current.set(id, timer);
    },
    [dismiss],
  );

  useEffect(() => {
    const map = timers.current;
    return () => {
      map.forEach((timer) => clearTimeout(timer));
      map.clear();
    };
  }, []);

  const value = useMemo(() => ({ toast }), [toast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        aria-atomic="false"
        className="pointer-events-none fixed inset-x-3 top-[calc(env(safe-area-inset-top,0px)+12px)] z-[90] flex flex-col items-stretch gap-2 sm:left-auto sm:right-6 sm:w-[360px]"
      >
        <AnimatePresence initial={false}>
          {toasts.map((item) => {
            const tone = toneStyles[item.tone ?? "emerald"];
            const Icon = tone.icon;
            return (
              <motion.div
                key={item.id}
                layout
                initial={{ opacity: 0, y: -12, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -8, scale: 0.98 }}
                transition={{ type: "spring", stiffness: 360, damping: 30 }}
                className="pointer-events-auto relative overflow-hidden rounded-2xl border border-line bg-panel shadow-[0_18px_50px_rgba(0,0,0,0.55)]"
              >
                <span className={`absolute inset-y-0 left-0 w-[3px] ${tone.bar}`} />
                <div className="flex items-start gap-3 p-4 pl-5">
                  <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${tone.iconClass}`} strokeWidth={1.8} />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-ink">{item.title}</p>
                    {item.message ? (
                      <p className="mt-1 text-[13px] leading-5 text-muted">{item.message}</p>
                    ) : null}
                  </div>
                  <button
                    type="button"
                    onClick={() => dismiss(item.id)}
                    aria-label="Dismiss notification"
                    className="-mr-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-subtle transition hover:bg-white/[0.06] hover:text-ink"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const value = useContext(ToastContext);
  if (!value) {
    throw new Error("useToast must be used inside ToastProvider");
  }
  return value;
}
