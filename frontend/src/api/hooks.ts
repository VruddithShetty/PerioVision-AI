import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type {
  AdminConfig,
  Analysis,
  AnalysisListItem,
  AuditEntry,
  CarePlan,
  ChainVerification,
  Dashboard,
  LabResult,
  LabScenario,
  ModelStatus,
  ModelTrust,
  Patient,
  PerioChart,
  Progression,
  QueueItem,
  RecallRow,
  ReportSummary,
  SessionInfo,
  SystemStatus,
  ToothChart,
  UploadResult,
  User,
  VerifyResult,
} from "./types";

const get = <T,>(path: string) => api<T>(path).then((r) => r.data);

export const useDashboard = () => useQuery({ queryKey: ["dashboard"], queryFn: () => get<Dashboard>("/api/dashboard") });
export const useSystemStatus = () =>
  useQuery({ queryKey: ["system"], queryFn: () => get<SystemStatus>("/api/system/status"), refetchInterval: 30_000 });

export const usePatients = (q: string) =>
  useQuery({
    queryKey: ["patients", q],
    queryFn: () => get<Patient[]>(`/api/patients${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  });
export const usePatient = (id?: number | string) =>
  useQuery({ queryKey: ["patient", id], queryFn: () => get<Patient>(`/api/patients/${id}`), enabled: !!id });

export function useSavePatient() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id?: number; body: Record<string, unknown> }) =>
      api<Patient>(id ? `/api/patients/${id}` : "/api/patients", { method: id ? "PATCH" : "POST", body }).then(
        (r) => r.data,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["patients"] });
      qc.invalidateQueries({ queryKey: ["patient"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export const useAnalyses = (limit = 20) =>
  useQuery({ queryKey: ["analyses", limit], queryFn: () => get<AnalysisListItem[]>(`/api/analyses?limit=${limit}`) });
export const useAnalysis = (id?: string) =>
  useQuery({ queryKey: ["analysis", id], queryFn: () => get<Analysis>(`/api/analyses/${id}`), enabled: !!id });

export function useUpload() {
  return useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("image", file);
      return api<UploadResult>("/api/radiographs", { form, method: "POST" }).then((r) => r.data);
    },
  });
}

export function useRunAnalysis() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { upload_id: string; patient_id: number; visit_date?: string }) =>
      api<Analysis>("/api/analyses", { body }).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["analyses"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      qc.invalidateQueries({ queryKey: ["queue"] });
      qc.invalidateQueries({ queryKey: ["patient"] });
    },
  });
}

export const useProgression = (patientId?: number | string) =>
  useQuery({
    queryKey: ["progression", patientId],
    queryFn: () => get<Progression>(`/api/patients/${patientId}/progression`),
    enabled: !!patientId,
  });

export const useReviewQueue = () => useQuery({ queryKey: ["queue"], queryFn: () => get<QueueItem[]>("/api/review/queue") });

export function useSignOff() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      api(`/api/review/${id}`, { body }).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["queue"] });
      qc.invalidateQueries({ queryKey: ["analysis"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export const useReports = () => useQuery({ queryKey: ["reports"], queryFn: () => get<ReportSummary[]>("/api/reports") });
export function useCreateReport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (analysis_id: string) => api<ReportSummary>("/api/reports", { body: { analysis_id } }).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["reports"] }),
  });
}
export const verifyReportById = (id: string) =>
  api<VerifyResult>(`/api/reports/verify/${encodeURIComponent(id)}`, { auth: false }).then((r) => r.data);
export function verifyReportFile(file: File) {
  const form = new FormData();
  form.append("file", file);
  return api<VerifyResult>("/api/reports/verify", { form, method: "POST", auth: false }).then((r) => r.data);
}

export const useAuditLogs = (action: string, limit = 100) =>
  useQuery({
    queryKey: ["audit", action, limit],
    queryFn: () => get<AuditEntry[]>(`/api/audit/logs?limit=${limit}${action ? `&action=${encodeURIComponent(action)}` : ""}`),
    refetchInterval: 15_000,
  });
export function useVerifyChain() {
  return useMutation({ mutationFn: () => get<ChainVerification>("/api/audit/verify") });
}
export function useAnchor() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api("/api/audit/anchor", { method: "POST" }).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["audit"] }),
  });
}

export const useRbacMatrix = () =>
  useQuery({
    queryKey: ["rbac"],
    queryFn: () => get<{ roles: string[]; matrix: Record<string, Record<string, boolean>> }>("/api/security/rbac-matrix"),
  });
export const useAllSessions = (enabled: boolean) =>
  useQuery({ queryKey: ["sessions", "all"], queryFn: () => get<SessionInfo[]>("/api/security/sessions"), enabled });
export const useMySessions = () =>
  useQuery({ queryKey: ["sessions", "me"], queryFn: () => get<SessionInfo[]>("/api/auth/sessions") });

export const useModelStatus = () =>
  useQuery({
    queryKey: ["models"],
    queryFn: () => get<{ models: ModelStatus[]; public_key_fingerprint: string | null }>("/api/models/status"),
  });
export const useModelTrust = () => useQuery({ queryKey: ["trust"], queryFn: () => get<ModelTrust>("/api/models/trust") });

export const useLabScenarios = () =>
  useQuery({ queryKey: ["lab"], queryFn: () => get<LabScenario[]>("/api/security-lab") });
export const runLabScenario = (id: string) =>
  api<LabResult>(`/api/security-lab/${id}/run`, { method: "POST" }).then((r) => r.data);

export const useUsers = () => useQuery({ queryKey: ["users"], queryFn: () => get<User[]>("/api/admin/users") });
export function useSaveUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id?: string; body: Record<string, unknown> }) =>
      api<User>(id ? `/api/admin/users/${id}` : "/api/admin/users", { method: id ? "PATCH" : "POST", body }).then(
        (r) => r.data,
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });
}
export function useLockUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, minutes }: { id: string; minutes: number }) =>
      api(`/api/admin/users/${id}/lock`, { body: { minutes } }).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });
}
export const useAdminConfig = () =>
  useQuery({ queryKey: ["admin-config"], queryFn: () => get<AdminConfig>("/api/admin/config") });

// ---------- chairside clinical tools ----------
export const usePerioCharts = (patientId?: number | string) =>
  useQuery({
    queryKey: ["charts", patientId],
    queryFn: () => get<PerioChart[]>(`/api/patients/${patientId}/perio-charts`),
    enabled: !!patientId,
  });

export function useSaveChart(patientId?: number | string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { exam_date: string; teeth: Record<string, ToothChart>; notes?: string | null }) =>
      api<PerioChart>(`/api/patients/${patientId}/perio-charts`, { body }).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["charts", patientId] });
      qc.invalidateQueries({ queryKey: ["care-plan", patientId] });
      qc.invalidateQueries({ queryKey: ["recall"] });
    },
  });
}

export const useCarePlan = (patientId?: number | string) =>
  useQuery({ queryKey: ["care-plan", patientId], queryFn: () => get<CarePlan>(`/api/patients/${patientId}/care-plan`), enabled: !!patientId });

export const useRecall = () =>
  useQuery({ queryKey: ["recall"], queryFn: () => api<RecallRow[]>("/api/recall") });
