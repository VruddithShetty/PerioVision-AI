import clsx from "clsx";
import { Moon, Sun } from "lucide-react";
import { useTheme } from "@/store/theme";

/** Switches between the light (default) and dark theme; the choice is remembered on this device. */
export function ThemeToggle({ className, withLabel = false }: { className?: string; withLabel?: boolean }) {
  const theme = useTheme((s) => s.theme);
  const toggle = useTheme((s) => s.toggle);
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={`Switch to ${next} mode`}
      title={`Switch to ${next} mode`}
      className={clsx(
        "inline-flex items-center gap-2 rounded-xl border border-white/10 bg-ink-800/70 px-2.5 py-2 text-mist-300 shadow-glass transition hover:border-brand-400/50 hover:text-brand-300",
        className,
      )}
    >
      {theme === "dark" ? <Sun className="h-4 w-4" aria-hidden /> : <Moon className="h-4 w-4" aria-hidden />}
      {withLabel && <span className="text-xs font-medium">{theme === "dark" ? "Light mode" : "Dark mode"}</span>}
    </button>
  );
}
