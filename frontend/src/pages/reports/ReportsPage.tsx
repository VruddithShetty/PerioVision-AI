import { Download, FileSignature, QrCode } from "lucide-react";
import { useEffect, useState } from "react";
import { apiBlob, downloadFile } from "@/api/client";
import { useReports } from "@/api/hooks";
import type { ReportSummary } from "@/api/types";
import { VerifyPanel } from "@/components/VerifyPanel";
import { EmptyState, ErrorState, LoadingRows, PageHeader } from "@/components/ui/blocks";
import { Badge, Button, Card, CardTitle, Skeleton } from "@/components/ui/primitives";
import { fmtDateTime, shortHash } from "@/lib/format";

function Preview({ report }: { report: ReportSummary }) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    let u: string | null = null;
    setUrl(null);
    apiBlob(`/api/reports/${report.report_id}/download`).then((b) => {
      u = URL.createObjectURL(b);
      setUrl(u);
    });
    return () => {
      if (u) URL.revokeObjectURL(u);
    };
  }, [report.report_id]);
  return url ? <iframe src={url} title={`Report ${report.report_id}`} className="h-[640px] w-full rounded-xl border border-white/[0.06] bg-white" /> : <Skeleton className="h-[640px] w-full" />;
}

export default function ReportsPage() {
  const { data, isLoading, error, refetch } = useReports();
  const [open, setOpen] = useState<ReportSummary | null>(null);
  useEffect(() => {
    if (!open && data?.length) setOpen(data[0]!);
  }, [data, open]);

  return (
    <div>
      <PageHeader
        eyebrow="Reports"
        title="Signed clinical reports"
        subtitle="Each PDF's SHA-256 is signed with RSA-PSS and stored encrypted. The QR code on the report links to public verification."
      />
      <div className="grid gap-6 xl:grid-cols-[380px_minmax(0,1fr)]">
        <div className="space-y-6">
          <Card>
            <CardTitle icon={<FileSignature className="h-4 w-4" />}>Issued reports</CardTitle>
            {error ? <ErrorState error={error} retry={refetch} /> : isLoading ? <LoadingRows rows={4} /> : !data?.length ? (
              <EmptyState title="No reports yet" body="Open an analysis that has been signed off and choose “Signed report”." />
            ) : (
              <ul className="space-y-2">
                {data.map((r) => (
                  <li key={r.report_id}>
                    <button
                      onClick={() => setOpen(r)}
                      className={`w-full rounded-xl border p-3 text-left transition ${open?.report_id === r.report_id ? "border-brand-400/40 bg-brand-400/[0.06]" : "border-white/[0.06] hover:border-white/15"}`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-xs text-brand-300">{r.report_id}</span>
                        {r.mode === "demo" && <Badge>demo</Badge>}
                      </div>
                      <p className="mt-1 text-sm">{r.pseudo_id} · {fmtDateTime(r.created)}</p>
                      <p className="mt-1 font-mono text-[10px] text-mist-500">sha256 {shortHash(r.sha256, 12)}</p>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card>
            <CardTitle icon={<QrCode className="h-4 w-4" />}>Verify a report</CardTitle>
            <VerifyPanel initialId="" />
          </Card>
        </div>
        <Card>
          {open ? (
            <>
              <CardTitle action={<Button size="sm" icon={<Download className="h-3.5 w-3.5" />} onClick={() => downloadFile(`/api/reports/${open.report_id}/download`, `PerioVision_${open.report_id}.pdf`)}>Download PDF</Button>}>
                {open.report_id}
              </CardTitle>
              <Preview report={open} />
            </>
          ) : (
            <EmptyState title="Select a report to preview" />
          )}
        </Card>
      </div>
    </div>
  );
}
