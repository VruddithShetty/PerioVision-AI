import clsx from "clsx";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, ClipboardList, Copy, Keyboard, Save, Scale } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "@/api/client";
import { usePatient, usePerioCharts, useSaveChart } from "@/api/hooks";
import type { PerioChart, ToothChart } from "@/api/types";
import { EmptyState, ErrorState, LoadingRows, PageHeader, Stat } from "@/components/ui/blocks";
import { Badge, Button, Card, CardTitle, Input } from "@/components/ui/primitives";
import { fmtDate, stageColor } from "@/lib/format";
import { useCan } from "@/store/auth";

const UPPER = ["18", "17", "16", "15", "14", "13", "12", "11", "21", "22", "23", "24", "25", "26", "27", "28"];
const LOWER = ["48", "47", "46", "45", "44", "43", "42", "41", "31", "32", "33", "34", "35", "36", "37", "38"];
const ALL = [...UPPER, ...LOWER];
const SITE_NAMES = ["DB", "B", "MB", "DL", "L", "ML"];

const blank = (): ToothChart => ({ pd: [0, 0, 0, 0, 0, 0], rec: [0, 0, 0, 0, 0, 0], bop: Array(6).fill(false), plaque: Array(6).fill(false), mobility: 0, furcation: 0, missing: false });

/** Site indices in on-screen order. The patient's right side is drawn on the left, so distal comes first in quadrants 1 and 4. */
function order(tooth: string, face: "b" | "l"): number[] {
  const distalFirst = tooth[0] === "1" || tooth[0] === "4";
  const b = distalFirst ? [0, 1, 2] : [2, 1, 0];
  return face === "b" ? b : b.map((i) => i + 3);
}

const pdTone = (v: number) => (v >= 6 ? "text-critical-400" : v >= 4 ? "text-review-400" : "text-mist-100");

function Cell({ value, onChange, register, next, tone, label, min = 0, max = 15 }: {
  value: number;
  onChange: (v: number) => void;
  register: (el: HTMLInputElement | null) => void;
  next: () => void;
  tone?: string;
  label: string;
  min?: number;
  max?: number;
}) {
  return (
    <input
      ref={register}
      inputMode="numeric"
      aria-label={label}
      value={value === 0 ? "" : value}
      placeholder="0"
      onFocus={(e) => e.target.select()}
      onChange={(e) => {
        const raw = e.target.value.replace(/[^\d-]/g, "");
        const n = raw === "" || raw === "-" ? 0 : Math.max(min, Math.min(max, Number(raw)));
        onChange(n);
        if (raw.length >= 1 && raw !== "-" && !(raw === "1" && max >= 10)) next();
      }}
      className={clsx("h-7 w-[22px] rounded-md bg-ink-900/80 text-center font-mono text-xs outline-none ring-1 ring-white/5 placeholder:text-mist-500/40 focus:ring-brand-400", tone)}
    />
  );
}

function PocketGraph({ t, tooth, face }: { t: ToothChart; tooth: string; face: "b" | "l" }) {
  const idx = order(tooth, face);
  const xs = [8, 20, 32];
  const scale = 3; // px per mm
  const gum = 18;
  return (
    <svg viewBox="0 0 40 64" className="h-16 w-10" aria-hidden>
      {/* root silhouette */}
      <path d={face === "b" ? "M10 4 h20 l-3 58 h-14 z" : "M10 60 h20 l-3 -58 h-14 z"} fill="#e6f1ff" opacity="0.08" />
      {(() => {
        const pts = idx.map((i, k) => `${xs[k]},${gum + t.rec[i]! * scale}`).join(" ");
        const pocket = idx.map((i, k) => `${xs[k]},${gum + (t.rec[i]! + t.pd[i]!) * scale}`).join(" ");
        return (
          <>
            <polyline points={pts} fill="none" stroke="#f472b6" strokeWidth="1.5" />
            <polyline points={pocket} fill="none" stroke="#22d3ee" strokeWidth="1" strokeDasharray="2 1.5" />
            {idx.map((i, k) => (
              <line
                key={i}
                x1={xs[k]}
                x2={xs[k]}
                y1={gum + t.rec[i]! * scale}
                y2={gum + (t.rec[i]! + t.pd[i]!) * scale}
                stroke={t.pd[i]! >= 6 ? "#ef4444" : t.pd[i]! >= 4 ? "#fbbf24" : "#2dd4bf"}
                strokeWidth="4"
                strokeLinecap="round"
              />
            ))}
          </>
        );
      })()}
    </svg>
  );
}

function ToothColumn({ tooth, t, set, reg, focusNext, readOnly, previous }: {
  tooth: string;
  t: ToothChart;
  set: (patch: Partial<ToothChart>) => void;
  reg: (key: string) => (el: HTMLInputElement | null) => void;
  focusNext: (key: string) => void;
  readOnly: boolean;
  previous?: ToothChart;
}) {
  const setArr = (field: "pd" | "rec", i: number, v: number) => {
    const arr = [...t[field]];
    arr[i] = v;
    set({ [field]: arr } as Partial<ToothChart>);
  };
  const toggle = (field: "bop" | "plaque", i: number) => {
    const arr = [...t[field]];
    arr[i] = !arr[i];
    set({ [field]: arr } as Partial<ToothChart>);
  };
  const maxPd = Math.max(...t.pd);
  const worsened = previous && t.pd.some((v, i) => v - (previous.pd[i] ?? 0) >= 2);

  const face = (f: "b" | "l") => (
    <div className="space-y-1">
      <div className="flex justify-center gap-0.5">
        {order(tooth, f).map((i) => (
          <Cell key={i} label={`Tooth ${tooth} ${SITE_NAMES[i]} probing depth`} value={t.pd[i]!} tone={pdTone(t.pd[i]!)} onChange={(v) => setArr("pd", i, v)} register={reg(`${tooth}-pd-${i}`)} next={() => focusNext(`${tooth}-pd-${i}`)} />
        ))}
      </div>
      <div className="flex justify-center gap-0.5">
        {order(tooth, f).map((i) => (
          <Cell key={i} label={`Tooth ${tooth} ${SITE_NAMES[i]} recession`} value={t.rec[i]!} min={-5} tone="text-pink-300" onChange={(v) => setArr("rec", i, v)} register={reg(`${tooth}-rec-${i}`)} next={() => focusNext(`${tooth}-rec-${i}`)} />
        ))}
      </div>
      <div className="flex justify-center gap-[7px] py-0.5">
        {order(tooth, f).map((i) => (
          <button key={i} type="button" disabled={readOnly} onClick={() => toggle("bop", i)} aria-label={`Bleeding ${tooth} ${SITE_NAMES[i]}`} aria-pressed={t.bop[i]} className={clsx("h-3 w-3 rounded-full ring-1 transition", t.bop[i] ? "bg-critical-500 ring-critical-400" : "ring-white/15 hover:ring-critical-400/60")} />
        ))}
      </div>
      <div className="flex justify-center gap-[7px]">
        {order(tooth, f).map((i) => (
          <button key={i} type="button" disabled={readOnly} onClick={() => toggle("plaque", i)} aria-label={`Plaque ${tooth} ${SITE_NAMES[i]}`} aria-pressed={t.plaque[i]} className={clsx("h-2.5 w-2.5 rounded-sm ring-1 transition", t.plaque[i] ? "bg-review-400 ring-review-400" : "ring-white/10 hover:ring-review-400/60")} />
        ))}
      </div>
    </div>
  );

  return (
    <div className={clsx("flex w-[76px] shrink-0 flex-col items-center gap-1 rounded-xl border px-1 py-2 transition", t.missing ? "border-dashed border-white/10 opacity-40" : maxPd >= 6 ? "border-critical-500/30 bg-critical-500/[0.04]" : maxPd >= 4 ? "border-review-500/25 bg-review-500/[0.03]" : "border-white/[0.06]")}>
      <button type="button" disabled={readOnly} onClick={() => set({ missing: !t.missing })} className="font-mono text-sm font-bold text-mist-100 hover:text-brand-300" title="Click to mark missing">
        {tooth}
        {worsened && <span className="ml-0.5 text-critical-400" title="Pocket deepened ≥ 2 mm since the last chart">▲</span>}
      </button>
      {!t.missing && (
        <>
          {face("b")}
          <PocketGraph t={t} tooth={tooth} face="b" />
          <div className="flex gap-0.5">
            <select disabled={readOnly} aria-label={`Mobility ${tooth}`} value={t.mobility} onChange={(e) => set({ mobility: Number(e.target.value) })} className="h-6 w-[33px] rounded bg-ink-900 text-center text-[10px] text-mist-300">
              {[0, 1, 2, 3].map((v) => <option key={v} value={v}>M{v}</option>)}
            </select>
            <select disabled={readOnly} aria-label={`Furcation ${tooth}`} value={t.furcation} onChange={(e) => set({ furcation: Number(e.target.value) })} className="h-6 w-[33px] rounded bg-ink-900 text-center text-[10px] text-mist-300">
              {[0, 1, 2, 3].map((v) => <option key={v} value={v}>F{v}</option>)}
            </select>
          </div>
          <PocketGraph t={t} tooth={tooth} face="l" />
          {face("l")}
        </>
      )}
    </div>
  );
}

function liveSummary(teeth: Record<string, ToothChart>) {
  let sites = 0, bop = 0, plaque = 0, d4 = 0, d6 = 0, calSum = 0;
  for (const t of Object.values(teeth)) {
    if (t.missing || t.pd.every((p) => p === 0)) continue; // uncharted teeth don't dilute the scores
    sites += 6;
    t.pd.forEach((p, i) => {
      bop += t.bop[i] ? 1 : 0;
      plaque += t.plaque[i] ? 1 : 0;
      d4 += p >= 4 ? 1 : 0;
      d6 += p >= 6 ? 1 : 0;
      calSum += Math.max(0, p + (t.rec[i] ?? 0));
    });
  }
  return {
    bop: sites ? (100 * bop) / sites : 0,
    plaque: sites ? (100 * plaque) / sites : 0,
    d4, d6,
    meanCal: sites ? calSum / sites : 0,
  };
}

export default function PerioChartPage() {
  const { patientId } = useParams();
  const { data: patient } = usePatient(patientId);
  const { data: charts, isLoading, error, refetch } = usePerioCharts(patientId);
  const save = useSaveChart(patientId);
  const canWrite = useCan("chart:write");
  const [teeth, setTeeth] = useState<Record<string, ToothChart>>(() => Object.fromEntries(ALL.map((t) => [t, blank()])));
  const [examDate, setExamDate] = useState(new Date().toISOString().slice(0, 10));
  const [viewing, setViewing] = useState<PerioChart | null>(null);
  const [saved, setSaved] = useState<PerioChart | null>(null);
  const refs = useRef<Map<string, HTMLInputElement>>(new Map());
  const orderKeys = useMemo(() => ALL.flatMap((t) => [...order(t, "b"), ...order(t, "l")].map((i) => `${t}-pd-${i}`)), []);

  const latest = charts?.[0];
  useEffect(() => {
    if (latest && !viewing) setViewing(latest);
  }, [latest, viewing]);

  const copyForward = () => {
    if (!latest) return;
    setTeeth(Object.fromEntries(ALL.map((t) => [t, latest.teeth[t] ? { ...blank(), ...latest.teeth[t] } : blank()])));
  };

  const focusNext = (key: string) => {
    const i = orderKeys.indexOf(key);
    if (i >= 0 && i < orderKeys.length - 1) refs.current.get(orderKeys[i + 1]!)?.focus();
  };
  const reg = (key: string) => (el: HTMLInputElement | null) => {
    if (el) refs.current.set(key, el);
  };

  const live = liveSummary(teeth);
  const shown = saved ?? viewing;

  const submit = async () => {
    const payload = Object.fromEntries(Object.entries(teeth).filter(([, t]) => t.missing || t.pd.some((v) => v > 0)));
    const res = await save.mutateAsync({ exam_date: examDate, teeth: payload });
    setSaved(res);
    setViewing(res);
    refetch();
  };

  const row = (ids: string[]) => (
    <div className="flex gap-1.5">
      {ids.slice(0, 8).map((id) => (
        <ToothColumn key={id} tooth={id} t={teeth[id]!} set={(patch) => setTeeth((s) => ({ ...s, [id]: { ...s[id]!, ...patch } }))} reg={reg} focusNext={focusNext} readOnly={!canWrite} previous={latest?.teeth[id]} />
      ))}
      <div className="w-px shrink-0 bg-white/10" />
      {ids.slice(8).map((id) => (
        <ToothColumn key={id} tooth={id} t={teeth[id]!} set={(patch) => setTeeth((s) => ({ ...s, [id]: { ...s[id]!, ...patch } }))} reg={reg} focusNext={focusNext} readOnly={!canWrite} previous={latest?.teeth[id]} />
      ))}
    </div>
  );

  return (
    <div>
      <PageHeader
        eyebrow="Periodontal chart"
        title={patient?.patient_name ?? `Patient ${patientId}`}
        subtitle="Six-point probing with automatic attachment-loss, bleeding and staging. Each tooth is cross-checked against the X-ray AI so disagreements stand out."
        actions={
          <>
            <Link to={`/app/patients/${patientId}/care-plan`}><Button variant="outline" icon={<ClipboardList className="h-4 w-4" />}>Care plan</Button></Link>
            {canWrite && latest && <Button variant="subtle" icon={<Copy className="h-4 w-4" />} onClick={copyForward}>Copy last chart</Button>}
          </>
        }
      />
      {error && <ErrorState error={error} retry={refetch} />}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <Stat label="Bleeding on probing" value={`${live.bop.toFixed(0)}%`} tone={live.bop >= 30 ? "critical" : live.bop >= 10 ? "review" : "ok"} hint="≥ 10 % = inflamed" />
        <Stat label="Plaque score" value={`${live.plaque.toFixed(0)}%`} tone={live.plaque >= 30 ? "review" : "ok"} />
        <Stat label="Sites ≥ 4 mm" value={live.d4} tone={live.d4 ? "review" : "ok"} />
        <Stat label="Sites ≥ 6 mm" value={live.d6} tone={live.d6 ? "critical" : "ok"} />
        <Stat label="Mean CAL" value={`${live.meanCal.toFixed(1)} mm`} hint="CAL = probing depth + recession" />
      </div>

      <Card className="mt-6">
        <CardTitle
          icon={<Keyboard className="h-4 w-4" />}
          action={
            canWrite && (
              <div className="flex items-center gap-2">
                <Input type="date" value={examDate} onChange={(e) => setExamDate(e.target.value)} className="py-1.5 text-xs" aria-label="Exam date" />
                <Button icon={<Save className="h-4 w-4" />} loading={save.isPending} onClick={submit}>Save chart</Button>
              </div>
            )
          }
        >
          New examination
        </CardTitle>
        <p className="mb-3 text-xs text-mist-400">
          Type one digit per site: the cursor jumps to the next site. Rows per tooth: probing depth, recession (pink), bleeding (red dot), plaque (amber square).
          Click a tooth number to mark it missing. ▲ = pocket deepened by 2 mm or more since the last chart.
        </p>
        {save.error && <div className="mb-3"><ErrorState error={save.error as ApiError} /></div>}
        <div className="overflow-x-auto pb-2">
          <div className="w-fit space-y-4">
            <div><p className="label mb-1.5">Maxilla · buccal top / palatal bottom</p>{row(UPPER)}</div>
            <div><p className="label mb-1.5">Mandible · buccal top / lingual bottom</p>{row(LOWER)}</div>
          </div>
        </div>
      </Card>

      <div className="mt-6 grid gap-6 xl:grid-cols-[1.3fr_1fr]">
        <Card strong>
          <CardTitle icon={<Scale className="h-4 w-4" />}>Clinical vs radiographic concordance</CardTitle>
          {isLoading ? <LoadingRows /> : !shown ? (
            <EmptyState title="No saved chart yet" body="Save a chart to compare probing with the X-ray AI tooth by tooth." />
          ) : !shown.concordance.length ? (
            <EmptyState title="Nothing to compare" body="Concordance needs a radiograph analysis with numbered teeth for this patient." />
          ) : (
            <div className="space-y-2">
              <AnimatePresence>
                {shown.concordance.map((c) => (
                  <motion.div key={c.tooth_id} layout initial={{ opacity: 0 }} animate={{ opacity: 1 }} className={clsx("rounded-xl border p-3", c.status === "agree" ? "border-white/[0.06]" : "border-review-500/35 bg-review-500/[0.06]")}>
                    <div className="flex flex-wrap items-center gap-3 text-sm">
                      <span className="font-mono font-bold">{c.tooth_id}</span>
                      <span>Probing: <b style={{ color: stageColor(c.clinical_stage) }}>Stage {c.clinical_stage ?? "–"}</b> <span className="text-mist-500">({c.interdental_cal_mm} mm CAL)</span></span>
                      <span>X-ray: <b style={{ color: stageColor(c.radiographic_stage) }}>Stage {c.radiographic_stage ?? "–"}</b> <span className="text-mist-500">({c.bone_loss_pct?.toFixed(0) ?? "–"}%)</span></span>
                      <span className="ml-auto">{c.status === "agree" ? <Badge tone="ok"><CheckCircle2 className="h-3 w-3" /> agree</Badge> : <Badge tone="review"><AlertTriangle className="h-3 w-3" /> {c.status}</Badge>}</span>
                    </div>
                    {c.hint && <p className="mt-1.5 text-xs text-mist-300">{c.hint}</p>}
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          )}
        </Card>
        <Card>
          <CardTitle>Chart history</CardTitle>
          {!charts?.length ? <EmptyState title="No charts yet" /> : (
            <ul className="space-y-2">
              {charts.map((c) => (
                <li key={c.chart_id}>
                  <button onClick={() => { setViewing(c); setSaved(null); }} className={clsx("w-full rounded-xl border p-3 text-left transition", shown?.chart_id === c.chart_id ? "border-brand-400/40 bg-brand-400/[0.06]" : "border-white/[0.06] hover:border-white/15")}>
                    <div className="flex items-center justify-between">
                      <span className="font-medium">{fmtDate(c.exam_date)}</span>
                      <span className="text-xs" style={{ color: stageColor(c.summary.clinical_stage) }}>Stage {c.summary.clinical_stage ?? "–"}</span>
                    </div>
                    <p className="mt-1 text-xs text-mist-400">
                      BOP {c.summary.bop_pct ?? "–"}% · {c.summary.sites_pd_4_plus} sites ≥ 4 mm · {c.summary.gingival_status}
                    </p>
                    <p className="text-[11px] text-mist-500">by {c.examiner_name ?? "–"} · {c.concordance.filter((x) => x.status !== "agree").length} discordant teeth</p>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-3 text-[11px] text-mist-500">
            Clinical stage uses the worst interdental CAL (1–2 mm I, 3–4 mm II, ≥ 5 mm III; 2017 AAP/EFP).
          </p>
        </Card>
      </div>
    </div>
  );
}
