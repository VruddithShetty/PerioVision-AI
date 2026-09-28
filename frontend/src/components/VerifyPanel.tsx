import clsx from "clsx";
import { motion } from "framer-motion";
import { BadgeCheck, FileUp, Search, ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { ApiError } from "@/api/client";
import { verifyReportById, verifyReportFile } from "@/api/hooks";
import type { VerifyResult } from "@/api/types";
import { Button, Input } from "@/components/ui/primitives";
import { fmtDateTime, shortHash } from "@/lib/format";

/** Public report verification: by ID (from the QR code) or by uploading the PDF itself. */
export function VerifyPanel({ initialId = "" }: { initialId?: string }) {
  const [id, setId] = useState(initialId);
  const [result, setResult] = useState<VerifyResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const check = async (fn: () => Promise<VerifyResult>) => {
    setBusy(true);
    setErr(null);
    try {
      setResult(await fn());
    } catch (e) {
      setErr((e as ApiError).message);
      setResult(null);
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (initialId) void check(() => verifyReportById(initialId));
  }, [initialId]);

  return (
    <div className="space-y-4">
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (id.trim()) void check(() => verifyReportById(id.trim()));
        }}
      >
        <Input placeholder="Verification ID, e.g. RPT-1a2b3c4d5e6f7a8b" value={id} onChange={(e) => setId(e.target.value)} aria-label="Report verification ID" />
        <Button type="submit" loading={busy} icon={<Search className="h-4 w-4" />}>Verify</Button>
      </form>
      <label className="flex cursor-pointer items-center justify-center gap-2 rounded-xl border border-dashed border-white/15 px-4 py-4 text-sm text-mist-400 transition hover:border-brand-400/50 hover:text-mist-100">
        <FileUp className="h-4 w-4" /> …or drop in the PDF to check that it wasn't altered
        <input type="file" accept="application/pdf" className="sr-only" onChange={(e) => e.target.files?.[0] && check(() => verifyReportFile(e.target.files![0]!))} />
      </label>
      {err && <p className="text-sm text-critical-400">{err}</p>}
      {result && (
        <motion.div
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          className={clsx("rounded-2xl border p-5", result.valid ? "border-teal-400/35 bg-teal-400/[0.07]" : "border-critical-500/40 bg-critical-500/[0.08]")}
        >
          <div className="flex items-center gap-3">
            {result.valid ? <BadgeCheck className="h-8 w-8 text-teal-400" /> : <ShieldAlert className="h-8 w-8 text-critical-400" />}
            <div>
              <p className="font-display text-xl font-semibold">{result.valid ? "Authentic, unaltered report" : "Verification failed"}</p>
              <p className="text-sm text-mist-400">{result.valid ? "The RSA-PSS signature matches the SHA-256 of this document." : result.reason}</p>
            </div>
          </div>
          {result.report_id && (
            <dl className="mt-4 grid gap-2 text-xs sm:grid-cols-2">
              <div><dt className="label">Report</dt><dd className="font-mono">{result.report_id}</dd></div>
              <div><dt className="label">Issued</dt><dd>{fmtDateTime(result.created)}</dd></div>
              <div><dt className="label">SHA-256</dt><dd className="hash">{shortHash(result.sha256, 20)}</dd></div>
              <div><dt className="label">Signing key</dt><dd className="hash">{result.key_fingerprint ?? "–"}</dd></div>
            </dl>
          )}
        </motion.div>
      )}
    </div>
  );
}
