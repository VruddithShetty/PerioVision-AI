import { motion } from "framer-motion";
import { ArrowLeft, Cigarette, Droplets, HeartPulse, Printer, Smile, Sparkles, Stethoscope } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { Area, AreaChart, CartesianGrid, Legend, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useCarePlan } from "@/api/hooks";
import { ToothCrossSection } from "@/components/dental/ToothCrossSection";
import { DemoDataBanner, ErrorState, LoadingRows } from "@/components/ui/blocks";
import { Button } from "@/components/ui/primitives";
import { stageColor } from "@/lib/format";

const PLAIN_STAGE: Record<string, { title: string; text: string }> = {
  I: { title: "Early gum disease", text: "A little of the bone that holds your teeth has been lost. With good cleaning this can stay stable for life." },
  II: { title: "Moderate gum disease", text: "Some of the supporting bone has been lost. Deep cleaning and regular check-ups can stop it getting worse." },
  III: { title: "Advanced gum disease", text: "A lot of the supporting bone has been lost around some teeth. Treatment now can save teeth that would otherwise loosen." },
  IV: { title: "Advanced gum disease with tooth loss", text: "Bone loss has already cost some teeth. A specialist plan helps protect the teeth you still have." },
};
const NO_STAGE = { title: "Not assessed yet", text: "Your X-ray could not be measured automatically. Your dentist will assess your gums directly." };

/**
 * Plain-language explainer for the patient. It only shows numbers that were measured:
 * the most affected tooth's bone level, and a forecast ONLY when two comparable X-rays
 * gave a rate of change larger than the measurement error. No typical rates, habit
 * multipliers or assumed lab values are used; habit advice is given in words.
 */
export default function PatientExplainerPage() {
  const { patientId } = useParams();
  const { data: plan, isLoading, error, refetch } = useCarePlan(patientId);

  if (isLoading) return <LoadingRows rows={8} />;
  if (error || !plan) return <ErrorState error={error} retry={refetch} />;

  const measuredTeeth = plan.teeth.filter((t) => t.bone_loss_pct !== null);
  const worst = [...measuredTeeth].sort((a, b) => b.bone_loss_pct! - a.bone_loss_pct!)[0];
  const start = worst?.bone_loss_pct ?? null;
  const rates = plan.progression
    .filter((c) => c.reliable && c.change_detectable && c.velocity_pct_per_year !== null)
    .map((c) => c.velocity_pct_per_year!);
  const rate = rates.length ? Math.max(...rates) : null;
  const forecast = start !== null && rate !== null && rate > 0;
  const data = forecast
    ? Array.from({ length: 11 }, (_, y) => ({ year: y === 0 ? "Today" : `+${y} yr`, "If nothing changes": Math.min(100, +(start + rate * y).toFixed(1)) }))
    : [];
  const yearsTo50 = forecast ? (start >= 50 ? 0 : Math.round((50 - start) / rate)) : null;
  const plain = plan.stage ? PLAIN_STAGE[plan.stage] ?? NO_STAGE : NO_STAGE;
  const counts = { healthy: 0, watch: 0, care: 0, unmeasured: 0 };
  plan.teeth.forEach((t) => {
    if (t.bone_loss_pct === null || !t.stage) counts.unmeasured++;
    else if (t.stage === "I") counts.healthy++;
    else if (t.stage === "II") counts.watch++;
    else counts.care++;
  });
  const p = plan.patient;
  const tips = [
    ...(p.smoking_status === "current"
      ? [{ icon: Cigarette, title: "Stopping smoking", text: "Smokers lose the bone around their teeth faster. Stopping is the single biggest thing you can do." }]
      : []),
    ...(p.diabetic
      ? [{ icon: Droplets, title: "Blood sugar", text: "Well-controlled diabetes (HbA1c below 7 %) protects your gums too. Ask your doctor about your latest result." }]
      : []),
    { icon: Sparkles, title: "Cleaning between your teeth", text: "Floss or small interdental brushes, once a day, remove the plaque that brushing misses." },
    { icon: Stethoscope, title: `Coming back every ${plan.recall.months} months`, text: "Professional cleaning keeps the disease under control and lets us catch changes early." },
  ];

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-6 flex items-center justify-between print:hidden">
        <Link to={`/app/patients/${patientId}/care-plan`} className="flex items-center gap-1 text-sm text-mist-400 hover:text-mist-100"><ArrowLeft className="h-4 w-4" /> Back to care plan</Link>
        <Button variant="outline" icon={<Printer className="h-4 w-4" />} onClick={() => window.print()}>Print for the patient</Button>
      </div>
      {plan.demo_data && <div className="print:hidden"><DemoDataBanner what="This explanation and its 10-year forecast" /></div>}

      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="glass-strong overflow-hidden">
        <div className="grid items-center gap-8 p-8 md:grid-cols-[1fr_300px]">
          <div>
            <p className="label text-brand-300">Your gum health, explained</p>
            <h1 className="mt-2 text-4xl font-bold md:text-5xl">Hello {p.patient_name.split(" ")[0]},</h1>
            <p className="mt-4 text-2xl font-semibold" style={{ color: stageColor(plan.stage) }}>{plain.title}</p>
            <p className="mt-2 max-w-xl text-lg text-mist-300">{plain.text}</p>
            <div className="mt-6 grid max-w-lg grid-cols-4 gap-3 text-center">
              <div className="rounded-2xl bg-teal-400/10 p-3"><p className="font-display text-3xl font-bold text-teal-400">{counts.healthy}</p><p className="text-xs text-mist-400">teeth looking healthy</p></div>
              <div className="rounded-2xl bg-review-500/10 p-3"><p className="font-display text-3xl font-bold text-review-400">{counts.watch}</p><p className="text-xs text-mist-400">to watch</p></div>
              <div className="rounded-2xl bg-critical-500/10 p-3"><p className="font-display text-3xl font-bold text-critical-400">{counts.care}</p><p className="text-xs text-mist-400">need care</p></div>
              <div className="rounded-2xl bg-white/[0.04] p-3"><p className="font-display text-3xl font-bold text-mist-300">{counts.unmeasured}</p><p className="text-xs text-mist-400">checked by your dentist</p></div>
            </div>
          </div>
          <div className="text-center">
            {start !== null ? (
              <>
                <ToothCrossSection boneLossPct={start} className="mx-auto h-72 w-auto" />
                <p className="mt-2 text-sm text-mist-400">Your most affected tooth ({worst!.tooth_id}): the yellow line is where the bone sits now.</p>
              </>
            ) : (
              <p className="text-sm text-mist-400">No tooth on this X-ray could be measured automatically.</p>
            )}
          </div>
        </div>
      </motion.div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[360px_1fr]">
        <div className="glass space-y-4 p-6">
          <p className="label text-brand-300">What helps</p>
          {tips.map((t) => (
            <div key={t.title} className="flex gap-3">
              <div className="h-fit rounded-xl bg-brand-400/10 p-2.5 text-brand-300"><t.icon className="h-5 w-5" /></div>
              <div><p className="font-display font-semibold">{t.title}</p><p className="text-sm text-mist-400">{t.text}</p></div>
            </div>
          ))}
        </div>

        <div className="glass p-6">
          <p className="label text-brand-300">Your next 10 years</p>
          {forecast ? (
            <>
              <div className="mt-2 rounded-2xl border border-critical-500/25 bg-critical-500/[0.05] p-4">
                <p className="text-sm text-mist-400">If nothing changes</p>
                <p className="font-display text-2xl font-bold text-critical-400">{yearsTo50 === 0 ? "Already at risk" : `Tooth at risk in about ${yearsTo50} ${yearsTo50 === 1 ? "year" : "years"}`}</p>
              </div>
              <div className="mt-4 h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={data} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
                    <defs>
                      <linearGradient id="now" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="#ef4444" stopOpacity={0.35} /><stop offset="1" stopColor="#ef4444" stopOpacity={0} /></linearGradient>
                    </defs>
                    <CartesianGrid stroke="rgba(255,255,255,0.05)" />
                    <XAxis dataKey="year" stroke="#5b6f8c" fontSize={11} tickLine={false} axisLine={false} />
                    <YAxis unit="%" domain={[0, 100]} stroke="#5b6f8c" fontSize={11} tickLine={false} axisLine={false} />
                    <ReferenceLine y={50} stroke="#ef4444" strokeDasharray="4 4" label={{ value: "tooth at risk", fill: "#f87171", fontSize: 10, position: "insideTopRight" }} />
                    <Tooltip contentStyle={{ background: "#0a1628", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 12 }} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Area type="monotone" dataKey="If nothing changes" stroke="#ef4444" fill="url(#now)" strokeWidth={2} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
              <p className="mt-3 flex items-start gap-2 text-xs text-mist-500">
                <HeartPulse className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                A straight-line continuation of the change measured between your X-rays ({rate.toFixed(1)} % of root length per year,
                starting from {start.toFixed(0)} %). It is a conversation aid, not a prediction: treatment and the habits on the left can slow it.
              </p>
            </>
          ) : (
            <div className="mt-3 rounded-2xl border border-white/10 p-5 text-sm text-mist-300">
              <p className="font-semibold text-mist-100">We cannot draw a forecast yet.</p>
              <p className="mt-1 text-mist-400">
                {start === null
                  ? "Your X-ray could not be measured automatically."
                  : "A forecast needs two comparable X-rays taken some time apart that show a change larger than the measurement error. Until then we only show where the bone is today."}
              </p>
            </div>
          )}
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
