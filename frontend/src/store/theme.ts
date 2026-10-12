import { create } from "zustand";

export type Theme = "light" | "dark";

const KEY = "pv-theme";

/** The saved choice, or light (the default). Storage can be unavailable (private windows): fall back quietly. */
function initialTheme(): Theme {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    /* storage blocked */
  }
  return "light";
}

function apply(theme: Theme) {
  const root = document.documentElement;
  root.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme === "dark" ? "#03070f" : "#f4f9ff");
}

interface ThemeState {
  theme: Theme;
  setTheme: (t: Theme) => void;
  toggle: () => void;
}

export const useTheme = create<ThemeState>((set, get) => ({
  theme: initialTheme(),
  setTheme: (theme) => {
    apply(theme);
    try {
      localStorage.setItem(KEY, theme);
    } catch {
      /* storage blocked: the choice lasts for this visit only */
    }
    set({ theme });
  },
  toggle: () => get().setTheme(get().theme === "dark" ? "light" : "dark"),
}));

apply(useTheme.getState().theme);
