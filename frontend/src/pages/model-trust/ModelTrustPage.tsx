import { BadgeCheck, FileLock2, Gauge, Info, ShieldX } from "lucide-react";
import { lazy } from "react";
import { useModelStatus, useModelTrust } from "@/api/hooks";
import { CalibrationPlot, ReasonBars } from "@/components/charts/Charts";
import { EmptyState, ErrorState, LoadingRows, PageHeader, Stat } from "@/components/ui/blocks";
import { Badge, Card, CardTitle } from "@/components/ui/primitives";
import { REASON_LABEL, shortHash } from "@/lib/format";
import { SceneGate } from "@/three/SceneGate";

const TrustOrb = lazy(() => import("@/three/TrustOrb"));

export default function ModelTrustPage() {
  const { data, isLoading, error, refetch } = useModelTrust();
  const { data: status } = useModelStatus();
  if (isLoading) return <LoadingRows rows={8} />;
  if (error || !data) return <ErrorState error={error} retry={refetch} />;
  const cal = data.calibration;
  // a missing optional model is fine; a present-but-unsigned model never is
  const verified = data.models.every((m) => m.signature_valid || (m.optional && !m.present));

  return (
    <div>
      <PageHeader
        eyebrow="Model trust"
        title="Can you trust this model today?"
        subtitle="Signature status of every weight file, how honest the uncertainty is, and how often cases are pushed to a dentist."
      />
      <div className="grid gap-6 lg:grid-cols-[1fr_1.4fr]">
        <Card strong className="relative overflow-hidden">
          <div className="h-72">
            <SceneGate allowReducedMotion fallback={<div className="flex h-full items-center justify-center"><Gauge className="h-24 w-24 text-brand-400/40" /></div>}>
              <TrustOrb verified={verified} calibrated={cal.calibrated} />
            </SceneGate>
          </div>
          <div className="grid grid-cols-3 gap-2 text-center text-xs">
            <div className="rounded-xl border border-white/[0.06] p-2">
              <p className={verified ? "text-teal-400" : "text-critical-400"}>{verified ? "Signed" : "Unsigned"}</p>
              <p className="text-mist-500">weights</p>
            </div>
            <div className="rounded-xl border border-white/[0.06] p-2">
              <p className={cal.calibrated ? "text-teal-400" : "text-review-400"}>{cal.calibrated ? "Calibrated" : "Uncalibrated"}</p>
              <p className="text-mist-500">uncertainty</p>
            </div>
            <div className="rounded-xl border border-white/[0.06] p-2">
              <p className="text-brand-300">Human-in-loop</p>
              <p className="text-mist-500">review</p>
            </div>
          </div>
        </Card>
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-3">
            <Stat label="Analyses" value={data.analyses_total} />
            <Stat label="Auto-flagged" value={data.auto_flagged} tone="review" hint="sent to clinician review" />
            <Stat label="Flagged share" value={data.flagged_share === null ? "–" : `${Math.round(data.flagged_share * 100)}%`} tone="review" />
          </div>
          <Card>
            <CardTitle icon={<FileLock2 className="h-4 w-4" />}>Model registry</CardTitle>
            <div className="space-y-2">
              {data.models.map((m) => (
                <div key={m.name} className="flex items-start gap-3 rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
                  {m.signature_valid ? <BadgeCheck className="mt-0.5 h-5 w-5 text-teal-400" /> : <ShieldX className="mt-0.5 h-5 w-5 text-critical-400" />}
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium">{m.purpose}</p>
                    <p className="font-mono text-[11px] text-mist-500">{m.file} · sha256 {shortHash(m.sha256)}</p>
                    {!m.signature_valid && <p className="text-xs text-critical-400">Refused: {m.reason}</p>}
                  </div>
                  <Badge tone={m.loaded ? "ok" : "neutral"}>{m.loaded ? "loaded" : "not loaded"}</Badge>
                </div>
              ))}
            </div>
            <p className="mt-3 text-xs text-mist-500">
              RSA-PSS public key fingerprint <span className="hash">{status?.public_key_fingerprint ?? "–"}</span> · risk model: {data.risk_model.type} ({data.risk_model.version})
            </p>
          </Card>
        </div>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card>
          <CardTitle icon={<Gauge className="h-4 w-4" />}>Conformal coverage</CardTitle>
          {!cal.calibrated ? (
            <EmptyState icon={<Info className="h-6 w-6" />} title="Not calibrated yet" body={cal.message} />
          ) : (
            <>
              <div className="grid grid-cols-3 gap-2 text-center">
                {Object.entries(cal.levels ?? {}).map(([k, v]) => (
                  <div key={k} className="rounded-xl border border-white/[0.06] p-3">
                    <p className="label">target {Math.round(Number(k) * 100)}%</p>
                    <p className="mt-1 font-display text-2xl font-bold">
                      {v.empirical_coverage_other_half === null ? "–" : `${Math.round(v.empirical_coverage_other_half * 100)}%`}
                    </p>
                    <p className="text-[11px] text-mist-500">
                      {v.mean_half_width_pct != null ? `avg ± ${v.mean_half_width_pct.toFixed(1)} pts` : `± ${v.q_from_half?.toFixed(1) ?? "∞"} pts`}
                    </p>
                  </div>
                ))}
              </div>
              <CalibrationPlot bins={cal.reliability_bins ?? []} />
              <p className="text-xs text-mist-500">Source: {cal.source} · {cal.n_scores} teeth · MAE {cal.mean_absolute_error_pct} pts{cal.adaptive ? " · adaptive: each tooth's interval widens when the normal and mirrored readings disagree" : ""}</p>
            </>
          )}
        </Card>
        <Card>
          <CardTitle>Why cases were flagged</CardTitle>
          {Object.keys(data.flag_reasons).length ? <ReasonBars data={data.flag_reasons} labels={REASON_LABEL} /> : <EmptyState title="No flags yet" />}
        </Card>
      </div>
    </div>
  );
}
