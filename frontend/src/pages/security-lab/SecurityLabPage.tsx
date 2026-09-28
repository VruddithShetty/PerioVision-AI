import clsx from "clsx";
import { AnimatePresence, motion } from "framer-motion";
import {
  Bug,
  CheckCircle2,
  FileWarning,
  FlaskConical,
  KeyRound,
  Link2Off,
  Loader2,
  Lock,
  Play,
  PlayCircle,
  ScanFace,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { useState } from "react";
import { runLabScenario, useLabScenarios } from "@/api/hooks";
import type { LabResult } from "@/api/types";
import { ErrorState, LoadingRows, PageHeader } from "@/components/ui/blocks";
import { Badge, Button } from "@/components/ui/primitives";

const ICON: Record<string, typeof Bug> = {
  "model-tamper": Bug,
  "audit-tamper": Link2Off,
  "jwt-replay": KeyRound,
  "disguised-upload": FileWarning,
  "report-tamper": ShieldCheck,
  "adversarial-input": ScanFace,
  "encryption-tamper": Lock,
};

const STORY: Record<string, string> = {
  "model-tamper": "An attacker swaps one bit in the tooth-detection weights to skew diagnoses.",
  "audit-tamper": "An insider edits the audit trail to hide who opened a patient record, then rebuilds the chain.",
  "jwt-replay": "A stolen, expired login token is replayed; a forged admin token and an unsigned 'alg:none' token are tried.",
  "disguised-upload": "Malware renamed to xray.png, a PDF posing as a JPEG, a path-traversal file name and an SVG with script.",
  "report-tamper": "Someone downgrades 'Stage II' to 'Stage I' inside a signed PDF report.",
  "adversarial-input": "Invisible pixel noise is added to a radiograph to fool the model.",
  "encryption-tamper": "Bytes of an encrypted radiograph are flipped on disk, or it is swapped in as a report.",
};

function ScenarioCard({ id, title, defence, result, running, onRun }: {
  id: string;
  title: string;
  defence: string;
  result?: LabResult;
  running: boolean;
  onRun: () => void;
}) {
  const Icon = ICON[id] ?? FlaskConical;
  const state = running ? "running" : result ? (result.defended ? "defended" : "failed") : "idle";
  return (
    <motion.div
      layout
      className={clsx(
        "glass relative overflow-hidden p-5 transition",
        state === "defended" && "border-teal-400/35",
        state === "failed" && "border-critical-500/50",
        state === "running" && "border-brand-400/40 shadow-glow",
      )}
    >
      <div className="flex items-start gap-4">
        <div className={clsx("rounded-2xl p-3 ring-1", state === "defended" ? "bg-teal-400/10 text-teal-400 ring-teal-400/25" : state === "failed" ? "bg-critical-500/10 text-critical-400 ring-critical-500/30" : "bg-critical-500/10 text-critical-400 ring-critical-500/20")}>
          <Icon className="h-6 w-6" />
        </div>
        <div className="flex-1">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="font-display text-lg font-semibold">{title}</p>
            {state === "defended" && <Badge tone="ok"><CheckCircle2 className="h-3 w-3" /> Attack blocked</Badge>}
            {state === "failed" && <Badge tone="critical"><XCircle className="h-3 w-3" /> Not defended</Badge>}
          </div>
          <p className="mt-1 text-sm text-mist-400">{STORY[id]}</p>
          <p className="mt-2 text-xs text-brand-300">Defence: {defence}</p>
        </div>
      </div>

      <AnimatePresence>
        {result && (
          <motion.ol initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} className="mt-4 space-y-1.5 border-t border-white/[0.06] pt-4">
            {result.steps.map((s, i) => (
              <motion.li
                key={s.label}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.25 }}
                className="flex items-start gap-2.5 text-sm"
              >
                {s.passed ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-teal-400" /> : <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-critical-400" />}
                <div>
                  <p className="text-mist-100">{s.label}</p>
                  {s.detail && <p className="font-mono text-[11px] text-mist-500">{s.detail}</p>}
                </div>
              </motion.li>
            ))}
            {result.error && <li className="text-sm text-critical-400">{result.error}</li>}
            <li className="pt-1 text-[11px] text-mist-500">ran in {result.duration_ms} ms on throwaway data</li>
          </motion.ol>
        )}
      </AnimatePresence>

      <div className="mt-4">
        <Button size="sm" variant={result ? "outline" : "primary"} icon={running ? undefined : <Play className="h-3.5 w-3.5" />} loading={running} onClick={onRun}>
          {running ? "Attacking…" : result ? "Run again" : "Launch attack"}
        </Button>
      </div>
      {running && <motion.div className="absolute inset-x-0 bottom-0 h-0.5 bg-gradient-to-r from-transparent via-brand-400 to-transparent" animate={{ x: ["-100%", "100%"] }} transition={{ repeat: Infinity, duration: 1.1 }} />}
    </motion.div>
  );
}

export default function SecurityLabPage() {
  const { data, isLoading, error, refetch } = useLabScenarios();
  const [results, setResults] = useState<Record<string, LabResult>>({});
  const [running, setRunning] = useState<Set<string>>(new Set());
  const [allBusy, setAllBusy] = useState(false);

  const run = async (id: string) => {
    setRunning((r) => new Set(r).add(id));
    try {
      const res = await runLabScenario(id);
      await new Promise((r) => setTimeout(r, 450)); // let the attack animation read clearly
      setResults((x) => ({ ...x, [id]: res }));
    } finally {
      setRunning((r) => {
        const n = new Set(r);
        n.delete(id);
        return n;
      });
    }
  };
  const runAll = async () => {
    setAllBusy(true);
    for (const s of data ?? []) await run(s.id);
    setAllBusy(false);
  };

  const done = Object.values(results);
  const defended = done.filter((r) => r.defended).length;

  return (
    <div>
      <PageHeader
        eyebrow="Security lab"
        title="Attack the system (safely)"
        subtitle="Each scenario runs a real attack against temporary copies: throwaway keys, isolated logs, synthetic images. Real patients, weights and the real audit trail are never touched."
        actions={<Button icon={allBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlayCircle className="h-4 w-4" />} disabled={allBusy || !data} onClick={runAll}>Run all attacks</Button>}
      />
      {done.length > 0 && (
        <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="mb-6 flex items-center gap-4 rounded-2xl border border-teal-400/25 bg-gradient-to-r from-teal-400/10 to-transparent p-4">
          <ShieldCheck className="h-8 w-8 text-teal-400" />
          <div>
            <p className="font-display text-2xl font-bold">{defended} / {done.length} attacks blocked</p>
            <p className="text-xs text-mist-400">Every run is also recorded in the audit log as SECURITY_LAB_RUN.</p>
          </div>
        </motion.div>
      )}
      {error ? <ErrorState error={error} retry={refetch} /> : isLoading ? <LoadingRows /> : (
        <div className="grid gap-5 lg:grid-cols-2">
          {data!.map((s) => (
            <ScenarioCard key={s.id} {...s} result={results[s.id]} running={running.has(s.id)} onRun={() => run(s.id)} />
          ))}
        </div>
      )}
    </div>
  );
}
