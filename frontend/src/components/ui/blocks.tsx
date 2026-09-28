import clsx from "clsx";
import { AlertTriangle, Inbox, X } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, type ReactNode } from "react";
import { ApiError } from "@/api/client";
import { Button, Skeleton } from "./primitives";

export function PageHeader({ title, subtitle, actions, eyebrow }: {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  eyebrow?: string;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        {eyebrow && <p className="label mb-1 text-brand-300">{eyebrow}</p>}
        <h1 className="text-2xl font-bold text-mist-100 md:text-3xl">{title}</h1>
        {subtitle && <p className="mt-1 max-w-2xl text-sm text-mist-400">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Stat({ label, value, hint, icon, tone = "brand" }: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  icon?: ReactNode;
  tone?: "brand" | "review" | "ok" | "critical";
}) {
  const ring = { brand: "text-brand-300", review: "text-review-400", ok: "text-teal-400", critical: "text-critical-400" }[tone];
  return (
    <div className="glass relative overflow-hidden p-5">
      <div className="flex items-start justify-between">
        <p className="label">{label}</p>
        {icon && <span className={clsx("opacity-80", ring)}>{icon}</span>}
      </div>
      <p className="mt-3 font-display text-3xl font-bold text-mist-100">{value}</p>
      {hint && <p className="mt-1 text-xs text-mist-500">{hint}</p>}
      <div className={clsx("pointer-events-none absolute -bottom-10 -right-10 h-28 w-28 rounded-full opacity-20 blur-2xl", {
        "bg-brand-400": tone === "brand",
        "bg-review-500": tone === "review",
        "bg-teal-400": tone === "ok",
        "bg-critical-500": tone === "critical",
      })} />
    </div>
  );
}

export function EmptyState({ title, body, action, icon }: { title: string; body?: string; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-white/10 px-6 py-12 text-center">
      <div className="mb-3 rounded-full bg-white/5 p-3 text-mist-400">{icon ?? <Inbox className="h-6 w-6" />}</div>
      <p className="font-display font-semibold text-mist-100">{title}</p>
      {body && <p className="mt-1 max-w-sm text-sm text-mist-400">{body}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  const status = error instanceof ApiError ? error.status : 0;
  const message = error instanceof Error ? error.message : "Something went wrong.";
  return (
    <div role="alert" className="flex items-start gap-3 rounded-2xl border border-critical-500/30 bg-critical-500/[0.06] p-4 text-sm">
      <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-critical-400" />
      <div className="flex-1">
        <p className="font-medium text-critical-400">{status === 403 ? "You don't have access to this." : "Could not load this."}</p>
        <p className="mt-0.5 text-mist-300">{message}</p>
      </div>
      {retry && (
        <Button size="sm" variant="outline" onClick={retry}>
          Retry
        </Button>
      )}
    </div>
  );
}

export function LoadingRows({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-11 w-full" />
      ))}
    </div>
  );
}

export function Table({ head, children, className }: { head: ReactNode[]; children: ReactNode; className?: string }) {
  return (
    <div className={clsx("overflow-x-auto rounded-xl border border-white/[0.06]", className)}>
      <table className="w-full min-w-[640px] text-left text-sm">
        <thead className="bg-white/[0.03] text-mist-400">
          <tr>
            {head.map((h, i) => (
              <th key={i} scope="col" className="px-4 py-3 text-[11px] font-semibold uppercase tracking-wider">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-white/[0.05]">{children}</tbody>
      </table>
    </div>
  );
}

export function Tabs<T extends string>({ value, onChange, items }: {
  value: T;
  onChange: (v: T) => void;
  items: { value: T; label: string }[];
}) {
  return (
    <div role="tablist" className="inline-flex rounded-xl border border-white/10 bg-ink-900/60 p-1">
      {items.map((it) => (
        <button
          key={it.value}
          role="tab"
          aria-selected={value === it.value}
          onClick={() => onChange(it.value)}
          className={clsx(
            "rounded-lg px-3 py-1.5 text-xs font-medium transition",
            value === it.value ? "bg-brand-400/15 text-brand-300" : "text-mist-400 hover:text-mist-100",
          )}
        >
          {it.label}
        </button>
      ))}
    </div>
  );
}

function useEscape(open: boolean, onClose: () => void) {
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);
}

export function Drawer({ open, onClose, title, children, width = "max-w-xl" }: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  width?: string;
}) {
  useEscape(open, onClose);
  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label={title}>
          <motion.div
            className="absolute inset-0 bg-ink-950/70 backdrop-blur-sm"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />
          <motion.aside
            className={clsx("glass-strong absolute right-0 top-0 flex h-full w-full flex-col rounded-none rounded-l-2xl", width)}
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", damping: 30, stiffness: 280 }}
          >
            <div className="flex items-center justify-between border-b border-white/[0.06] px-6 py-4">
              <h2 className="font-display text-lg font-semibold">{title}</h2>
              <button onClick={onClose} className="rounded-lg p-1.5 text-mist-400 hover:bg-white/5" aria-label="Close">
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-6">{children}</div>
          </motion.aside>
        </div>
      )}
    </AnimatePresence>
  );
}

export function Modal({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: ReactNode }) {
  useEscape(open, onClose);
  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label={title}>
          <motion.div className="absolute inset-0 bg-ink-950/70 backdrop-blur-sm" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} />
          <motion.div
            className="glass-strong relative w-full max-w-lg p-6"
            initial={{ opacity: 0, y: 16, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 16, scale: 0.98 }}
          >
            <div className="mb-4 flex items-center justify-between">
              <h2 className="font-display text-lg font-semibold">{title}</h2>
              <button onClick={onClose} className="rounded-lg p-1.5 text-mist-400 hover:bg-white/5" aria-label="Close">
                <X className="h-5 w-5" />
              </button>
            </div>
            {children}
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
