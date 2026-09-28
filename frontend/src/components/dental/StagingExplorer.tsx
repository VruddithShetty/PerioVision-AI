import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { stageColor } from "@/lib/format";
import { ToothCrossSection } from "./ToothCrossSection";

const STAGES = [
  { stage: "I", range: "< 15 %", title: "Initial periodontitis", text: "Bone loss confined to the coronal third of the root. Usually reversible with good hygiene and debridement." },
  { stage: "II", range: "15 – 33 %", title: "Moderate periodontitis", text: "Bone loss reaches toward the middle third. Non-surgical therapy and closer monitoring are indicated." },
  { stage: "III", range: "> 33 %", title: "Severe periodontitis", text: "Bone loss extends to the middle third or beyond, with risk of losing teeth. Specialist care is often needed." },
  { stage: "IV", range: "> 33 % + ≥ 5 teeth lost", title: "Severe, with tooth loss", text: "As stage III, plus loss of five or more teeth to periodontitis and complex rehabilitation needs." },
];

const stageOf = (p: number) => (p < 15 ? "I" : p <= 33 ? "II" : "III");

/** Drag the slider to watch the bone crest recede and the 2017 AAP/EFP stage change. */
export function StagingExplorer() {
  const [pct, setPct] = useState(22);
  const stage = stageOf(pct);
  const info = STAGES.find((s) => s.stage === stage)!;
  return (
    <div className="grid items-center gap-8 md:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <div className="glass relative overflow-hidden p-4">
        <ToothCrossSection boneLossPct={pct} className="mx-auto h-[320px] w-auto" />
      </div>
      <div>
        <p className="label text-brand-300">Try it · radiographic bone loss</p>
        <div className="mt-3 flex items-baseline gap-3">
          <span className="font-display text-6xl font-bold" style={{ color: stageColor(stage) }}>
            {pct}%
          </span>
          <span className="text-mist-400">of root length below the CEJ</span>
        </div>
        <input
          type="range"
          min={0}
          max={80}
          value={pct}
          onChange={(e) => setPct(Number(e.target.value))}
          className="mt-6 w-full accent-cyan-400"
          aria-label="Bone loss percentage"
        />
        <div className="mt-2 flex justify-between text-[11px] text-mist-500">
          <span>0%</span>
          <span>15%</span>
          <span>33%</span>
          <span>80%</span>
        </div>
        <AnimatePresence mode="wait">
          <motion.div
            key={stage}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="mt-6 rounded-2xl border p-5"
            style={{ borderColor: `${stageColor(stage)}55`, background: `${stageColor(stage)}10` }}
          >
            <p className="label" style={{ color: stageColor(stage) }}>
              Stage {info.stage} · {info.range}
            </p>
            <p className="mt-1 font-display text-xl font-semibold">{info.title}</p>
            <p className="mt-2 text-sm text-mist-300">{info.text}</p>
          </motion.div>
        </AnimatePresence>
        <div className="mt-4 grid grid-cols-4 gap-2">
          {STAGES.map((s) => (
            <div
              key={s.stage}
              className="rounded-lg border px-2 py-1.5 text-center text-xs transition"
              style={{
                borderColor: s.stage === stage ? stageColor(s.stage) : "rgba(255,255,255,0.08)",
                color: s.stage === stage ? stageColor(s.stage) : "#7f93b0",
              }}
            >
              Stage {s.stage}
            </div>
          ))}
        </div>
        <p className="mt-3 text-xs text-mist-500">
          Stage bands follow the 2017 AAP/EFP classification (Tonetti et al., 2018). Stage IV also needs the tooth-loss history
          that only a clinician can enter.
        </p>
      </div>
    </div>
  );
}
