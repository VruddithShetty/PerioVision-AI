import { motion } from "framer-motion";
import { AlertTriangle, ArrowUpRight, ClipboardList, ScanLine, ShieldAlert, Stethoscope, Users } from "lucide-react";
import { Link } from "react-router-dom";
import { useDashboard } from "@/api/hooks";
import { RiskDonut, StageBars } from "@/components/charts/Charts";
import { SystemStatusCard } from "@/components/SystemStatusCard";
import { EmptyState, ErrorState, PageHeader, Stat } from "@/components/ui/blocks";
import { Badge, Button, Card, CardTitle, Skeleton } from "@/components/ui/primitives";
import { fmtDateTime, REVIEW_LABEL, REVIEW_TONE } from "@/lib/format";
import { useAuth, useCan } from "@/store/auth";

const greeting = () => {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
};

export default function DashboardPage() {
  const { data, isLoading, error, refetch } = useDashboard();
  const user = useAuth((s) => s.user);
  const canRun = useCan("analysis:run");
  const clinical = data?.analyses_total !== undefined;

  return (
    <div>
      <PageHeader
        eyebrow="Dashboard"
        title={`${greeting()}, ${user?.name?.split(" ")[0] ?? ""}`}
        subtitle={clinical ? "Today's periodontal workload, flagged cases and system integrity at a glance." : "Security and integrity overview for your role."}
        actions={
          canRun && (
            <Link to="/app/analysis/new">
              <Button icon={<ScanLine className="h-4 w-4" />}>New analysis</Button>
            </Link>
          )
        }
      />
      {error && <ErrorState error={error} retry={refetch} />}

      {clinical || isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {isLoading ? (
            Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-32" />)
          ) : (
            <>
              <Stat label="Patients" value={data?.patients ?? 0} icon={<Users className="h-5 w-5" />} hint="On your care list" />
              <Stat label="Analyses today" value={data?.analyses_today ?? 0} icon={<ScanLine className="h-5 w-5" />} hint={`${data?.analyses_total ?? 0} in total`} />
              <Stat label="Flagged for review" value={data?.flagged_for_review ?? 0} tone="review" icon={<Stethoscope className="h-5 w-5" />} hint="Need a dentist's sign-off" />
              <Stat
                label="Audit chain"
                value={data?.system.audit_chain_intact ? "Intact" : "Broken"}
                tone={data?.system.audit_chain_intact ? "ok" : "critical"}
                icon={<ShieldAlert className="h-5 w-5" />}
                hint={`${data?.system.audit_entries ?? 0} entries verified`}
              />
            </>
          )}
        </div>
      ) : null}

      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <div className="space-y-6 xl:col-span-2">
          {clinical && (
            <div className="grid gap-6 md:grid-cols-2">
              <Card>
                <CardTitle>Stage distribution</CardTitle>
                <StageBars data={data?.stage_distribution ?? {}} />
              </Card>
              <Card>
                <CardTitle>Risk mix</CardTitle>
                <RiskDonut data={data?.risk_distribution ?? {}} />
                <p className="mt-1 text-center text-[11px] text-mist-500">Rule-assisted demo score, not a calibrated clinical risk.</p>
              </Card>
            </div>
          )}
          {clinical && (
            <Card>
              <CardTitle icon={<ClipboardList className="h-4 w-4" />}>Recent analyses</CardTitle>
              {!data?.recent?.length ? (
                <EmptyState title="No analyses yet" body="Upload a radiograph to run the first analysis." />
              ) : (
                <ul className="divide-y divide-white/[0.05]">
                  {data.recent.map((a, i) => (
                    <motion.li key={a.analysis_id} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.04 }}>
                      <Link to={`/app/analysis/${a.analysis_id}`} className="group flex items-center gap-4 py-3">
                        <div className="rounded-xl bg-white/[0.04] p-2 font-mono text-xs text-brand-300">{a.pseudo_id}</div>
                        <div className="flex-1">
                          <p className="text-sm text-mist-100">Visit {a.visit_date}</p>
                          <p className="text-xs text-mist-500">{fmtDateTime(a.created)}</p>
                        </div>
                        {a.mode === "demo" && <Badge>demo</Badge>}
                        <Badge tone={REVIEW_TONE[a.review_status]}>{REVIEW_LABEL[a.review_status]}</Badge>
                        <ArrowUpRight className="h-4 w-4 text-mist-500 transition group-hover:text-brand-300" />
                      </Link>
                    </motion.li>
                  ))}
                </ul>
              )}
            </Card>
          )}
          {data?.recent_security_events && (
            <Card>
              <CardTitle icon={<AlertTriangle className="h-4 w-4" />}>Recent security events</CardTitle>
              {!data.recent_security_events.length ? (
                <EmptyState title="All quiet" body="No denied, failed or alerting events recently." />
              ) : (
                <ul className="space-y-2">
                  {data.recent_security_events.map((e) => (
                    <li key={e.seq} className="flex items-center gap-3 rounded-xl border border-white/[0.05] px-3 py-2 text-sm">
                      <span className="font-mono text-xs text-mist-500">#{e.seq}</span>
                      <span className="flex-1 text-mist-100">{e.action}</span>
                      <Badge tone={e.outcome === "alert" ? "critical" : "review"}>{e.outcome}</Badge>
                      <span className="text-xs text-mist-500">{fmtDateTime(e.timestamp)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          )}
        </div>
        <div className="space-y-6">
          <SystemStatusCard status={data?.system} />
          <Card className="bg-gradient-to-br from-brand-400/10 to-transparent">
            <p className="label text-brand-300">Clinical reminder</p>
            <p className="mt-2 text-sm text-mist-300">
              PerioVision suggests stages and grades from radiographic bone loss. Probing depths, bleeding and attachment loss
              still come from your clinical exam.
            </p>
          </Card>
        </div>
      </div>
    </div>
  );
}
