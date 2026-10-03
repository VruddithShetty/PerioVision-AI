import clsx from "clsx";
import { motion } from "framer-motion";
import { ArrowLeft } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useModelMetrics } from "@/api/hooks";
import { Logo } from "@/components/layout/Logo";
import { PageHeader, Table } from "@/components/ui/blocks";
import { Card, CardTitle } from "@/components/ui/primitives";

const pct = (v: number | null | undefined) => (v === null || v === undefined ? "not evaluated" : `${(v * 100).toFixed(1)}%`);

/** Accuracy as measured on held-out test data, read from the installed models' metric files (never typed in here). */
function MeasuredAccuracy() {
  const { data: m, isLoading, error } = useModelMetrics();
  if (isLoading) return <>Loading measured accuracy…</>;
  if (error || !m) return <>Measured accuracy is unavailable (could not reach the server).</>;
  const det = m.tooth_detector;
  const lm = m.landmarks?.test;
  const cov = m.conformal?.levels?.["0.9"];
  return (
    <>
      {det ? `Tooth detector (${det.model}) on held-out test X-rays: ${pct(det.test_precision)} precision, ${pct(det.test_recall)} recall, ${pct(det.test_mAP50)} mAP@0.5. ` : "Tooth detector: no test metrics installed. "}
      {lm ? `Landmarks on ${lm.n_teeth} held-out ${m.conformal?.image_type ?? ""} teeth: bone-loss error ${lm.bone_loss_MAE_pct_points.toFixed(1)} points, ${pct(lm.stage_agreement)} stage agreement` : "Landmarks: no test metrics installed"}
      {cov?.empirical_coverage_other_half != null ? `, ${pct(cov.empirical_coverage_other_half)} coverage of the 90 % conformal interval (${cov.mean_half_width_pct != null ? `on average ±${cov.mean_half_width_pct.toFixed(1)} points, wider for harder teeth` : `±${cov.q_from_half?.toFixed(1)} points`}). ` : ". "}
      {m.conformal?.image_type ? `Bone loss is measured on ${m.conformal.image_type} X-rays only; on other X-ray types teeth are detected and numbered but no bone-loss numbers are given.` : "Landmarks are not calibrated, so every case is reviewed."}
    </>
  );
}

type NodeId = "ui" | "api" | "zt" | "ml" | "sec" | "db" | "store" | "audit";

const NODES: { id: NodeId; label: string; sub: string; x: number; y: number; detail: string }[] = [
  { id: "ui", label: "React frontend", sub: "Vite · TS · three.js", x: 40, y: 150, detail: "15 pages. Holds the access token in memory only; the refresh token is an httpOnly cookie. Hides what your role can't use." },
  { id: "zt", label: "Zero Trust guard", sub: "every request", x: 250, y: 150, detail: "Re-checks token, server-side session, device fingerprint, account state and RBAC permission on every call. Unclassified routes are denied." },
  { id: "api", label: "Flask REST API", sub: "blueprints · envelope", x: 460, y: 150, detail: "Thin route handlers with strict pydantic validation. Every response: {data, meta, error, mode}. OpenAPI at /api/docs." },
  { id: "ml", label: "ML pipeline", sub: "YOLO11m · Grad-CAM · conformal", x: 680, y: 50, detail: "Quality gate → CLAHE → FDI detection → CEJ/crest/apex → bone loss & staging → Grad-CAM ROI check → conformal interval → review routing → risk." },
  { id: "sec", label: "Signing service", sub: "RSA-PSS", x: 680, y: 150, detail: "Verifies the signed weight manifest before any model loads, and signs the SHA-256 of every PDF report." },
  { id: "audit", label: "Audit chain", sub: "hash chain + Merkle", x: 680, y: 250, detail: "Append-only, hash-chained entries (no PHI). Merkle roots anchored with an HMAC key outside the database." },
  { id: "db", label: "MongoDB", sub: "encrypted fields", x: 900, y: 100, detail: "Patients (names/contacts AES-256-GCM encrypted with blind indexes), users, sessions, analyses, reports. mongomock in demo mode." },
  { id: "store", label: "Encrypted blobs", sub: "AES-256-GCM files", x: 900, y: 210, detail: "Radiographs, overlays, Grad-CAM layers and PDFs, each bound to its purpose via GCM associated data." },
];
const EDGES: [NodeId, NodeId][] = [["ui", "zt"], ["zt", "api"], ["api", "ml"], ["api", "sec"], ["api", "audit"], ["ml", "db"], ["api", "db"], ["api", "store"], ["sec", "store"]];

const TRACE = [
  ["O1 Bone-loss detection", "ml/detection, ml/landmarks, ml/measurement", "POST /api/analyses", "New analysis, Analysis viewer"],
  ["O2 Longitudinal progression", "services/progression_service.py", "GET /api/patients/:id/progression", "Progression timeline"],
  ["O3 Explainability (Grad-CAM)", "ml/explainability/gradcam.py", "GET /api/analyses/:id/image/gradcam", "Analysis viewer (heatmap layer)"],
  ["O4 Uncertainty (conformal)", "ml/uncertainty/*", "GET /api/models/trust", "Viewer tooth panel, Model trust"],
  ["O5 Multimodal risk fusion", "ml/fusion/multimodal_risk.py", "POST /api/analyses (risk)", "Analysis viewer (risk gauge)"],
  ["O6 Cybersecurity mechanisms", "security/* (crypto, auth, rbac, zero_trust, audit_log, model_signing, upload_guard)", "/api/auth/*, /api/audit/*, /api/security-lab/*", "Login, Security center, Security lab, Admin"],
  ["O7 Secure decision support", "services/analysis_service.py, api/*", "full workflow", "Dashboard → … → Reports"],
];

export default function AboutPage({ embedded = false }: { embedded?: boolean }) {
  const [active, setActive] = useState<NodeId>("zt");
  const node = NODES.find((n) => n.id === active)!;
  const pos = (id: NodeId) => NODES.find((n) => n.id === id)!;

  const body = (
    <>
      <PageHeader
        eyebrow="About"
        title="PerioVision AI architecture"
        subtitle="A secure, explainable clinical decision-support system for periodontal bone-loss detection. Final-year cybersecurity project."
      />
      <Card strong>
        <CardTitle>How a request flows (click any block)</CardTitle>
        <div className="overflow-x-auto">
          <svg viewBox="0 0 1060 320" className="min-w-[860px]" role="img" aria-label="Architecture diagram">
            <defs>
              <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M0 0 L10 5 L0 10 z" fill="#2dd4bf" />
              </marker>
            </defs>
            {EDGES.map(([a, b]) => {
              const A = pos(a);
              const B = pos(b);
              const hot = active === a || active === b;
              return (
                <line key={`${a}-${b}`} x1={A.x + 150} y1={A.y + 28} x2={B.x} y2={B.y + 28} stroke={hot ? "#22d3ee" : "#1a3050"} strokeWidth={hot ? 2.5 : 1.5} markerEnd="url(#arrow)" />
              );
            })}
            {NODES.map((n) => (
              <g key={n.id} transform={`translate(${n.x},${n.y})`} className="cursor-pointer" onClick={() => setActive(n.id)} onMouseEnter={() => setActive(n.id)}>
                <rect width="150" height="56" rx="14" fill={active === n.id ? "rgba(34,211,238,0.14)" : "rgba(10,22,40,0.9)"} stroke={active === n.id ? "#22d3ee" : "rgba(255,255,255,0.1)"} />
                <text x="75" y="25" textAnchor="middle" fontSize="13" fontWeight="600" fill="#e6f1ff" fontFamily="Inter">{n.label}</text>
                <text x="75" y="42" textAnchor="middle" fontSize="10" fill="#7f93b0" fontFamily="JetBrains Mono">{n.sub}</text>
              </g>
            ))}
          </svg>
        </div>
        <motion.div key={active} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="mt-4 rounded-xl border border-brand-400/20 bg-brand-400/[0.05] p-4">
          <p className="font-display font-semibold text-brand-300">{node.label}</p>
          <p className="mt-1 text-sm text-mist-300">{node.detail}</p>
        </motion.div>
      </Card>

      <Card className="mt-6">
        <CardTitle>Synopsis objectives → code → API → screen</CardTitle>
        <Table head={["Objective", "Backend module", "API", "UI page"]}>
          {TRACE.map((r) => (
            <tr key={r[0]}>
              {r.map((c, i) => <td key={i} className={clsx("px-4 py-2.5", i === 0 ? "font-medium" : "text-mist-400", i === 1 && "font-mono text-xs")}>{c}</td>)}
            </tr>
          ))}
        </Table>
      </Card>

      <Card className="mt-6">
        <p className="label">Honest limitations</p>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-mist-300">
          <li>Decision-support tool; not a certified medical device.</li>
          <li>Controls are aligned with HIPAA safeguards, not certified.</li>
          <li><MeasuredAccuracy /></li>
          <li>The risk score is a documented rule-assisted demo, not a trained clinical model.</li>
        </ul>
      </Card>
    </>
  );

  if (embedded) return body;
  return (
    <div className="mx-auto max-w-6xl px-5 py-10">
      <div className="mb-8 flex items-center justify-between">
        <Logo />
        <Link to="/" className="flex items-center gap-1 text-sm text-mist-400 hover:text-mist-100"><ArrowLeft className="h-4 w-4" /> Home</Link>
      </div>
      {body}
    </div>
  );
}
