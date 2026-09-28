import clsx from "clsx";
import { motion } from "framer-motion";
import { ArrowLeft, Cigarette, Droplets, HeartPulse, Printer, Smile, Sparkles, Stethoscope } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Area, AreaChart, CartesianGrid, Legend, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useCarePlan } from "@/api/hooks";
import { ToothCrossSection } from "@/components/dental/ToothCrossSection";
import { ErrorState, LoadingRows } from "@/components/ui/blocks";
import { Button, Toggle } from "@/components/ui/primitives";
import { stageColor } from "@/lib/format";

const PLAIN_STAGE: Record<string, { title: string; text: string }> = {
  I: { title: "Early gum disease", text: "A little of the bone that holds your teeth has been lost. With good cleaning this can stay stable for life." },
  II: { title: "Moderate gum disease", text: "Some of the supporting bone has been lost. Deep cleaning and regular check-ups can stop it getting worse." },
  III: { title: "Advanced gum disease", text: "A lot of the supporting bone has been lost around some teeth. Treatment now can save teeth that would otherwise loosen." },
  IV: { title: "Advanced gum disease with tooth loss", text: "Bone loss has already cost some teeth. A specialist plan helps protect the teeth you still have." },
};

/** Illustrative yearly bone-loss rate (% of root) by grade, used only when no measured rate exists. */
const DEFAULT_RATE: Record<string, number> = { A: 0.5, B: 1.5, C: 3.0 };

interface Habits {
  smoking: "current" | "quit" | "never";
  cigs: number;
  hba1c: number | null;
  homeCare: boolean;
  maintenance: boolean;
}

/**
 * Relative multipliers on the yearly rate. Directions follow the literature (smoking and poorly
 * controlled diabetes roughly double-to-triple periodontitis risk; daily interdental cleaning and
 * regular supportive care slow progression), but the exact values are illustrative.
 */
function multiplier(h: Habits): number {
  let m = 1;
  if (h.smoking === "current") m *= h.cigs >= 10 ? 2.2 : 1.7;
  if (h.hba1c !== null && h.hba1c > 6.5) m *= Math.min(1.8, 1 + 0.15 * (h.hba1c - 6.5));
  m *= h.homeCare ? 0.75 : 1.15;
  m *= h.maintenance ? 0.65 : 1.25;
  return m;
}

export default function PatientExplainerPage() {
  const { patientId } = useParams();
  const { data: plan, isLoading, error, refetch } = useCarePlan(patientId);

  const baseline: Habits | null = useMemo(() => {
    if (!plan) return null;
    const p = plan.patient;
    return {
      smoking: p.smoking_status === "current" ? "current" : p.smoking_status === "former" ? "quit" : "never",
      cigs: p.cigarettes_per_day ?? 10,
      hba1c: p.hba1c ?? (p.diabetic ? 7.5 : null),
      homeCare: false,
      maintenance: false,
    };
  }, [plan]);
  const [changes, setChanges] = useState<Partial<Habits>>({});

  if (isLoading || !baseline) return <LoadingRows rows={8} />;
  if (error || !plan) return <ErrorState error={error} retry={refetch} />;

  const chosen: Habits = { ...baseline, ...changes };
  const worst = [...plan.teeth].sort((a, b) => (b.bone_loss_pct ?? 0) - (a.bone_loss_pct ?? 0))[0];
  const start = worst?.bone_loss_pct ?? 0;
  const measured = plan.progression.filter((c) => c.reliable && c.velocity_pct_per_year !== null).map((c) => c.velocity_pct_per_year!);
  const baseRate = measured.length ? Math.max(0.2, Math.max(...measured)) : DEFAULT_RATE[plan.grade.grade ?? "B"] ?? 1.5;
  const rateNow = baseRate;
  const rateChosen = baseRate * (multiplier(chosen) / multiplier(baseline));
  const years = Array.from({ length: 11 }, (_, i) => i);
  const data = years.map((y) => ({
    year: y === 0 ? "Today" : `+${y} yr`,
    "If nothing changes": Math.min(100, +(start + rateNow * y).toFixed(1)),
    "With your changes": Math.min(100, +(start + rateChosen * y).toFixed(1)),
  }));
  const yearsTo50 = (rate: number) => (start >= 50 ? 0 : rate <= 0 ? null : Math.round((50 - start) / rate));
  const now50 = yearsTo50(rateNow);
  const chosen50 = yearsTo50(rateChosen);
  const stage = plan.stage ?? "I";
  const plain = PLAIN_STAGE[stage] ?? PLAIN_STAGE.I!;
  const counts = { healthy: 0, watch: 0, care: 0 };
  plan.teeth.forEach((t) => {
    const s = t.stage;
    if (!s || s === "I") counts.healthy++;
    else if (s === "II") counts.watch++;
    else counts.care++;
  });

  const set = (patch: Partial<Habits>) => setChanges((c) => ({ ...c, ...patch }));

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-6 flex items-center justify-between print:hidden">
        <Link to={`/app/patients/${patientId}/care-plan`} className="flex items-center gap-1 text-sm text-mist-400 hover:text-mist-100"><ArrowLeft className="h-4 w-4" /> Back to care plan</Link>
        <Button variant="outline" icon={<Printer className="h-4 w-4" />} onClick={() => window.print()}>Print for the patient</Button>
      </div>

      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="glass-strong overflow-hidden">
        <div className="grid items-center gap-8 p-8 md:grid-cols-[1fr_300px]">
          <div>
            <p className="label text-brand-300">Your gum health, explained</p>
            <h1 className="mt-2 text-4xl font-bold md:text-5xl">Hello {plan.patient.patient_name.split(" ")[0]},</h1>
            <p className="mt-4 text-2xl font-semibold" style={{ color: stageColor(stage) }}>{plain.title}</p>
            <p className="mt-2 max-w-xl text-lg text-mist-300">{plain.text}</p>
            <div className="mt-6 grid max-w-md grid-cols-3 gap-3 text-center">
              <div className="rounded-2xl bg-teal-400/10 p-3"><p className="font-display text-3xl font-bold text-teal-400">{counts.healthy}</p><p className="text-xs text-mist-400">teeth looking healthy</p></div>
              <div className="rounded-2xl bg-review-500/10 p-3"><p className="font-display text-3xl font-bold text-review-400">{counts.watch}</p><p className="text-xs text-mist-400">to watch</p></div>
              <div className="rounded-2xl bg-critical-500/10 p-3"><p className="font-display text-3xl font-bold text-critical-400">{counts.care}</p><p className="text-xs text-mist-400">need care</p></div>
            </div>
          </div>
          <div className="text-center">
            <ToothCrossSection boneLossPct={start} className="mx-auto h-72 w-auto" />
            <p className="mt-2 text-sm text-mist-400">Your most affected tooth{worst ? ` (${worst.tooth_id})` : ""}: the yellow line is where the bone sits now.</p>
          </div>
        </div>
      </motion.div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[360px_1fr]">
        <div className="glass space-y-5 p-6">
          <div>
            <p className="label text-brand-300">What if…</p>
            <p className="mt-1 text-sm text-mist-400">Change the habits below and watch the forecast on the right.</p>
          </div>
          {baseline.smoking === "current" && (
            <div className={clsx("rounded-2xl border p-4 transition", chosen.smoking === "quit" ? "border-teal-400/40 bg-teal-400/[0.06]" : "border-white/10")}>
              <Toggle label="I stop smoking" checked={chosen.smoking === "quit"} onChange={(v) => set({ smoking: v ? "quit" : "current" })} />
              <p className="mt-1 flex items-center gap-1.5 text-xs text-mist-500"><Cigarette className="h-3.5 w-3.5" /> Smokers lose bone around 2–3× faster.</p>
            </div>
          )}
          {baseline.hba1c !== null && (
            <div className="rounded-2xl border border-white/10 p-4">
              <div className="flex items-center justify-between text-sm text-mist-300">
                <span className="flex items-center gap-1.5"><Droplets className="h-4 w-4 text-brand-300" /> Blood sugar (HbA1c)</span>
                <span className="font-mono text-mist-100">{chosen.hba1c?.toFixed(1)}%</span>
              </div>
              <input type="range" min={5.5} max={11} step={0.1} value={chosen.hba1c ?? 7} onChange={(e) => set({ hba1c: Number(e.target.value) })} className="mt-2 w-full accent-cyan-400" aria-label="HbA1c" />
              <p className="mt-1 text-xs text-mist-500">Well-controlled diabetes (below 7%) protects your gums too.</p>
            </div>
          )}
          <div className={clsx("rounded-2xl border p-4 transition", chosen.homeCare ? "border-teal-400/40 bg-teal-400/[0.06]" : "border-white/10")}>
            <Toggle label="I clean between my teeth every day" checked={chosen.homeCare} onChange={(v) => set({ homeCare: v })} />
            <p className="mt-1 flex items-center gap-1.5 text-xs text-mist-500"><Sparkles className="h-3.5 w-3.5" /> Floss or small interdental brushes, once a day.</p>
          </div>
          <div className={clsx("rounded-2xl border p-4 transition", chosen.maintenance ? "border-teal-400/40 bg-teal-400/[0.06]" : "border-white/10")}>
            <Toggle label={`I come back every ${plan.recall.months} months`} checked={chosen.maintenance} onChange={(v) => set({ maintenance: v })} />
            <p className="mt-1 flex items-center gap-1.5 text-xs text-mist-500"><Stethoscope className="h-3.5 w-3.5" /> Professional cleaning keeps the disease under control.</p>
          </div>
        </div>

        <div className="glass p-6">
          <p className="label text-brand-300">Your next 10 years (illustration)</p>
          <div className="mt-2 grid gap-3 sm:grid-cols-2">
            <div className="rounded-2xl border border-critical-500/25 bg-critical-500/[0.05] p-4">
              <p className="text-sm text-mist-400">If nothing changes</p>
              <p className="font-display text-2xl font-bold text-critical-400">{now50 === null ? "Stable" : now50 === 0 ? "Already at risk" : `Tooth at risk in about ${now50} ${now50 === 1 ? "year" : "years"}`}</p>
            </div>
            <div className="rounded-2xl border border-teal-400/30 bg-teal-400/[0.06] p-4">
              <p className="text-sm text-mist-400">With your changes</p>
              <p className="font-display text-2xl font-bold text-teal-400">{chosen50 === null ? "Stable" : chosen50 === 0 ? "Already at risk" : chosen50 > 40 ? "Likely kept for life" : `At risk in about ${chosen50} ${chosen50 === 1 ? "year" : "years"}`}</p>
            </div>
          </div>
          <div className="mt-4 h-72">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
                <defs>
                  <linearGradient id="now" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="#ef4444" stopOpacity={0.35} /><stop offset="1" stopColor="#ef4444" stopOpacity={0} /></linearGradient>
                  <linearGradient id="chosen" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="#2dd4bf" stopOpacity={0.4} /><stop offset="1" stopColor="#2dd4bf" stopOpacity={0} /></linearGradient>
                </defs>
                <CartesianGrid stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="year" stroke="#5b6f8c" fontSize={11} tickLine={false} axisLine={false} />
                <YAxis unit="%" domain={[0, 100]} stroke="#5b6f8c" fontSize={11} tickLine={false} axisLine={false} />
                <ReferenceLine y={50} stroke="#ef4444" strokeDasharray="4 4" label={{ value: "tooth at risk", fill: "#f87171", fontSize: 10, position: "insideTopRight" }} />
                <Tooltip contentStyle={{ background: "#0a1628", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 12 }} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Area type="monotone" dataKey="If nothing changes" stroke="#ef4444" fill="url(#now)" strokeWidth={2} />
                <Area type="monotone" dataKey="With your changes" stroke="#2dd4bf" fill="url(#chosen)" strokeWidth={2.5} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-3 flex items-start gap-2 text-xs text-mist-500">
            <HeartPulse className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            This is a conversation aid, not a prediction. It starts from your most affected tooth ({start.toFixed(0)}% bone loss) and
            {measured.length ? " the rate measured between your X-rays" : ` a typical rate for Grade ${plan.grade.grade ?? "B"}`}, then applies
            illustrative effects of smoking, blood sugar, daily cleaning and regular visits.
          </p>
        </div>
      </div>

      <div className="glass mt-6 grid gap-4 p-6 md:grid-cols-3">
        {[
          { icon: Smile, title: "At home", text: "Brush twice a day and clean between your teeth once a day." },
          { icon: Stethoscope, title: "In the clinic", text: plan.steps.find((s) => s.step === 2)?.indicated ? "A deep clean below the gum line, then a check 6–8 weeks later." : "A professional clean and a check of your gums." },
          { icon: HeartPulse, title: "Keep it stable", text: `Come back every ${plan.recall.months} months so we can catch changes early.` },
        ].map((s) => (
          <div key={s.title} className="flex gap-3">
            <div className="h-fit rounded-xl bg-brand-400/10 p-2.5 text-brand-300"><s.icon className="h-5 w-5" /></div>
            <div><p className="font-display font-semibold">{s.title}</p><p className="text-sm text-mist-400">{s.text}</p></div>
          </div>
        ))}
      </div>
    </div>
  );
}
