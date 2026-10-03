export type Role = "admin" | "dentist" | "technician" | "auditor";
export type Mode = "demo" | "live";
export type ReviewStatus = "review_required" | "auto_cleared" | "approved" | "corrected" | "rejected";

export interface Envelope<T> {
  data: T;
  meta: Record<string, unknown>;
  error: { code: number; message: string; details?: unknown } | null;
  mode: Mode;
}

export interface User {
  doctor_id: string;
  name: string;
  email: string;
  role: Role;
  mfa_enabled?: boolean;
  /** true when this role must use MFA and the account has not enrolled yet (server blocks everything else) */
  mfa_enrolment_required?: boolean;
  clinic_name?: string | null;
  permissions?: string[];
  active?: boolean;
  last_login?: string | null;
  locked_until?: string | null;
}

export interface PatientAnalysisRef {
  analysis_id: string;
  visit_date: string;
  mode: Mode;
  review_status: ReviewStatus;
  stage: string | null;
  risk: string | null;
}

export interface Patient {
  patient_id: number;
  pseudo_id: string;
  patient_name: string;
  age?: number | null;
  sex?: string | null;
  contact_number?: string;
  notes?: string;
  smoking_status?: string | null;
  cigarettes_per_day?: number | null;
  diabetic?: boolean | null;
  hba1c?: number | null;
  teeth_lost_perio?: number | null;
  created_date?: string;
  analyses?: PatientAnalysisRef[];
}

export interface Uncertainty {
  interval: [number, number] | null;
  stage_set: string[];
  set_size: number;
  calibrated: boolean;
}

export interface Tooth {
  tooth_id: string;
  tooth_id_source: string;
  bbox: [number, number, number, number];
  confidence: number | null;
  /** null when no model placed the landmarks ("not_measured"): never drawn, never measured */
  cej: [number, number] | null;
  abc: [number, number] | null;
  root_apex: [number, number] | null;
  landmark_source: string;
  measurement_status?: string;
  landmark_confidence?: number | null;
  bone_loss_pct: number | null;
  cej_to_crest_mm: number | null;
  stage: string | null;
  uncertainty: Uncertainty;
  roi: [number, number, number, number] | null;
  roi_attention: number | null;
  flags: Record<string, boolean>;
}

export interface ReviewReason {
  code: string;
  message: string;
  teeth?: string[];
}

export interface Comparison {
  tooth_id: string;
  previous_tooth_id: string;
  match_method: "tooth_number" | "spatial";
  from_date: string;
  to_date: string;
  interval_days: number;
  previous_bone_loss_pct: number;
  current_bone_loss_pct: number;
  delta_pct: number;
  velocity_pct_per_year: number | null;
  velocity_pct_per_month: number | null;
  label: string;
  raw_label: string | null;
  reliable: boolean;
  /** true only when |delta| exceeds twice the calibrated measurement error */
  change_detectable?: boolean;
  measurement_error_pct?: number | null;
  reliability_reasons: string[];
}

export interface RiskResult {
  /** "insufficient_data": required inputs missing, so no score at all (never a default) */
  status?: "ok" | "insufficient_data" | "unavailable";
  /** which validated NHANES model was used (HbA1c known or not) */
  variant?: "with_hba1c" | "without_hba1c";
  validation?: { source: string; outcome: string; test_n: number; roc_auc: number; brier: number };
  category: "low" | "moderate" | "high" | null;
  probability: number | null;
  top_factors: { factor: string; contribution: number; text: string }[];
  missing_inputs: string[];
  model_type: string;
  model_version: string;
  disclaimer: string;
}

export interface QualityResult {
  verdict: "pass" | "warn" | "reject";
  reasons: { level: string; message: string }[];
  metrics: Record<string, number>;
}

export interface ModelStatus {
  name: string;
  file: string;
  purpose: string;
  /** optional models (e.g. the panoramic whole-film models) may be absent without the system being unsafe */
  optional?: boolean;
  present: boolean;
  signature_valid: boolean;
  loaded: boolean;
  sha256: string | null;
  reason: string | null;
}

export interface ReviewDecision {
  status: ReviewStatus;
  reviewer_id: string;
  reviewer_name: string;
  reviewer_role: Role;
  at: string;
  comment: string | null;
  corrections: { tooth_id: string; bone_loss_pct: number | null; stage: string | null; note: string | null }[];
}

export interface Analysis {
  analysis_id: string;
  patient_id: number;
  pseudo_id: string;
  visit_date: string;
  mode: Mode;
  /** "synthetic_demo" for seeded demo records; live analyses are never tagged this way */
  source?: string;
  created: string;
  created_by: string;
  image_size: [number, number];
  pixel_spacing_mm: number | null;
  quality: QualityResult;
  adversarial: { is_suspicious: boolean; triggers: string[]; metrics: Record<string, number> };
  ood: { is_ood: boolean; reasons: string[] };
  explainability: { gradcam_available: boolean; method: string | null; model?: string | null };
  teeth: Tooth[];
  summary: {
    teeth_detected: number;
    teeth_measured?: number;
    mean_bone_loss_pct: number | null;
    max_bone_loss_pct: number | null;
    affected_teeth: number;
    stage: string | null;
    grade: { grade: string | null; basis: string | null; reasons: string[] };
    max_velocity_pct_per_year: number | null;
  };
  risk: RiskResult;
  alignment: { confidence: number; status: string; reason?: string | null } | null;
  /** Whole-film panoramic estimate (patient level); only on panoramic films with the optional models installed. */
  panoramic_assessment?: PanoramicAssessment | null;
  progression: Comparison[];
  previous_analysis_id: string | null;
  calibration: { calibrated: boolean; q: number | null; coverage: number };
  models: ModelStatus[];
  review: {
    status: ReviewStatus;
    label: string;
    reasons: ReviewReason[];
    history: ReviewDecision[];
    decision?: ReviewDecision;
  };
  images: Partial<Record<"radiograph" | "annotated" | "gradcam", string>>;
  patient?: { patient_id: number; pseudo_id: string; name: string; age: number | null };
}

export interface AnalysisListItem {
  analysis_id: string;
  pseudo_id: string;
  patient_id: number;
  visit_date: string;
  mode: Mode;
  created: string;
  review_status: ReviewStatus;
  stage: string | null;
  risk: string | null;
}

export interface QueueItem {
  analysis_id: string;
  patient_id: number;
  pseudo_id: string;
  visit_date: string;
  created: string;
  mode: Mode;
  reasons: ReviewReason[];
  stage: string | null;
  teeth: number;
}

export interface Progression {
  visits: { analysis_id: string; visit_date: string; review_status: ReviewStatus }[];
  series: Record<string, { date: string; analysis_id: string; bone_loss_pct: number; stage: string | null }[]>;
  comparisons: Comparison[];
  latest: Comparison[];
  summary: {
    visits: number;
    max_reliable_velocity_pct_per_year: number | null;
    unreliable_comparisons: number;
    labels: Record<string, number>;
  };
}

export interface ReportSummary {
  report_id: string;
  analysis_id: string;
  patient_id: number;
  pseudo_id: string;
  created: string;
  sha256: string;
  signature_algorithm: string;
  key_fingerprint: string | null;
  mode: Mode;
  size_bytes: number;
}

export interface VerifyResult {
  valid: boolean;
  report_id?: string;
  created?: string;
  sha256?: string;
  signature_valid?: boolean;
  hash_matches?: boolean;
  key_fingerprint?: string | null;
  mode?: Mode;
  reason: string | null;
}

export interface AuditEntry {
  seq: number;
  timestamp: string;
  actor: string;
  action: string;
  outcome: string;
  resource: string | null;
  details: Record<string, unknown>;
  prev_hash: string;
  entry_hash: string;
}

export interface ChainVerification {
  chain_intact: boolean;
  first_tampered_seq: number | null;
  reason: string | null;
  entries_verified: number;
  current_root: string;
  anchors_checked: number;
  anchors: { count: number; timestamp: string; anchor_genuine: boolean; root_matches: boolean }[];
  latest_anchor: { count: number; root: string; timestamp: string } | null;
}

export interface SystemStatus {
  mode: Mode;
  database: boolean;
  models: { name: string; present: boolean; signature_valid: boolean; loaded: boolean; reason: string | null }[];
  models_verified: boolean;
  audit_chain_intact: boolean;
  audit_entries: number;
  calibrated: boolean;
}

export interface Dashboard {
  role: Role;
  system: SystemStatus;
  patients?: number;
  analyses_total?: number;
  analyses_today?: number;
  flagged_for_review?: number;
  stage_distribution?: Record<string, number>;
  risk_distribution?: Record<string, number>;
  recent?: {
    analysis_id: string;
    pseudo_id: string;
    visit_date: string;
    created: string;
    review_status: ReviewStatus;
    mode: Mode;
  }[];
  recent_security_events?: AuditEntry[];
}

export interface LabStep {
  label: string;
  passed: boolean;
  detail: string;
}

export interface LabScenario {
  id: string;
  title: string;
  defence: string;
}

export interface LabResult extends LabScenario {
  steps: LabStep[];
  defended: boolean;
  error: string | null;
  duration_ms: number;
  ran_at: string;
}

export interface SessionInfo {
  sid: string;
  user_id: string;
  created: string;
  last_seen: string;
  current?: boolean;
}

export interface ModelTrust {
  calibration: {
    calibrated: boolean;
    target_coverage: number;
    message?: string;
    q_current?: number | null;
    adaptive?: boolean;
    levels?: Record<string, { q_from_half: number | null; empirical_coverage_other_half: number | null; mean_half_width_pct?: number | null }>;
    reliability_bins?: { bin: [number, number]; n: number; mean_predicted: number; mean_reference: number }[];
    source?: string;
    n_scores?: number;
    mean_absolute_error_pct?: number;
  };
  analyses_total: number;
  auto_flagged: number;
  flagged_share: number | null;
  flag_reasons: Record<string, number>;
  models: ModelStatus[];
  risk_model: { type: string; version: string };
}

export interface AdminConfig {
  thresholds: Record<string, Record<string, unknown>>;
  thresholds_file: string;
  encryption: { algorithm: string; active_key_id: string; key_ids: string[] };
  signing: { algorithm: string; public_key_fingerprint: string | null; private_key_available: boolean };
  mode: Mode;
}

export interface UploadResult {
  upload_id: string;
  kind: string;
  width: number;
  height: number;
  pixel_spacing_mm: number | null;
  study_date: string | null;
  removed_metadata: string[];
  quality: QualityResult;
}

// ---------- chairside clinical tools ----------
export interface ToothChart {
  pd: number[];
  rec: number[];
  bop: boolean[];
  plaque: boolean[];
  mobility: number;
  furcation: number;
  missing: boolean;
}

export interface ToothChartSummary {
  missing: boolean;
  cal?: number[];
  max_pd?: number;
  max_cal?: number;
  interdental_cal?: number;
  bop_sites?: number;
  deep_pockets?: number;
  mobility?: number;
  furcation?: number;
  clinical_stage?: string | null;
}

export interface ChartSummary {
  teeth: Record<string, ToothChartSummary>;
  teeth_present: number;
  teeth_missing: number;
  bop_pct: number | null;
  plaque_pct: number | null;
  sites_pd_4_plus: number;
  sites_pd_6_plus: number;
  mean_cal: number | null;
  clinical_stage: string | null;
  gingival_status: string;
}

export interface ConcordanceRow {
  tooth_id: string;
  clinical_stage: string | null;
  radiographic_stage: string | null;
  interdental_cal_mm: number;
  bone_loss_pct: number | null;
  status: "agree" | "clinical worse" | "radiograph worse";
  hint: string | null;
}

export interface PerioChart {
  chart_id: string;
  patient_id: number;
  exam_date: string;
  created: string;
  teeth: Record<string, ToothChart>;
  notes: string | null;
  examiner_name?: string | null;
  summary: ChartSummary;
  concordance: ConcordanceRow[];
}

export interface CarePlan {
  stage: string | null;
  radiographic_stage: string | null;
  clinical_stage: string | null;
  grade: { grade: string | null; basis: string | null; reasons: string[] };
  risk: string | null;
  recall: { months: number; reasons: string[] };
  last_visit: string | null;
  next_recall_due: string | null;
  steps: { step: number; title: string; items: string[]; indicated: boolean }[];
  prognosis: { tooth_id: string; category: "favourable" | "questionable" | "unfavourable" | "hopeless" | "not assessable"; reasons: string[] }[];
  referral_suggested: boolean;
  chart_summary: ChartSummary | null;
  disclaimer: string;
  patient: Pick<Patient, "patient_id" | "pseudo_id" | "patient_name" | "age" | "sex" | "smoking_status" | "cigarettes_per_day" | "diabetic" | "hba1c" | "teeth_lost_perio">;
  analysis_id: string | null;
  teeth: { tooth_id: string; bone_loss_pct: number | null; stage: string | null }[];
  progression: Comparison[];
}

export interface RecallRow {
  patient_id: number;
  pseudo_id: string;
  patient_name: string;
  stage: string | null;
  grade: string | null;
  risk: string | null;
  interval_months: number;
  last_visit: string | null;
  next_due: string | null;
  days_until_due: number | null;
  status: "overdue" | "due soon" | "scheduled";
  referral_suggested: boolean;
}

export interface ModelMetrics {
  tooth_detector: { dataset: string; model: string; test_precision: number; test_recall: number; test_mAP50: number; test_mAP50_95: number } | null;
  landmarks: {
    dataset: string;
    model: string;
    tooth_recall: number | null;
    test: { n_teeth: number; bone_loss_MAE_pct_points: number; within_10_points: number; stage_agreement: number } | null;
  } | null;
  conformal: { source: string; image_type: string | null; levels: Record<string, { q_from_half: number | null; empirical_coverage_other_half: number | null; mean_half_width_pct?: number | null }> } | null;
}

export interface PanoramicAssessment {
  level: string;
  note: string;
  screen?: Record<"maxilla" | "mandible", {
    probability: number; bone_loss_suggested: boolean; threshold: number;
    test: { test_auc: number; test_sensitivity: number; test_specificity: number };
  }>;
  screen_validation?: { dataset: string; test_films: number };
  worst_tooth?: {
    bone_loss_pct: number; stage: string | null; interval_90: [number, number]; stage_set: string[]; dataset: string;
    test: { test_MAE: number; test_stage_agreement: number; test_interval_coverage: number; test_films: number };
  };
}
