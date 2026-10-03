import { AlertTriangle, Box, CheckCircle2, ClipboardList, FileSignature, LineChart, ScanLine, ShieldCheck, Stethoscope } from "lucide-react";
import { lazy, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError } from "@/api/client";
import { useAnalysis, useCreateReport } from "@/api/hooks";
import { RiskGauge } from "@/components/charts/Charts";
import { Odontogram } from "@/components/dental/Odontogram";
import { RadiographViewer } from "@/components/dental/RadiographViewer";
import { ToothPanel } from "@/components/dental/ToothPanel";
import { ErrorState, PageHeader, Tabs } from "@/components/ui/blocks";
import { Badge, Button, Card, CardTitle, Skeleton } from "@/components/ui/primitives";
import { fmtDate, fmtPct, PROGRESSION_TONE, REASON_LABEL, REVIEW_LABEL, REVIEW_TONE, stageColor } from "@/lib/format";
import { useCan } from "@/store/auth";
import { SceneGate } from "@/three/SceneGate";

const DentalArch3D = lazy(() => import("@/three/DentalArch3D"));

export default function AnalysisViewerPage() {
  const { analysisId } = useParams();
  const navigate = useNavigate();
  const { data: a, isLoading, error, refetch } = useAnalysis(analysisId);
  const [selected, setSelected] = useState<string | null>(null);
  const [view, setView] = useState<"2d" | "chart" | "3d">("2d");
  const canReview = useCan("review:signoff");
  const canReport = useCan("report:generate");
  const createReport = useCreateReport();

  useEffect(() => {
    if (a && !selected && a.teeth.length) {
      const measured = a.teeth.filter((t) => t.bone_loss_pct !== null);
      const worst = measured.length ? measured.reduce((x, y) => (y.bone_loss_pct! > x.bone_loss_pct! ? y : x)) : a.teeth[0]!;
      setSelected(worst.tooth_id);
    }
  }, [a, selected]);

  const tooth = useMemo(() => a?.teeth.find((t) => t.tooth_id === selected) ?? null, [a, selected]);
  const comparison = useMemo(() => a?.progression.find((c) => c.tooth_id === selected), [a, selected]);

  if (isLoading) return <div className="space-y-4"><Skeleton className="h-16" /><Skeleton className="h-[460px]" /></div>;
  if (error || !a) return <ErrorState error={error} retry={refetch} />;

  const needsReview = a.review.status === "review_required";
  const report = async () => {
    try {
      await createReport.mutateAsync(a.analysis_id);
      navigate("/app/reports");
    } catch {
      /* shown below */
    }
  };

  return (
    <div>
      <PageHeader
        eyebrow={`Analysis ${a.analysis_id}`}
        title={a.patient ? `${a.patient.name}` : a.pseudo_id}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-brand-300">{a.pseudo_id}</span> · visit {fmtDate(a.visit_date)} · {a.summary.teeth_detected} teeth
            {a.mode === "demo" && <Badge tone="review">Demo mode — synthetic data, not clinical</Badge>}
            {a.summary.teeth_measured !== undefined && a.summary.teeth_measured < a.summary.teeth_detected && (
              <Badge tone="review">{a.summary.teeth_measured} of {a.summary.teeth_detected} measured</Badge>
            )}
          </span>
        }
        actions={
          <>
            <Link to={`/app/patients/${a.patient_id}/progression`}>
              <Button variant="outline" icon={<LineChart className="h-4 w-4" />}>Progression</Button>
            </Link>
            <Link to={`/app/patients/${a.patient_id}/care-plan`}>
              <Button variant="outline" icon={<ClipboardList className="h-4 w-4" />}>Care plan</Button>
            </Link>
            {canReview && needsReview && (
              <Link to={`/app/review?open=${a.analysis_id}`}>
                <Button variant="subtle" icon={<Stethoscope className="h-4 w-4" />}>Review & sign off</Button>
              </Link>
            )}
            {canReport && (
              <Button icon={<FileSignature className="h-4 w-4" />} disabled={needsReview || a.review.status === "rejected"} loading={createReport.isPending} onClick={report} title={needsReview ? "Needs a dentist's sign-off first" : "Generate a signed PDF"}>
                Signed report
              </Button>
            )}
          </>
        }
      />
      {createReport.error && <div className="mb-4"><ErrorState error={createReport.error as ApiError} /></div>}

      <div className={`mb-6 flex items-start gap-3 rounded-2xl border p-4 ${needsReview ? "border-review-500/30 bg-review-500/[0.07]" : "border-teal-400/25 bg-teal-400/[0.05]"}`}>
        {needsReview ? <AlertTriangle className="mt-0.5 h-5 w-5 text-review-400" /> : <CheckCircle2 className="mt-0.5 h-5 w-5 text-teal-400" />}
        <div className="flex-1">
          <p className="font-medium">
            <Badge tone={REVIEW_TONE[a.review.status]}>{REVIEW_LABEL[a.review.status]}</Badge>{" "}
            <span className="ml-1">{needsReview ? "Mandatory clinician review: this result cannot be reported until a dentist signs it off." : a.review.decision ? `Signed off by ${a.review.decision.reviewer_name}` : "No automatic flags."}</span>
          </p>
          {a.review.reasons.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {a.review.reasons.map((r) => (
                <span key={r.code} title={r.message} className="rounded-lg border border-white/10 bg-ink-900/60 px-2 py-1 text-xs text-mist-300">
                  {REASON_LABEL[r.code] ?? r.code}
                  {r.teeth && <span className="text-mist-500"> · {r.teeth.length} teeth</span>}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="grid gap-6 2xl:grid-cols-[minmax(0,1fr)_380px] xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="space-y-6">
          <Card>
            <CardTitle
              action={
                <Tabs
                  value={view}
                  onChange={setView}
                  items={[
                    { value: "2d", label: "Radiograph" },
                    { value: "chart", label: "Dental chart" },
                    { value: "3d", label: "3D arch" },
                  ]}
                />
              }
            >
              Findings
            </CardTitle>
            {view === "2d" && (
              <RadiographViewer
                radiographUrl={a.images.radiograph}
                gradcamUrl={a.images.gradcam}
                width={a.image_size[0]}
                height={a.image_size[1]}
                teeth={a.teeth}
                selected={selected}
                onSelect={setSelected}
              />
            )}
            {view === "chart" && <Odontogram teeth={a.teeth} selected={selected} onSelect={setSelected} />}
            {view === "3d" && (
              <div className="h-[460px] rounded-2xl border border-white/[0.06] bg-gradient-to-b from-ink-800/60 to-ink-950">
                <SceneGate allowReducedMotion fallback={<Odontogram teeth={a.teeth} selected={selected} onSelect={setSelected} />}>
                  <DentalArch3D teeth={a.teeth} selected={selected} onSelect={setSelected} />
                </SceneGate>
              </div>
            )}
          </Card>

          <div className="grid gap-6 md:grid-cols-3">
            <Card>
              <p className="label">Worst-tooth stage</p>
              <p className="mt-2 font-display text-4xl font-bold" style={{ color: stageColor(a.summary.stage) }}>{a.summary.stage ?? "–"}</p>
              <p className="mt-1 text-xs text-mist-500">mean {fmtPct(a.summary.mean_bone_loss_pct)} · max {fmtPct(a.summary.max_bone_loss_pct)}</p>
            </Card>
            <Card>
              <p className="label">Grade suggestion</p>
              <p className="mt-2 font-display text-4xl font-bold text-mist-100">{a.summary.grade.grade ?? "–"}</p>
              <p className="mt-1 text-xs text-mist-500">{a.summary.grade.basis ?? "insufficient data"}</p>
            </Card>
            <Card>
              <p className="label">Affected teeth</p>
              <p className="mt-2 font-display text-4xl font-bold text-mist-100">{a.summary.affected_teeth}</p>
              <p className="mt-1 text-xs text-mist-500">bone loss above 15%</p>
            </Card>
          </div>

          <Card>
            <CardTitle icon={<ShieldCheck className="h-4 w-4" />}>Integrity and inputs</CardTitle>
            <div className="grid gap-3 text-sm md:grid-cols-3">
              <div className="rounded-xl border border-white/[0.06] p-3">
                <p className="label">Image quality</p>
                <p className="mt-1 capitalize">{a.quality.verdict}</p>
                <p className="text-xs text-mist-500">sharpness {a.quality.metrics.sharpness} · contrast {a.quality.metrics.contrast}</p>
              </div>
              <div className="rounded-xl border border-white/[0.06] p-3">
                <p className="label">Adversarial screen</p>
                <p className="mt-1">{a.adversarial.is_suspicious ? "Suspicious" : "Clean"}</p>
                <p className="text-xs text-mist-500">noise residual {a.adversarial.metrics.noise_residual}</p>
              </div>
              <div className="rounded-xl border border-white/[0.06] p-3">
                <p className="label">Models</p>
                {a.models.map((m) => (
                  <p key={m.name} className="text-xs">
                    {m.signature_valid ? <span className="text-teal-400">✓ signed</span> : <span className="text-review-400">✗ {m.reason}</span>} · {m.name}
                  </p>
                ))}
              </div>
            </div>
          </Card>
        </div>

        <div className="space-y-6">
          <Card strong className="xl:sticky xl:top-6">
            <ToothPanel tooth={tooth} coverage={a.calibration.coverage} />
            {comparison && (
              <div className="mt-5 rounded-xl border border-white/[0.06] bg-white/[0.02] p-3 text-sm">
                <p className="label mb-1">Since {fmtDate(comparison.from_date)}</p>
                <div className="flex items-center justify-between">
                  <span>{comparison.delta_pct > 0 ? "+" : ""}{comparison.delta_pct}% bone loss</span>
                  <Badge tone={PROGRESSION_TONE[comparison.label] ?? "neutral"}>{comparison.label}</Badge>
                </div>
                {!comparison.reliable && <p className="mt-1 text-xs text-mist-500">{comparison.reliability_reasons[0]}</p>}
              </div>
            )}
          </Card>
          {a.panoramic_assessment && (
            <Card>
              <CardTitle icon={<ScanLine className="h-4 w-4" />}>Whole-film panoramic estimate</CardTitle>
              <p className="text-xs text-mist-500">{a.panoramic_assessment.note}</p>
              {a.panoramic_assessment.screen && (
                <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
                  {(["maxilla", "mandible"] as const).map((jaw) => {
                    const s = a.panoramic_assessment!.screen![jaw];
                    return (
                      <div key={jaw} className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
                        <p className="label">{jaw === "maxilla" ? "Upper jaw" : "Lower jaw"}</p>
                        <p className={s.bone_loss_suggested ? "mt-1 font-semibold text-review-400" : "mt-1 font-semibold text-teal-400"}>
                          {s.bone_loss_suggested ? "Generalised bone loss suggested" : "Not suggested"}
                        </p>
                        <p className="text-[11px] text-mist-500">probability {s.probability.toFixed(2)} · test AUC {s.test.test_auc.toFixed(2)}</p>
                      </div>
                    );
                  })}
                </div>
              )}
              {a.panoramic_assessment.worst_tooth && (() => {
                const w = a.panoramic_assessment!.worst_tooth!;
                return (
                  <div className="mt-3 rounded-xl border border-white/[0.06] bg-white/[0.02] p-3 text-sm">
                    <p className="label">Worst tooth (estimate)</p>
                    <p className="mt-1">
                      about <b style={{ color: stageColor(w.stage) }}>{w.bone_loss_pct.toFixed(0)}%</b> bone loss · 90% range {w.interval_90[0].toFixed(0)}–{w.interval_90[1].toFixed(0)}% · possible stages {w.stage_set.join(" / ")}
                    </p>
                    <p className="mt-1 text-[11px] text-mist-500">
                      Tested on {w.test.test_films} held-out films: average error {w.test.test_MAE.toFixed(1)} points, stage agreement {Math.round(w.test.test_stage_agreement * 100)}%. Tends to underestimate very severe cases.
                    </p>
                  </div>
                );
              })()}
            </Card>
          )}
          <Card>
            <CardTitle icon={<Box className="h-4 w-4" />}>Clinical risk profile</CardTitle>
            <div className="flex justify-center">
              {a.risk.probability !== null && a.risk.category ? (
                <RiskGauge value={a.risk.probability} category={a.risk.category} />
              ) : (
                <p className="py-6 text-center text-sm text-review-400">No risk score: required inputs are missing.</p>
              )}
            </div>
            <ul className="mt-3 space-y-2">
              {a.risk.top_factors.map((f) => (
                <li key={f.factor} className="flex items-center gap-3 text-sm">
                  <span className="h-1.5 rounded-full bg-gradient-to-r from-review-400 to-critical-400" style={{ width: `${Math.min(100, f.contribution * 60)}px` }} />
                  <span className="text-mist-300">{f.text}</span>
                </li>
              ))}
              {!a.risk.top_factors.length && <li className="text-sm text-mist-500">No strong contributing factors.</li>}
            </ul>
            {a.risk.missing_inputs.length > 0 && <p className="mt-3 text-xs text-review-400">Missing: {a.risk.missing_inputs.join(", ")}</p>}
            <p className="mt-3 text-[11px] text-mist-500">{a.risk.model_type}{a.risk.validation ? ` (validated on ${a.risk.validation.test_n.toLocaleString()} people, AUC ${a.risk.validation.roc_auc.toFixed(2)})` : ""} · {a.risk.disclaimer}</p>
          </Card>
        </div>
      </div>
    </div>
  );
}
