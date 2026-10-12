import type { Theme } from "@/store/theme";
import { useTheme } from "@/store/theme";

/**
 * Concrete colours for things that cannot read CSS variables (SVG presentation attributes in Recharts, canvas,
 * three.js). Light: deeper, saturated tones that stay readable on white. Dark: the original bright tones.
 */
export interface ChartColors {
  axis: string;
  grid: string;
  track: string;
  needle: string;
  muted: string;
  tooltip: { background: string; border: string; label: string; item: string; cursor: string };
  series: string[];
  sky: string;
  teal: string;
  amber: string;
  orange: string;
  red: string;
}

const LIGHT: ChartColors = {
  axis: "#6b839e",
  grid: "rgba(14,66,120,0.09)",
  track: "rgba(14,66,120,0.10)",
  needle: "#0b2440",
  muted: "#6b839e",
  tooltip: { background: "#ffffff", border: "rgba(14,66,120,0.16)", label: "#2c4a6b", item: "#0b2440",
             cursor: "rgba(2,132,199,0.07)" },
  series: ["#0284c7", "#0d9488", "#d97706", "#ea580c", "#dc2626", "#7c3aed", "#2563eb", "#db2777"],
  sky: "#0284c7",
  teal: "#0d9488",
  amber: "#d97706",
  orange: "#ea580c",
  red: "#dc2626",
};

const DARK: ChartColors = {
  axis: "#5b6f8c",
  grid: "rgba(255,255,255,0.05)",
  track: "rgba(255,255,255,0.07)",
  needle: "#e6f1ff",
  muted: "#7f93b0",
  tooltip: { background: "#0a1628", border: "rgba(255,255,255,0.08)", label: "#a9bcd6", item: "#e6f1ff",
             cursor: "rgba(34,211,238,0.06)" },
  series: ["#22d3ee", "#2dd4bf", "#fbbf24", "#fb923c", "#ef4444", "#a78bfa", "#60a5fa", "#f472b6"],
  sky: "#22d3ee",
  teal: "#2dd4bf",
  amber: "#fbbf24",
  orange: "#fb923c",
  red: "#ef4444",
};

export const chartColors = (theme: Theme): ChartColors => (theme === "dark" ? DARK : LIGHT);

/** Chart colours for the current theme; the component re-renders when the theme changes. */
export function useChartColors(): ChartColors {
  return chartColors(useTheme((s) => s.theme));
}
