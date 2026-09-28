import clsx from "clsx";
import { motion } from "framer-motion";
import { AlarmClock, CalendarCheck2, CalendarClock, ChevronRight, Send } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useRecall } from "@/api/hooks";
import type { RecallRow } from "@/api/types";
import { EmptyState, ErrorState, LoadingRows, PageHeader, Stat, Tabs } from "@/components/ui/blocks";
import { Badge } from "@/components/ui/primitives";
import { fmtDate, RISK_TONE, stageColor } from "@/lib/format";

type Filter = "all" | "overdue" | "due soon" | "scheduled";

function dueLabel(r: RecallRow) {
  if (r.days_until_due === null) return "no visit yet";
  if (r.days_until_due < 0) return `${-r.days_until_due} days overdue`;
  if (r.days_until_due === 0) return "due today";
  return `in ${r.days_until_due} days`;
}

export default function RecallBoardPage() {
  const { data, isLoading, error, refetch } = useRecall();
  const [filter, setFilter] = useState<Filter>("all");
  const rows = useMemo(() => (data?.data ?? []).filter((r) => filter === "all" || r.status === filter), [data, filter]);
  const meta = data?.meta as { overdue?: number; due_soon?: number } | undefined;

  return (
    <div>
      <PageHeader
        eyebrow="Supportive periodontal care"
        title="Recall board"
        subtitle="Every patient's next maintenance visit, set from their stage, grade, bleeding score and progression (3, 4 or 6 months). Overdue high-risk patients come first."
        actions={<Tabs value={filter} onChange={setFilter} items={[{ value: "all", label: "All" }, { value: "overdue", label: "Overdue" }, { value: "due soon", label: "Due ≤ 30 days" }, { value: "scheduled", label: "Scheduled" }]} />}
      />
      <div className="grid gap-4 sm:grid-cols-3">
        <Stat label="Overdue" value={meta?.overdue ?? 0} tone="critical" icon={<AlarmClock className="h-5 w-5" />} />
        <Stat label="Due in 30 days" value={meta?.due_soon ?? 0} tone="review" icon={<CalendarClock className="h-5 w-5" />} />
        <Stat label="On schedule" value={(data?.data.length ?? 0) - (meta?.overdue ?? 0) - (meta?.due_soon ?? 0)} tone="ok" icon={<CalendarCheck2 className="h-5 w-5" />} />
      </div>
      <div className="mt-6">
        {error ? <ErrorState error={error} retry={refetch} /> : isLoading ? <LoadingRows /> : !rows.length ? (
          <EmptyState title="Nobody here" body="No patients match this filter." />
        ) : (
          <div className="space-y-2">
            {rows.map((r, i) => (
              <motion.div key={r.patient_id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}>
                <Link to={`/app/patients/${r.patient_id}/care-plan`} className={clsx("glass group flex flex-wrap items-center gap-4 p-4 transition hover:border-brand-400/30", r.status === "overdue" && "border-critical-500/30")}>
                  <div className={clsx("flex h-12 w-12 flex-col items-center justify-center rounded-xl font-mono text-xs", r.status === "overdue" ? "bg-critical-500/15 text-critical-400" : r.status === "due soon" ? "bg-review-500/15 text-review-400" : "bg-teal-400/10 text-teal-400")}>
                    <span className="text-base font-bold">{r.interval_months}</span>mo
                  </div>
                  <div className="min-w-[180px] flex-1">
                    <p className="font-medium text-mist-100">{r.patient_name}</p>
                    <p className="font-mono text-xs text-brand-300">{r.pseudo_id}</p>
                  </div>
                  <div className="text-sm">
                    <p className="text-mist-400">Next visit</p>
                    <p className="font-medium">{r.next_due ? fmtDate(r.next_due) : "–"} <span className={clsx("text-xs", r.status === "overdue" ? "text-critical-400" : "text-mist-500")}>· {dueLabel(r)}</span></p>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Badge><span style={{ color: stageColor(r.stage) }}>Stage {r.stage ?? "–"}</span></Badge>
                    <Badge>Grade {r.grade ?? "–"}</Badge>
                    {r.risk && <Badge tone={RISK_TONE[r.risk] ?? "neutral"}>{r.risk} risk</Badge>}
                    {r.referral_suggested && <Badge tone="review"><Send className="h-3 w-3" /> referral</Badge>}
                  </div>
                  <ChevronRight className="h-4 w-4 text-mist-500 transition group-hover:translate-x-0.5 group-hover:text-brand-300" />
                </Link>
              </motion.div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
