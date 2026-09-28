import type { ReviewStatus } from "@/api/types";

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

export const STAGE_COLOR: Record<string, string> = {
  I: "#2dd4bf",
  II: "#fbbf24",
  III: "#fb923c",
  IV: "#ef4444",
};

export const stageColor = (stage?: string | null) => (stage ? STAGE_COLOR[stage] ?? "#7f93b0" : "#7f93b0");

export const RISK_TONE: Record<string, Tone> = { low: "ok", moderate: "review", high: "critical" };

export const PROGRESSION_TONE: Record<string, Tone> = {
  stable: "ok",
  improved: "brand",
  progressing: "review",
  "rapidly progressing": "critical",
  "unreliable comparison": "neutral",
};

export const FLAG_LABEL: Record<string, string> = {
  low_confidence: "Low confidence",
  low_attention_validity: "Attention outside periodontal area",
  heuristic_landmarks: "Estimated landmarks",
};

export const REASON_LABEL: Record<string, string> = {
  demo_mode: "Demo mode",
  uncalibrated: "Uncertainty not calibrated",
  ambiguous_stage: "Ambiguous stage",
  low_quality: "Borderline image quality",
  out_of_distribution: "Unusual image",
  low_attention_validity: "Attention outside ROI",
  heuristic_landmarks: "Estimated landmarks",
  low_confidence: "Low confidence",
};
