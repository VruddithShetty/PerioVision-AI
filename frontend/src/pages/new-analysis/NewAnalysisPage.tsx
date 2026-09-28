import clsx from "clsx";
import { AnimatePresence, motion } from "framer-motion";
import {
  Brain,
  CheckCircle2,
  Crosshair,
  FileImage,
  Gauge,
  ImageUp,
  Loader2,
  ScanLine,
  ShieldCheck,
  Sigma,
  Sparkles,
  TriangleAlert,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ApiError } from "@/api/client";
import { usePatients, useRunAnalysis, useUpload } from "@/api/hooks";
import type { QualityResult, UploadResult } from "@/api/types";
import { PageHeader } from "@/components/ui/blocks";
import { Badge, Button, Card, CardTitle, Field, Input, Select } from "@/components/ui/primitives";

const PIPELINE = [
  { key: "pre", label: "Preprocess", detail: "CLAHE contrast, quality gate", icon: Sparkles },
  { key: "det", label: "Detect", detail: "YOLOv8 teeth · FDI numbers", icon: ScanLine },
  { key: "lm", label: "Landmarks", detail: "CEJ · alveolar crest · apex", icon: Crosshair },
  { key: "exp", label: "Explain", detail: "Grad-CAM attention check", icon: Brain },
  { key: "unc", label: "Uncertainty", detail: "Conformal interval · review routing", icon: Sigma },
  { key: "risk", label: "Risk", detail: "Clinical + image fusion", icon: Gauge },
];

function QualityCard({ q, upload }: { q: QualityResult; upload: UploadResult }) {
  const tone = q.verdict === "pass" ? "ok" : q.verdict === "warn" ? "review" : "critical";
  const Icon = q.verdict === "pass" ? CheckCircle2 : q.verdict === "warn" ? TriangleAlert : XCircle;
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
      <div className={clsx("flex items-start gap-3 rounded-2xl border p-4", {
        "border-teal-400/30 bg-teal-400/[0.06]": tone === "ok",
        "border-review-500/30 bg-review-500/[0.06]": tone === "review",
        "border-critical-500/30 bg-critical-500/[0.06]": tone === "critical",
      })}>
        <Icon className={clsx("mt-0.5 h-5 w-5", { "text-teal-400": tone === "ok", "text-review-400": tone === "review", "text-critical-400": tone === "critical" })} />
        <div>
          <p className="font-medium">
            {q.verdict === "pass" ? "Image quality looks good" : q.verdict === "warn" ? "Usable, with warnings (case will be reviewed)" : "Image rejected by the quality gate"}
          </p>
          {q.reasons.map((r) => (
            <p key={r.message} className="mt-1 text-sm text-mist-300">• {r.message}</p>
          ))}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
        {[
          ["Resolution", `${q.metrics.width}×${q.metrics.height}`],
          ["Sharpness", q.metrics.sharpness],
          ["Contrast", q.metrics.contrast],
          ["Format", upload.kind.toUpperCase()],
        ].map(([k, v]) => (
          <div key={k as string} className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-2.5">
            <p className="label">{k}</p>
            <p className="mt-1 font-mono text-mist-100">{v}</p>
          </div>
        ))}
      </div>
      <p className="flex items-start gap-2 text-xs text-mist-400">
        <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-teal-400" />
        Upload guard passed: magic bytes match, size and pixel limits checked, removed {upload.removed_metadata.join(", ") || "no metadata"}.
        Stored encrypted under a random ID.
      </p>
    </motion.div>
  );
}

export default function NewAnalysisPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { data: patients } = usePatients("");
  const [patientId, setPatientId] = useState<string>(params.get("patient") ?? "");
  const [visitDate, setVisitDate] = useState(new Date().toISOString().slice(0, 10));
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [active, setActive] = useState(-1);
  const upload = useUpload();
  const run = useRunAnalysis();

  useEffect(() => {
    if (!patientId && patients?.length) setPatientId(String(patients[0]!.patient_id));
  }, [patients, patientId]);

  const onFile = useCallback(
    (f: File) => {
      setFile(f);
      setPreview(f.type.startsWith("image/") ? URL.createObjectURL(f) : null);
      upload.reset();
      upload.mutate(f);
    },
    [upload],
  );

  // Animate the pipeline while the server works; finish when the response arrives.
  useEffect(() => {
    if (!run.isPending) return;
    setActive(0);
    const t = setInterval(() => setActive((a) => Math.min(a + 1, PIPELINE.length - 1)), 1400);
    return () => clearInterval(t);
  }, [run.isPending]);

  const start = async () => {
    if (!upload.data) return;
    try {
      const a = await run.mutateAsync({ upload_id: upload.data.upload_id, patient_id: Number(patientId), visit_date: visitDate });
      setActive(PIPELINE.length);
      setTimeout(() => navigate(`/app/analysis/${a.analysis_id}`), 700);
    } catch {
      setActive(-1);
    }
  };

  const uploadError = upload.error as ApiError | null;
  const runError = run.error as ApiError | null;
  const canRun = !!upload.data && upload.data.quality.verdict !== "reject" && !!patientId && !run.isPending;
  const patientName = useMemo(() => patients?.find((p) => String(p.patient_id) === patientId)?.patient_name, [patients, patientId]);

  return (
    <div>
      <PageHeader
        eyebrow="New analysis"
        title="Analyse a radiograph"
        subtitle="Panoramic or periapical, PNG, JPEG or DICOM. The file is checked, stripped of metadata and encrypted before any AI touches it."
      />
      <div className="grid gap-6 xl:grid-cols-[1.35fr_1fr]">
        <div className="space-y-6">
          <Card>
            <CardTitle icon={<FileImage className="h-4 w-4" />}>1 · Patient and visit</CardTitle>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Patient" htmlFor="patient">
                <Select id="patient" value={patientId} onChange={(e) => setPatientId(e.target.value)}>
                  {!patients?.length && <option value="">No patients available</option>}
                  {patients?.map((p) => (
                    <option key={p.patient_id} value={p.patient_id}>
                      {p.patient_name} · {p.pseudo_id}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Visit date" htmlFor="vd" hint="DICOM study date is used if present">
                <Input id="vd" type="date" value={visitDate} onChange={(e) => setVisitDate(e.target.value)} />
              </Field>
            </div>
          </Card>

          <Card>
            <CardTitle icon={<ImageUp className="h-4 w-4" />}>2 · Radiograph</CardTitle>
            <label
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                const f = e.dataTransfer.files[0];
                if (f) onFile(f);
              }}
              className={clsx(
                "group relative flex min-h-[260px] cursor-pointer flex-col items-center justify-center overflow-hidden rounded-2xl border-2 border-dashed transition",
                dragging ? "border-brand-400 bg-brand-400/10" : "border-white/10 hover:border-brand-400/50 hover:bg-white/[0.02]",
              )}
            >
              <input type="file" accept=".png,.jpg,.jpeg,.dcm" className="sr-only" onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])} />
              {preview ? (
                <>
                  <img src={preview} alt="Selected radiograph preview" className="max-h-[300px] w-full object-contain opacity-90" />
                  {upload.isPending && (
                    <div className="absolute inset-0 flex items-center justify-center bg-ink-950/60">
                      <div className="absolute inset-x-0 h-0.5 animate-[scan_1.6s_ease-in-out_infinite] bg-brand-400 shadow-[0_0_20px_#22d3ee]" />
                      <span className="flex items-center gap-2 text-sm"><Loader2 className="h-4 w-4 animate-spin" /> Checking file…</span>
                    </div>
                  )}
                </>
              ) : (
                <div className="text-center">
                  <div className="mx-auto mb-4 inline-flex rounded-2xl bg-brand-400/10 p-4 text-brand-300 ring-1 ring-brand-400/20 transition group-hover:scale-105">
                    <ImageUp className="h-8 w-8" />
                  </div>
                  <p className="font-medium">Drop a radiograph here or click to browse</p>
                  <p className="mt-1 text-xs text-mist-500">PNG · JPEG · DICOM (.dcm) · up to 16 MB</p>
                </div>
              )}
            </label>
            {file && <p className="mt-2 truncate text-xs text-mist-500">{file.name}</p>}
            <div className="mt-4">
              {uploadError && (
                <div role="alert" className="flex gap-2 rounded-xl border border-critical-500/30 bg-critical-500/10 p-3 text-sm text-critical-400">
                  <XCircle className="mt-0.5 h-4 w-4 shrink-0" /> Blocked by the upload guard: {uploadError.message}
                </div>
              )}
              {upload.data && <QualityCard q={upload.data.quality} upload={upload.data} />}
            </div>
          </Card>
        </div>

        <div className="space-y-6">
          <Card strong>
            <CardTitle icon={<ScanLine className="h-4 w-4" />}>3 · Run the pipeline</CardTitle>
            <ol className="relative space-y-1">
              {PIPELINE.map((s, i) => {
                const done = active > i;
                const current = active === i && run.isPending;
                return (
                  <li key={s.key} className={clsx("flex items-center gap-3 rounded-xl px-3 py-2.5 transition", current && "bg-brand-400/10")}>
                    <div className={clsx("relative flex h-9 w-9 items-center justify-center rounded-xl border transition", done ? "border-teal-400/40 bg-teal-400/10 text-teal-400" : current ? "border-brand-400/50 bg-brand-400/10 text-brand-300" : "border-white/10 text-mist-500")}>
                      {done ? <CheckCircle2 className="h-4 w-4" /> : current ? <Loader2 className="h-4 w-4 animate-spin" /> : <s.icon className="h-4 w-4" />}
                      {current && <span className="absolute inset-0 animate-ping rounded-xl border border-brand-400/40" />}
                    </div>
                    <div className="flex-1">
                      <p className={clsx("text-sm font-medium", done || current ? "text-mist-100" : "text-mist-400")}>{s.label}</p>
                      <p className="text-xs text-mist-500">{s.detail}</p>
                    </div>
                  </li>
                );
              })}
            </ol>
            <AnimatePresence>
              {runError && (
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} role="alert" className="mt-4 rounded-xl border border-critical-500/30 bg-critical-500/10 p-3 text-sm text-critical-400">
                  {runError.message}
                </motion.div>
              )}
            </AnimatePresence>
            <Button size="lg" className="mt-5 w-full" disabled={!canRun} loading={run.isPending} onClick={start}>
              {active >= PIPELINE.length ? "Done, opening results…" : "Analyse radiograph"}
            </Button>
            <p className="mt-3 text-center text-xs text-mist-500">
              {patientName ? `For ${patientName} · visit ${visitDate}` : "Choose a patient first"}
            </p>
          </Card>
          <Card>
            <p className="label">What happens to flagged cases?</p>
            <p className="mt-2 text-sm text-mist-300">
              Anything uncertain (ambiguous stage, attention outside the periodontal band, borderline quality, unusual image,
              estimated landmarks) is marked <Badge tone="review">Mandatory clinician review</Badge> and cannot be issued as a signed
              report until a dentist signs it off.
            </p>
          </Card>
        </div>
      </div>
    </div>
  );
}
