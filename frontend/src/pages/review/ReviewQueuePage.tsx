import clsx from "clsx";
import { AnimatePresence, motion } from "framer-motion";
import { Check, ClipboardCheck, PenLine, Stethoscope, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError } from "@/api/client";
import { useAnalysis, useReviewQueue, useSignOff } from "@/api/hooks";
import type { Tooth } from "@/api/types";
import { EmptyState, ErrorState, LoadingRows, PageHeader } from "@/components/ui/blocks";
import { Badge, Button, Card, CardTitle, Field, Input, Select, Skeleton } from "@/components/ui/primitives";
import { useAuthedImage } from "@/hooks";
import { fmtDate, fmtDateTime, REASON_LABEL, stageColor } from "@/lib/format";
import { useCan } from "@/store/auth";

type Correction = { bone_loss_pct: string; stage: string; note: string };

function CaseImage({ url }: { url?: string }) {
  const img = useAuthedImage(url);
  if (!img.url) return <Skeleton className="aspect-[2/1] w-full" />;
  return <img src={img.url} alt="Annotated radiograph" className="w-full rounded-xl border border-white/[0.06]" />;
}

function ReviewPanel({ id, onDone }: { id: string; onDone: () => void }) {
  const { data: a, isLoading, error } = useAnalysis(id);
  const signOff = useSignOff();
  const canSign = useCan("review:signoff");
  const [comment, setComment] = useState("");
  const [corr, setCorr] = useState<Record<string, Correction>>({});

  if (isLoading) return <LoadingRows rows={6} />;
  if (error || !a) return <ErrorState error={error} />;

  const edit = (t: Tooth, patch: Partial<Correction>) =>
    setCorr((c) => ({ ...c, [t.tooth_id]: { ...{ bone_loss_pct: "", stage: "", note: "" }, ...c[t.tooth_id], ...patch } }));
  const corrections = Object.entries(corr)
    .filter(([, v]) => v.bone_loss_pct !== "" || v.stage !== "" || v.note !== "")
    .map(([tooth_id, v]) => ({
      tooth_id,
      bone_loss_pct: v.bone_loss_pct === "" ? null : Number(v.bone_loss_pct),
      stage: v.stage || null,
      note: v.note || null,
    }));

  const decide = async (decision: "approve" | "correct" | "reject") => {
    await signOff.mutateAsync({ id, body: { decision, comment: comment || null, corrections: decision === "correct" ? corrections : [] } });
    onDone();
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="font-display text-lg font-semibold">{a.patient?.name ?? a.pseudo_id}</p>
          <p className="text-xs text-mist-500"><span className="font-mono text-brand-300">{a.pseudo_id}</span> · visit {fmtDate(a.visit_date)} · {a.mode}</p>
        </div>
        <Link to={`/app/analysis/${a.analysis_id}`} className="text-xs text-brand-300 hover:underline">Open full viewer →</Link>
      </div>
      <CaseImage url={a.images.annotated} />
      <div className="flex flex-wrap gap-1.5">
        {a.review.reasons.map((r) => (
          <span key={r.code} className="rounded-lg border border-review-500/30 bg-review-500/[0.08] px-2 py-1 text-xs text-review-400" title={r.message}>
            {REASON_LABEL[r.code] ?? r.code}
          </span>
        ))}
      </div>

      <div className="overflow-x-auto rounded-xl border border-white/[0.06]">
        <table className="w-full min-w-[620px] text-sm">
          <thead className="bg-white/[0.03] text-[11px] uppercase tracking-wider text-mist-400">
            <tr>
              <th className="px-3 py-2 text-left">Tooth</th>
              <th className="px-3 py-2 text-left">AI finding</th>
              <th className="px-3 py-2 text-left">Your bone loss %</th>
              <th className="px-3 py-2 text-left">Your stage</th>
              <th className="px-3 py-2 text-left">Note</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/[0.05]">
            {a.teeth.map((t) => {
              const c = corr[t.tooth_id];
              const changed = c && (c.bone_loss_pct !== "" || c.stage !== "");
              return (
                <tr key={t.tooth_id} className={clsx(changed && "bg-brand-400/[0.05]")}>
                  <td className="px-3 py-2 font-mono font-semibold">{t.tooth_id}</td>
                  <td className="px-3 py-2">
                    <span style={{ color: stageColor(t.stage) }}>{t.bone_loss_pct?.toFixed(1) ?? "–"}% · {t.stage ?? "–"}</span>
                    {t.bone_loss_pct === null && <span className="ml-1 text-[10px] text-review-400">not measured</span>}
                  </td>
                  <td className="px-3 py-2"><Input type="number" min={0} max={100} step="0.5" className="w-24 py-1.5" value={c?.bone_loss_pct ?? ""} onChange={(e) => edit(t, { bone_loss_pct: e.target.value })} disabled={!canSign} aria-label={`Corrected bone loss for tooth ${t.tooth_id}`} /></td>
                  <td className="px-3 py-2">
                    <Select className="w-24 py-1.5" value={c?.stage ?? ""} onChange={(e) => edit(t, { stage: e.target.value })} disabled={!canSign} aria-label={`Corrected stage for tooth ${t.tooth_id}`}>
                      <option value="">–</option>
                      <option>I</option><option>II</option><option>III</option><option>IV</option>
                    </Select>
                  </td>
                  <td className="px-3 py-2"><Input className="py-1.5" value={c?.note ?? ""} onChange={(e) => edit(t, { note: e.target.value })} disabled={!canSign} aria-label={`Note for tooth ${t.tooth_id}`} /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <Field label="Comment for the record" htmlFor="rc">
        <textarea id="rc" rows={2} className="input" value={comment} onChange={(e) => setComment(e.target.value)} disabled={!canSign} placeholder="e.g. Crest level confirmed clinically; probing depths 5 mm at 36." />
      </Field>
      {signOff.error && <ErrorState error={signOff.error as ApiError} />}
      {canSign ? (
        <div className="grid gap-2 sm:grid-cols-3">
          <Button icon={<Check className="h-4 w-4" />} onClick={() => decide("approve")} loading={signOff.isPending}>Approve</Button>
          <Button variant="outline" icon={<PenLine className="h-4 w-4" />} disabled={!corrections.length} onClick={() => decide("correct")}>
            Save {corrections.length || ""} correction{corrections.length === 1 ? "" : "s"}
          </Button>
          <Button variant="danger" icon={<X className="h-4 w-4" />} onClick={() => decide("reject")}>Reject</Button>
        </div>
      ) : (
        <p className="text-sm text-mist-400">Only dentists can sign off cases.</p>
      )}
      <p className="text-[11px] text-mist-500">Corrections are stored separately (for future retraining) and every decision is written to the tamper-evident audit log.</p>
    </div>
  );
}

export default function ReviewQueuePage() {
  const { data, isLoading, error, refetch } = useReviewQueue();
  const [params, setParams] = useSearchParams();
  const [open, setOpen] = useState<string | null>(params.get("open"));

  useEffect(() => {
    if (!open && data?.length) setOpen(data[0]!.analysis_id);
  }, [data, open]);

  const select = (id: string) => {
    setOpen(id);
    params.set("open", id);
    setParams(params, { replace: true });
  };

  return (
    <div>
      <PageHeader
        eyebrow="Clinician review"
        title="Review queue"
        subtitle="Every case the AI is not sure about waits here. Approve it, correct individual teeth, or reject it. Only signed-off cases can become signed reports."
      />
      {error ? (
        <ErrorState error={error} retry={refetch} />
      ) : isLoading ? (
        <LoadingRows />
      ) : !data?.length ? (
        <EmptyState icon={<ClipboardCheck className="h-6 w-6" />} title="Queue is clear" body="No cases are waiting for a dentist's sign-off." />
      ) : (
        <div className="grid gap-6 xl:grid-cols-[340px_minmax(0,1fr)]">
          <div className="space-y-2">
            <p className="label">{data.length} waiting</p>
            <AnimatePresence>
              {data.map((q) => (
                <motion.button
                  layout
                  key={q.analysis_id}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -30 }}
                  onClick={() => select(q.analysis_id)}
                  className={clsx("glass block w-full p-4 text-left transition", open === q.analysis_id ? "border-brand-400/40 shadow-glow" : "hover:border-white/15")}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-sm text-brand-300">{q.pseudo_id}</span>
                    <span className="text-[11px] text-mist-500">{fmtDateTime(q.created)}</span>
                  </div>
                  <p className="mt-1 text-sm">Visit {fmtDate(q.visit_date)} · {q.teeth} teeth · stage {q.stage ?? "–"}</p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {q.reasons.slice(0, 3).map((r) => <Badge key={r.code} tone="review">{REASON_LABEL[r.code] ?? r.code}</Badge>)}
                    {q.reasons.length > 3 && <Badge>+{q.reasons.length - 3}</Badge>}
                  </div>
                </motion.button>
              ))}
            </AnimatePresence>
          </div>
          <Card strong>
            <CardTitle icon={<Stethoscope className="h-4 w-4" />}>AI finding vs your assessment</CardTitle>
            {open ? <ReviewPanel key={open} id={open} onDone={() => { setOpen(null); params.delete("open"); setParams(params); refetch(); }} /> : <EmptyState title="Pick a case" />}
          </Card>
        </div>
      )}
    </div>
  );
}
