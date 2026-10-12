import type { ReviewStatus } from "@/api/types";
import type { Theme } from "@/store/theme";

export const fmtPct = (v: number | null | undefined, digits = 1) =>
  v === null || v === undefined ? "–" : `${v.toFixed(digits)}%`;

export const fmtNum = (v: number | null | undefined, digits = 2) =>
  v === null || v === undefined ? "–" : v.toFixed(digits);

export const fmtDate = (iso?: string | null) => {
  if (!iso) return "–";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
};

export const fmtDateTime = (iso?: string | null) => {
  if (!iso) return "–";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
};

export const shortHash = (h?: string | null, n = 10) => (h ? `${h.slice(0, n)}…${h.slice(-4)}` : "–");

export const REVIEW_LABEL: Record<ReviewStatus, string> = {
  review_required: "Needs review",
  auto_cleared: "No flags",
  approved: "Approved",
  corrected: "Corrected",
  rejected: "Rejected",
};

export type Tone = "neutral" | "brand" | "ok" | "review" | "critical";

export const REVIEW_TONE: Record<ReviewStatus, Tone> = {
  review_required: "review",
  auto_cleared: "brand",
  approved: "ok",
  corrected: "ok",
  rejected: "critical",
};

/** Stage colours. Dark: bright tones (also used for marks drawn on an X-ray, which is always dark). Light: deeper
 *  tones that stay readable on white. */
export const STAGE_COLOR_DARK: Record<string, string> = { I: "#2dd4bf", II: "#fbbf24", III: "#fb923c", IV: "#ef4444" };
export const STAGE_COLOR_LIGHT: Record<string, string> = { I: "#0d9488", II: "#d97706", III: "#ea580c", IV: "#dc2626" };
export const STAGE_COLOR = STAGE_COLOR_DARK;

/** Colour of a stage. Without a theme: a CSS variable (`var(--stage-ii)`) that follows the light / dark toggle
 *  instantly, for style props. With a theme: a fixed hex colour, for SVG attributes, charts and marks drawn on a
 *  radiograph (pass "dark" there: an X-ray is always dark). Mix in transparency with `tint()`, not by appending hex. */
export const stageColor = (stage?: string | null, theme?: Theme) => {
  if (!theme) return `var(--stage-${stage && STAGE_COLOR_DARK[stage] ? stage.toLowerCase() : "none"})`;
  const table = theme === "dark" ? STAGE_COLOR_DARK : STAGE_COLOR_LIGHT;
  const muted = theme === "dark" ? "#7f93b0" : "#6b839e";
  return stage ? table[stage] ?? muted : muted;
};

/** A colour at a given opacity (0-1); works with CSS variables as well as hex colours. */
export const tint = (color: string, opacity: number) =>
  `color-mix(in srgb, ${color} ${Math.round(opacity * 100)}%, transparent)`;

export const RISK_TONE: Record<string, Tone> = { low: "ok", moderate: "review", high: "critical" };

export const PROGRESSION_TONE: Record<string, Tone> = {
  stable: "ok",
  improved: "brand",
  progressing: "review",
  "rapidly progressing": "critical",
  "no change beyond measurement error": "neutral",
  "unreliable comparison": "neutral",
};

export const FLAG_LABEL: Record<string, string> = {
  low_confidence: "Low confidence",
  low_attention_validity: "Attention outside periodontal area",
  not_measured: "Not measured (no model landmarks)",
};

export const REASON_LABEL: Record<string, string> = {
  demo_mode: "Demo mode",
  uncalibrated: "Uncertainty not calibrated",
  ambiguous_stage: "Ambiguous stage",
  low_quality: "Borderline image quality",
  out_of_distribution: "Unusual image",
  low_attention_validity: "Attention outside ROI",
  not_measured: "Teeth not measured",
  not_validated_image_type: "Bone loss not validated on this X-ray type",
  landmarks_not_validated: "Landmarks not validated for this X-ray type",
  low_confidence: "Low confidence",
};
