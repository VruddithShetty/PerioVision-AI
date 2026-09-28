import { AlertTriangle, ArrowDownRight, ArrowUpRight, Link2, Minus, Zap } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAnalysis, usePatient, useProgression } from "@/api/hooks";
import type { Comparison } from "@/api/types";
import { ToothTrendChart } from "@/components/charts/Charts";
import { BeforeAfterSlider } from "@/components/dental/BeforeAfterSlider";
import { EmptyState, ErrorState, LoadingRows, PageHeader, Stat, Table } from "@/components/ui/blocks";
import { Badge, Card, CardTitle, Select } from "@/components/ui/primitives";
import { fmtDate, PROGRESSION_TONE } from "@/lib/format";

function VelocityChip({ c }: { c: Comparison }) {
  const Icon = c.raw_label === "rapidly progressing" ? Zap : c.raw_label === "progressing" ? ArrowUpRight : c.raw_label === "improved" ? ArrowDownRight : Minus;
  return (
    <Badge tone={PROGRESSION_TONE[c.label] ?? "neutral"}>
      <Icon className="h-3 w-3" /> {c.label}
    </Badge>
  );
}

export default function ProgressionPage() {
  const { patientId } = useParams();
  const { data: patient } = usePatient(patientId);
  const { data, isLoading, error, refetch } = useProgression(patientId);
  const [highlight, setHighlight] = useState<string | null>(null);
  const [fromId, setFromId] = useState("");
  const [toId, setToId] = useState("");

  useEffect(() => {
    if (data?.visits.length && !toId) {
      setToId(data.visits[data.visits.length - 1]!.analysis_id);
      setFromId(data.visits[Math.max(0, data.visits.length - 2)]!.analysis_id);
    }
  }, [data, toId]);

  const { data: fromA } = useAnalysis(fromId || undefined);
  const { data: toA } = useAnalysis(toId || undefined);
  const latest = useMemo(() => [...(data?.latest ?? [])].sort((a, b) => (b.velocity_pct_per_year ?? -99) - (a.velocity_pct_per_year ?? -99)), [data]);

  if (isLoading) return <LoadingRows rows={8} />;
  if (error || !data) return <ErrorState error={error} retry={refetch} />;

  const labels = data.summary.labels;
  return (
    <div>
      <PageHeader
        eyebrow="Progression timeline"
        title={patient?.patient_name ?? `Patient ${patientId}`}
        subtitle="Teeth are matched across visits by FDI number (or by position after radiograph registration). Comparisons that can't be trusted are labelled, never silently computed."
      />
      {data.visits.length < 2 ? (
        <EmptyState title="Only one visit so far" body="Progression needs at least two analysed radiographs of this patient." action={<Link to={`/app/analysis/new?patient=${patientId}`} className="text-brand-300 hover:underline">Analyse another radiograph →</Link>} />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Stat label="Visits" value={data.summary.visits} hint={`${fmtDate(data.visits[0]!.visit_date)} → ${fmtDate(data.visits[data.visits.length - 1]!.visit_date)}`} />
            <Stat label="Progressing" value={(labels["progressing"] ?? 0) + (labels["rapidly progressing"] ?? 0)} tone="review" hint={`${labels["rapidly progressing"] ?? 0} rapidly`} />
            <Stat label="Stable / improved" value={(labels["stable"] ?? 0) + (labels["improved"] ?? 0)} tone="ok" />
            <Stat label="Fastest reliable rate" value={data.summary.max_reliable_velocity_pct_per_year === null ? "–" : `${data.summary.max_reliable_velocity_pct_per_year}%/yr`} tone={data.summary.unreliable_comparisons ? "review" : "brand"} hint={`${data.summary.unreliable_comparisons} unreliable comparisons`} />
          </div>

          <div className="mt-6 grid gap-6 xl:grid-cols-[1.2fr_1fr]">
            <Card>
              <CardTitle
                action={
                  <div className="flex gap-2">
                    <Select value={fromId} onChange={(e) => setFromId(e.target.value)} className="py-1.5 text-xs" aria-label="Earlier visit">
                      {data.visits.map((v) => <option key={v.analysis_id} value={v.analysis_id}>{v.visit_date}</option>)}
                    </Select>
                    <Select value={toId} onChange={(e) => setToId(e.target.value)} className="py-1.5 text-xs" aria-label="Later visit">
                      {data.visits.map((v) => <option key={v.analysis_id} value={v.analysis_id}>{v.visit_date}</option>)}
                    </Select>
                  </div>
                }
              >
                Before / after
              </CardTitle>
              <BeforeAfterSlider beforeUrl={fromA?.images.annotated} afterUrl={toA?.images.annotated} beforeLabel={fromA?.visit_date ?? "earlier"} afterLabel={toA?.visit_date ?? "later"} />
              {toA?.alignment && (
                <p className="mt-2 flex items-center gap-1.5 text-xs text-mist-500">
                  <Link2 className="h-3 w-3" /> Registration with the previous visit: {toA.alignment.status} (score {toA.alignment.confidence.toFixed(2)})
                </p>
              )}
            </Card>
            <Card>
              <CardTitle>Bone loss per tooth over time</CardTitle>
              <ToothTrendChart series={data.series} highlight={highlight} />
            </Card>
          </div>

          <Card className="mt-6">
            <CardTitle>Latest comparison</CardTitle>
            <Table head={["Tooth", "Match", "Change", "Rate", "Status", "Reliability"]}>
              {latest.map((c) => (
                <tr key={c.tooth_id} className="transition hover:bg-white/[0.03]" onMouseEnter={() => setHighlight(c.tooth_id)} onMouseLeave={() => setHighlight(null)}>
                  <td className="px-4 py-3 font-mono font-semibold">{c.tooth_id}</td>
                  <td className="px-4 py-3 text-xs text-mist-400">{c.match_method === "tooth_number" ? "FDI number" : "position"}</td>
                  <td className="px-4 py-3">
                    <span className="text-mist-400">{c.previous_bone_loss_pct.toFixed(1)}%</span> → <span className="font-semibold">{c.current_bone_loss_pct.toFixed(1)}%</span>
                    <span className={c.delta_pct > 0 ? "ml-2 text-review-400" : "ml-2 text-teal-400"}>({c.delta_pct > 0 ? "+" : ""}{c.delta_pct})</span>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs">{c.velocity_pct_per_year === null ? "–" : `${c.velocity_pct_per_year}%/yr`}</td>
                  <td className="px-4 py-3"><VelocityChip c={c} /></td>
                  <td className="px-4 py-3 text-xs">
                    {c.reliable ? (
                      <span className="text-teal-400">reliable</span>
                    ) : (
                      <span className="flex items-center gap-1 text-review-400" title={c.reliability_reasons.join("\n")}>
                        <AlertTriangle className="h-3.5 w-3.5" /> {c.reliability_reasons[0]}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </Table>
          </Card>
        </>
      )}
    </div>
  );
}
