import clsx from "clsx";
import { Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes, HTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";
import { forwardRef } from "react";
import type { Tone } from "@/lib/format";

type ButtonVariant = "primary" | "ghost" | "outline" | "danger" | "subtle";

const BUTTON: Record<ButtonVariant, string> = {
  primary:
    "bg-gradient-to-r from-brand-400 to-teal-400 text-ink-950 font-semibold hover:brightness-110 shadow-glow disabled:shadow-none",
  ghost: "text-mist-300 hover:text-mist-100 hover:bg-white/5",
  outline: "border border-white/12 text-mist-100 hover:border-brand-400/50 hover:bg-brand-400/5",
  danger: "bg-critical-500/90 text-white hover:bg-critical-500",
  subtle: "bg-white/5 text-mist-100 hover:bg-white/10",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: "sm" | "md" | "lg";
  loading?: boolean;
  icon?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", loading, icon, className, children, disabled, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-xl transition disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" && "px-3 py-1.5 text-xs",
        size === "md" && "px-4 py-2 text-sm",
        size === "lg" && "px-6 py-3 text-base",
        BUTTON[variant],
        className,
      )}
      {...rest}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
});

export function Card({ className, children, strong, ...rest }: HTMLAttributes<HTMLDivElement> & { strong?: boolean }) {
  return (
    <div className={clsx(strong ? "glass-strong" : "glass", "p-5", className)} {...rest}>
      {children}
    </div>
  );
}

export function CardTitle({ children, action, icon }: { children: ReactNode; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="mb-4 flex items-center justify-between gap-3">
      <h3 className="flex items-center gap-2 font-display text-base font-semibold text-mist-100">
        {icon && <span className="text-brand-400">{icon}</span>}
        {children}
      </h3>
      {action}
    </div>
  );
}

const TONE: Record<Tone, string> = {
  neutral: "bg-white/5 text-mist-300 border-white/10",
  brand: "bg-brand-400/10 text-brand-300 border-brand-400/25",
  ok: "bg-teal-400/10 text-teal-400 border-teal-400/25",
  review: "bg-review-500/10 text-review-400 border-review-500/30",
  critical: "bg-critical-500/10 text-critical-400 border-critical-500/30",
};

export function Badge({ tone = "neutral", children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-[11px] font-medium",
        TONE[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Dot({ tone = "neutral" }: { tone?: Tone }) {
  const c = { neutral: "bg-mist-500", brand: "bg-brand-400", ok: "bg-teal-400", review: "bg-review-400", critical: "bg-critical-400" }[tone];
  return <span className={clsx("inline-block h-2 w-2 rounded-full", c)} aria-hidden />;
}

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input(
  { className, ...rest },
  ref,
) {
  return <input ref={ref} className={clsx("input", className)} {...rest} />;
});

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function Select(
  { className, children, ...rest },
  ref,
) {
  return (
    <select ref={ref} className={clsx("input appearance-none", className)} {...rest}>
      {children}
    </select>
  );
});

export function Field({ label, hint, error, children, htmlFor }: {
  label: string;
  hint?: string;
  error?: string;
  children: ReactNode;
  htmlFor?: string;
}) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={htmlFor} className="label block">
        {label}
      </label>
      {children}
      {error ? <p className="text-xs text-critical-400">{error}</p> : hint && <p className="text-xs text-mist-500">{hint}</p>}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return (
    <div className={clsx("relative overflow-hidden rounded-lg bg-white/[0.04]", className)} aria-hidden>
      <div className="absolute inset-0 -translate-x-full animate-shimmer bg-gradient-to-r from-transparent via-white/[0.06] to-transparent" />
    </div>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <span role="status" className="inline-flex items-center gap-2 text-sm text-mist-400">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> {label}
    </span>
  );
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className="flex cursor-pointer items-center justify-between gap-3 text-sm text-mist-300">
      <span>{label}</span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={clsx(
          "relative h-5 w-9 rounded-full transition",
          checked ? "bg-brand-400" : "bg-white/15",
        )}
      >
        <span
          className={clsx(
            "absolute top-0.5 h-4 w-4 rounded-full bg-ink-950 transition",
            checked ? "left-[18px]" : "left-0.5",
          )}
        />
      </button>
    </label>
  );
}
