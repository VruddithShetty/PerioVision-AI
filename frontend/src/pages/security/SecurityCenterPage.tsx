import clsx from "clsx";
import { Anchor, CheckCircle2, KeyRound, Link2, MonitorSmartphone, ShieldCheck, ShieldX, Smartphone, XCircle } from "lucide-react";
import { lazy, useState } from "react";
import { api, ApiError } from "@/api/client";
import { useAllSessions, useAnchor, useAuditLogs, useMySessions, useRbacMatrix, useVerifyChain } from "@/api/hooks";
import type { ChainVerification, User } from "@/api/types";
import { ErrorState, LoadingRows, PageHeader, Table, Tabs } from "@/components/ui/blocks";
import { Badge, Button, Card, CardTitle, Input } from "@/components/ui/primitives";
import { fmtDateTime, shortHash } from "@/lib/format";
import { useAuth, useCan } from "@/store/auth";
import { SceneGate } from "@/three/SceneGate";

const HashChain3D = lazy(() => import("@/three/HashChain3D"));

const OUTCOME_TONE: Record<string, "ok" | "review" | "critical" | "neutral" | "brand"> = {
  success: "ok", denied: "review", alert: "critical", rejected: "review", error: "critical", intact: "ok", tampered: "critical",
  defended: "ok", not_defended: "critical", valid: "ok", invalid: "review",
};

function AuditPanel() {
  const [action, setAction] = useState("");
  const { data, isLoading, error } = useAuditLogs(action, 150);
  const verify = useVerifyChain();
  const anchor = useAnchor();
  const result: ChainVerification | undefined = verify.data;

  return (
    <div className="space-y-6">
      <Card strong>
        <CardTitle
          icon={<Link2 className="h-4 w-4" />}
          action={
            <div className="flex gap-2">
              <Button size="sm" variant="outline" icon={<Anchor className="h-3.5 w-3.5" />} loading={anchor.isPending} onClick={() => anchor.mutate()}>
                Anchor root
              </Button>
              <Button size="sm" icon={<ShieldCheck className="h-3.5 w-3.5" />} loading={verify.isPending} onClick={() => verify.mutate()}>
                Verify chain
              </Button>
            </div>
          }
        >
          Hash chain
        </CardTitle>
        <div className="h-56 rounded-xl bg-gradient-to-b from-ink-900/60 to-transparent">
          {data && (
            <SceneGate allowReducedMotion fallback={<p className="p-6 text-sm text-mist-400">3D view unavailable on this device.</p>}>
              <HashChain3D entries={data} firstTampered={result?.first_tampered_seq ?? null} />
            </SceneGate>
          )}
        </div>
        {result && (
          <div className={clsx("mt-4 flex items-start gap-3 rounded-xl border p-4", result.chain_intact ? "border-teal-400/30 bg-teal-400/[0.06]" : "border-critical-500/40 bg-critical-500/[0.08]")}>
            {result.chain_intact ? <CheckCircle2 className="mt-0.5 h-5 w-5 text-teal-400" /> : <XCircle className="mt-0.5 h-5 w-5 text-critical-400" />}
            <div className="text-sm">
              <p className="font-medium">
                {result.chain_intact
                  ? `Chain intact: ${result.entries_verified} entries and ${result.anchors_checked} Merkle anchors verified.`
                  : `Tampering detected at entry #${result.first_tampered_seq}: ${result.reason}`}
              </p>
              <p className="mt-1 text-xs text-mist-400">
                Current Merkle root <span className="hash">{shortHash(result.current_root, 16)}</span>
                {result.latest_anchor && <> · last anchor covers {result.latest_anchor.count} entries ({fmtDateTime(result.latest_anchor.timestamp)})</>}
              </p>
            </div>
          </div>
        )}
      </Card>

      <Card>
        <CardTitle action={<Input placeholder="Filter by action, e.g. LOGIN_FAILED" value={action} onChange={(e) => setAction(e.target.value.toUpperCase())} className="w-64 py-1.5 text-xs" aria-label="Filter audit log" />}>
          Audit log
        </CardTitle>
        {error ? <ErrorState error={error} /> : isLoading ? <LoadingRows /> : (
          <Table head={["#", "Time", "Action", "Outcome", "Actor", "Resource", "Entry hash"]}>
            {data!.map((e) => (
              <tr key={e.seq} className="hover:bg-white/[0.02]">
                <td className="px-4 py-2 font-mono text-xs text-mist-500">{e.seq}</td>
                <td className="px-4 py-2 text-xs text-mist-400">{fmtDateTime(e.timestamp)}</td>
                <td className="px-4 py-2 font-medium">{e.action}</td>
                <td className="px-4 py-2"><Badge tone={OUTCOME_TONE[e.outcome] ?? "neutral"}>{e.outcome}</Badge></td>
                <td className="max-w-[120px] truncate px-4 py-2 font-mono text-xs text-mist-400" title={e.actor}>{e.actor.slice(0, 8)}</td>
                <td className="px-4 py-2 font-mono text-xs text-brand-300">{e.resource ?? "–"}</td>
                <td className="px-4 py-2 font-mono text-[11px] text-mist-500">{shortHash(e.entry_hash, 8)}</td>
              </tr>
            ))}
          </Table>
        )}
        <p className="mt-3 text-xs text-mist-500">Patients appear only as pseudonyms (P-…) and IP addresses as salted hashes. No PHI is logged.</p>
      </Card>
    </div>
  );
}

function RbacPanel() {
  const { data, isLoading } = useRbacMatrix();
  const myRole = useAuth((s) => s.user?.role);
  if (isLoading || !data) return <LoadingRows />;
  return (
    <Card>
      <CardTitle icon={<KeyRound className="h-4 w-4" />}>Role permission matrix (enforced on every request)</CardTitle>
      <Table head={["Permission", ...data.roles]}>
        {Object.entries(data.matrix).map(([perm, roles]) => (
          <tr key={perm}>
            <td className="px-4 py-2 font-mono text-xs">{perm}</td>
            {data.roles.map((r) => (
              <td key={r} className={clsx("px-4 py-2", r === myRole && "bg-brand-400/[0.06]")}>
                {roles[r] ? <CheckCircle2 className="h-4 w-4 text-teal-400" aria-label="allowed" /> : <span className="text-mist-500" aria-label="denied">·</span>}
              </td>
            ))}
          </tr>
        ))}
      </Table>
    </Card>
  );
}

function SessionsPanel() {
  const canSeeAll = useCan("security:read");
  const mine = useMySessions();
  const all = useAllSessions(canSeeAll);
  const list = canSeeAll ? all.data : mine.data;
  return (
    <Card>
      <CardTitle icon={<MonitorSmartphone className="h-4 w-4" />}>{canSeeAll ? "Active sessions (all users)" : "Your active sessions"}</CardTitle>
      {!list ? <LoadingRows /> : (
        <Table head={["Session", "User", "Started", "Last seen", ""]}>
          {list.map((s) => (
            <tr key={s.sid + s.created}>
              <td className="px-4 py-2 font-mono text-xs">{s.sid}</td>
              <td className="px-4 py-2 font-mono text-xs text-mist-400">{s.user_id.slice(0, 8)}</td>
              <td className="px-4 py-2 text-xs">{fmtDateTime(s.created)}</td>
              <td className="px-4 py-2 text-xs">{fmtDateTime(s.last_seen)}</td>
              <td className="px-4 py-2">{s.current && <Badge tone="brand">this device</Badge>}</td>
            </tr>
          ))}
        </Table>
      )}
      <p className="mt-3 text-xs text-mist-500">Sessions are bound to the device that signed in, expire after 30 idle minutes and are revoked on logout or refresh-token reuse.</p>
    </Card>
  );
}

function MfaPanel() {
  const user = useAuth((s) => s.user);
  const setUser = useAuth((s) => s.setUser);
  const [qr, setQr] = useState<{ otpauth_uri: string; qr_png_base64: string } | null>(null);
  const [code, setCode] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refreshMe = async () => setUser((await api<User>("/api/auth/me")).data);
  const start = async () => {
    setBusy(true);
    setMsg(null);
    try {
      setQr((await api<{ otpauth_uri: string; qr_png_base64: string }>("/api/auth/mfa/enroll", { method: "POST" })).data);
    } finally {
      setBusy(false);
    }
  };
  const confirm = async (path: string) => {
    setBusy(true);
    setMsg(null);
    try {
      await api(path, { body: { code } });
      setQr(null);
      setCode("");
      await refreshMe();
    } catch (e) {
      setMsg((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardTitle icon={<Smartphone className="h-4 w-4" />}>Two-step verification (TOTP)</CardTitle>
      {user?.mfa_enabled ? (
        <div className="space-y-4">
          <p className="flex items-center gap-2 text-sm text-teal-400"><ShieldCheck className="h-4 w-4" /> Enabled on your account.</p>
          <div className="flex max-w-sm gap-2">
            <Input inputMode="numeric" maxLength={6} placeholder="Current code" value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} aria-label="Code to disable MFA" />
            <Button variant="danger" disabled={code.length !== 6} loading={busy} onClick={() => confirm("/api/auth/mfa/disable")}>Disable</Button>
          </div>
        </div>
      ) : qr ? (
        <div className="grid gap-6 md:grid-cols-[auto_1fr]">
          <img src={`data:image/png;base64,${qr.qr_png_base64}`} alt="QR code for your authenticator app" className="h-44 w-44 rounded-xl bg-white p-2" />
          <div className="space-y-3 text-sm">
            <p className="text-mist-300">Scan with Google Authenticator, Microsoft Authenticator or similar, then enter the 6-digit code.</p>
            <div className="flex max-w-sm gap-2">
              <Input inputMode="numeric" maxLength={6} placeholder="123456" value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} aria-label="Verification code" />
              <Button disabled={code.length !== 6} loading={busy} onClick={() => confirm("/api/auth/mfa/confirm")}>Confirm</Button>
            </div>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="flex items-center gap-2 text-sm text-review-400"><ShieldX className="h-4 w-4" /> Not enabled. Protect your account with a second factor.</p>
          <Button loading={busy} onClick={start}>Set up authenticator</Button>
        </div>
      )}
      {msg && <p className="mt-3 text-sm text-critical-400">{msg}</p>}
    </Card>
  );
}

export default function SecurityCenterPage() {
  const canAudit = useCan("audit:read");
  const [tab, setTab] = useState<"audit" | "rbac" | "sessions" | "mfa">(canAudit ? "audit" : "mfa");
  const tabs = [
    ...(canAudit ? [{ value: "audit" as const, label: "Audit & hash chain" }] : []),
    { value: "rbac" as const, label: "RBAC matrix" },
    { value: "sessions" as const, label: "Sessions" },
    { value: "mfa" as const, label: "MFA" },
  ];
  return (
    <div>
      <PageHeader
        eyebrow="Security center"
        title="Integrity, access and accountability"
        subtitle="The audit trail is hash-chained and Merkle-anchored, so any edit is detectable. Every request is checked against the role matrix below."
        actions={<Tabs value={tab} onChange={setTab} items={tabs} />}
      />
      {tab === "audit" && canAudit && <AuditPanel />}
      {tab === "rbac" && <RbacPanel />}
      {tab === "sessions" && <SessionsPanel />}
      {tab === "mfa" && <MfaPanel />}
    </div>
  );
}
