import clsx from "clsx";
import { motion } from "framer-motion";
import { CalendarClock, CheckCircle2, Circle, ClipboardCopy, Clock3, FileText, HeartHandshake, Printer, Send, Stethoscope } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useCarePlan } from "@/api/hooks";
import type { CarePlan } from "@/api/types";
import { Odontogram } from "@/components/dental/Odontogram";
import { ErrorState, LoadingRows, PageHeader, Stat } from "@/components/ui/blocks";
import { Badge, Button, Card, CardTitle } from "@/components/ui/primitives";
import { fmtDate, stageColor } from "@/lib/format";
import { useAuth } from "@/store/auth";

const PROGNOSIS_COLOR: Record<string, string> = {
  favourable: "#2dd4bf",
  questionable: "#fbbf24",
  unfavourable: "#fb923c",
  hopeless: "#ef4444",
  "not assessable": "#7f93b0",
};

function referralLetter(plan: CarePlan, clinician: string, clinic: string): string {
  const p = plan.patient;
  const s = plan.chart_summary;
  const worst = plan.teeth.filter((t) => t.bone_loss_pct !== null).sort((a, b) => b.bone_loss_pct! - a.bone_loss_pct!).slice(0, 5);
  const factors = [
    p.smoking_status === "current" ? `current smoker (${p.cigarettes_per_day ?? "?"}/day)` : null,
    p.diabetic ? `diabetes${p.hba1c ? `, HbA1c ${p.hba1c}%` : ""}` : null,
  ].filter(Boolean);
  return `Dear Colleague,

Re: ${p.patient_name} (ref ${p.pseudo_id}), age ${p.age ?? "n/a"}

I would be grateful if you could assess this patient for periodontal management.

Findings
• Suggested diagnosis: periodontitis Stage ${plan.stage ?? "?"}, Grade ${plan.grade.grade ?? "?"} (2017 AAP/EFP classification).
• Radiographic stage ${plan.radiographic_stage ?? "n/a"}; clinical stage ${plan.clinical_stage ?? "n/a"}.
${s ? `• Chart: BOP ${s.bop_pct ?? "–"}%, ${s.sites_pd_4_plus} sites ≥ 4 mm, ${s.sites_pd_6_plus} sites ≥ 6 mm, mean CAL ${s.mean_cal ?? "–"} mm.\n` : ""}• Most affected teeth (radiographic bone loss): ${worst.map((t) => `${t.tooth_id} ${t.bone_loss_pct?.toFixed(0) ?? "–"}%`).join(", ") || "n/a"}.
• Risk factors: ${factors.join("; ") || "none recorded"}.
• Teeth with questionable or worse prognosis: ${plan.prognosis.filter((x) => x.category !== "favourable" && x.category !== "not assessable").map((x) => `${x.tooth_id} (${x.category})`).join(", ") || "none"}.
• Teeth not measured on the radiograph (assess clinically): ${plan.prognosis.filter((x) => x.category === "not assessable").map((x) => x.tooth_id).join(", ") || "none"}.

Treatment so far / proposed
${plan.steps.filter((x) => x.indicated).map((x) => `• Step ${x.step}: ${x.title}`).join("\n")}

Radiograph analysis was supported by PerioVision AI (decision support; findings reviewed by the referring clinician).

Kind regards,
${clinician}
${clinic}`;
}

export default function CarePlanPage() {
  const { patientId } = useParams();
  const { data: plan, isLoading, error, refetch } = useCarePlan(patientId);
  const user = useAuth((s) => s.user);
  const [done, setDone] = useState<Record<string, boolean>>({});
  const [copied, setCopied] = useState(false);
  const letter = useMemo(() => (plan ? referralLetter(plan, user?.name ?? "", user?.clinic_name ?? "") : ""), [plan, user]);

  if (isLoading) return <LoadingRows rows={8} />;
  if (error || !plan) return <ErrorState error={error} retry={refetch} />;

  const prognosisTeeth = plan.teeth.map((t) => {
    const pr = plan.prognosis.find((x) => x.tooth_id === t.tooth_id);
    // Re-use the odontogram: colour teeth by prognosis instead of stage.
    const stageLike = pr ? ({ favourable: "I", questionable: "II", unfavourable: "III", hopeless: "IV" } as Record<string, string>)[pr.category] ?? null : null;
    return { tooth_id: t.tooth_id, bone_loss_pct: t.bone_loss_pct, stage: stageLike } as never;
  });

  const copy = async () => {
    await navigator.clipboard.writeText(letter);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div>
      <PageHeader
        eyebrow="Care plan"
        title={plan.patient.patient_name}
        subtitle={plan.disclaimer}
        actions={
          <>
            <Link to={`/app/patients/${patientId}/perio-chart`}><Button variant="outline" icon={<Stethoscope className="h-4 w-4" />}>Perio chart</Button></Link>
            <Link to={`/app/patients/${patientId}/explain`}><Button variant="subtle" icon={<HeartHandshake className="h-4 w-4" />}>Explain to patient</Button></Link>
          </>
        }
      />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Diagnosis suggestion" value={<span style={{ color: stageColor(plan.stage) }}>Stage {plan.stage ?? "–"}</span>} hint={`X-ray ${plan.radiographic_stage ?? "–"} · clinical ${plan.clinical_stage ?? "–"}`} />
        <Stat label="Grade" value={plan.grade.grade ?? "–"} hint={plan.grade.basis ?? "insufficient data"} tone={plan.grade.grade === "C" ? "critical" : plan.grade.grade === "B" ? "review" : "ok"} />
        <Stat label="Recall interval" value={`${plan.recall.months} months`} icon={<Clock3 className="h-5 w-5" />} hint={plan.recall.reasons[0]} />
        <Stat
          label="Next recall"
          value={plan.next_recall_due ? fmtDate(plan.next_recall_due) : "–"}
          icon={<CalendarClock className="h-5 w-5" />}
          tone={plan.next_recall_due && new Date(plan.next_recall_due) < new Date() ? "critical" : "brand"}
          hint={plan.last_visit ? `last seen ${fmtDate(plan.last_visit)}` : undefined}
        />
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[1.25fr_1fr]">
        <Card strong>
          <CardTitle>EFP step-wise therapy</CardTitle>
          <ol className="relative space-y-4 border-l border-white/10 pl-6">
            {plan.steps.map((s, i) => (
              <motion.li key={s.step} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.08 }} className={clsx(!s.indicated && "opacity-45")}>
                <span className={clsx("absolute -left-[13px] flex h-6 w-6 items-center justify-center rounded-full border text-xs font-bold", s.indicated ? "border-brand-400 bg-ink-900 text-brand-300" : "border-white/15 bg-ink-900 text-mist-500")}>{s.step}</span>
                <div className="flex items-center gap-2">
                  <p className="font-display font-semibold">{s.title}</p>
                  {s.indicated ? <Badge tone="brand">indicated</Badge> : <Badge>not needed now</Badge>}
                </div>
                <ul className="mt-2 space-y-1.5">
                  {s.items.map((item) => {
                    const key = `${s.step}-${item}`;
                    return (
                      <li key={item}>
                        <button type="button" onClick={() => setDone((d) => ({ ...d, [key]: !d[key] }))} className="flex items-start gap-2 text-left text-sm text-mist-300 hover:text-mist-100">
                          {done[key] ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-teal-400" /> : <Circle className="mt-0.5 h-4 w-4 shrink-0 text-mist-500" />}
                          <span className={clsx(done[key] && "line-through opacity-60")}>{item}</span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </motion.li>
            ))}
          </ol>
          {plan.grade.reasons.length > 0 && (
            <div className="mt-5 rounded-xl border border-white/[0.06] bg-white/[0.02] p-3 text-xs text-mist-400">
              <p className="label mb-1">Why this grade</p>
              {plan.grade.reasons.map((r) => <p key={r}>• {r}</p>)}
            </div>
          )}
        </Card>

        <Card>
          <CardTitle>Tooth prognosis map</CardTitle>
          {plan.teeth.length ? (
            <>
              <Odontogram teeth={prognosisTeeth} selected={null} onSelect={() => undefined} />
              <div className="mt-4 flex flex-wrap gap-3 text-xs">
                {Object.entries(PROGNOSIS_COLOR).map(([k, c]) => (
                  <span key={k} className="flex items-center gap-1.5 capitalize text-mist-300"><span className="h-2.5 w-2.5 rounded-full" style={{ background: c }} />{k} ({plan.prognosis.filter((p) => p.category === k).length})</span>
                ))}
              </div>
              <ul className="mt-4 max-h-56 space-y-1 overflow-y-auto pr-1 text-xs">
                {plan.prognosis.filter((p) => p.category !== "favourable").map((p) => (
                  <li key={p.tooth_id} className="flex gap-2"><span className="w-8 font-mono font-bold" style={{ color: PROGNOSIS_COLOR[p.category] }}>{p.tooth_id}</span><span className="capitalize text-mist-100">{p.category}</span><span className="text-mist-500">· {p.reasons.join(", ")}</span></li>
                ))}
              </ul>
              <p className="mt-3 text-[11px] text-mist-500">Simplified after Kwok &amp; Caton (2007): bone loss, mobility and furcation from the latest X-ray and chart.</p>
            </>
          ) : (
            <p className="text-sm text-mist-400">Analyse a radiograph to see per-tooth prognosis.</p>
          )}
        </Card>
      </div>

      <Card className="mt-6">
        <CardTitle
          icon={<FileText className="h-4 w-4" />}
          action={
            <div className="flex gap-2">
              <Button size="sm" variant="outline" icon={<Printer className="h-3.5 w-3.5" />} onClick={() => window.print()}>Print</Button>
              <Button size="sm" icon={copied ? <CheckCircle2 className="h-3.5 w-3.5" /> : <ClipboardCopy className="h-3.5 w-3.5" />} onClick={copy}>{copied ? "Copied" : "Copy letter"}</Button>
            </div>
          }
        >
          Referral letter to a periodontist {plan.referral_suggested ? <Badge tone="review" className="ml-2"><Send className="h-3 w-3" /> referral suggested</Badge> : null}
        </CardTitle>
        <pre className="max-h-[420px] overflow-y-auto whitespace-pre-wrap rounded-xl border border-white/[0.06] bg-ink-950/60 p-4 font-sans text-sm leading-relaxed text-mist-300">{letter}</pre>
      </Card>
    </div>
  );
}
