import { Activity, CheckCircle2, Database, FileLock2, Gauge, XCircle } from "lucide-react";
import type { SystemStatus } from "@/api/types";
import { Card, CardTitle, Skeleton } from "@/components/ui/primitives";

function Row({ ok, label, detail, icon }: { ok: boolean; label: string; detail?: string; icon: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-white/[0.05] bg-white/[0.02] px-3 py-2.5">
      <span className="text-mist-400">{icon}</span>
      <div className="min-w-0 flex-1">
        <p className="text-sm text-mist-100">{label}</p>
        {detail && <p className="truncate text-xs text-mist-500">{detail}</p>}
      </div>
      {ok ? <CheckCircle2 className="h-5 w-5 text-teal-400" aria-label="OK" /> : <XCircle className="h-5 w-5 text-review-400" aria-label="Attention" />}
    </div>
  );
}

export function SystemStatusCard({ status }: { status?: SystemStatus }) {
  return (
    <Card>
      <CardTitle icon={<Activity className="h-4 w-4" />}>System status</CardTitle>
      {!status ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-12" />
          ))}
        </div>
      ) : (
        <div className="space-y-2">
          <Row ok={status.database} label="Database" detail={status.mode === "demo" ? "In-memory (demo mode)" : "MongoDB"} icon={<Database className="h-4 w-4" />} />
          <Row
            ok={status.models_verified}
            label="Model signatures"
            detail={status.models.map((m) => `${m.name}: ${m.signature_valid ? "valid" : m.reason ?? "missing"}`).join(" · ")}
            icon={<FileLock2 className="h-4 w-4" />}
          />
          <Row ok={status.audit_chain_intact} label="Audit chain" detail={`${status.audit_entries} entries verified`} icon={<Activity className="h-4 w-4" />} />
          <Row ok={status.calibrated} label="Uncertainty calibration" detail={status.calibrated ? "Conformal calibration loaded" : "Not calibrated: every case goes to review"} icon={<Gauge className="h-4 w-4" />} />
        </div>
      )}
    </Card>
  );
}
