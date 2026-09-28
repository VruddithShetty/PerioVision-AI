import { AnimatePresence, motion } from "framer-motion";
import { Eye, Ruler, Target } from "lucide-react";
import type { Tooth } from "@/api/types";
import { Badge } from "@/components/ui/primitives";
import { FLAG_LABEL, fmtNum, fmtPct, stageColor } from "@/lib/format";
import { ToothCrossSection } from "./ToothCrossSection";

/** Uncertainty band on a 0–100 % scale with stage cut-offs. */
function IntervalBar({ value, interval }: { value: number | null; interval: [number, number] | null }) {
  return (
    <div>
      <div className="relative h-3 rounded-full bg-gradient-to-r from-teal-400/30 via-review-400/30 to-orange-400/30">
        <span className="absolute top-[-3px] h-[18px] w-px bg-white/30" style={{ left: "15%" }} />
        <span className="absolute top-[-3px] h-[18px] w-px bg-white/30" style={{ left: "33%" }} />
        {interval && (
          <motion.span
            className="absolute top-0 h-3 rounded-full border border-brand-300/80 bg-brand-400/30"
            initial={false}
            animate={{ left: `${interval[0]}%`, width: `${Math.max(1, interval[1] - interval[0])}%` }}
          />
        )}
        {value !== null && (
          <motion.span className="absolute -top-1 h-5 w-1.5 -translate-x-1/2 rounded-full bg-white shadow-[0_0_10px_white]" initial={false} animate={{ left: `${value}%` }} />
        )}
      </div>
      <div className="mt-1 flex justify-between font-mono text-[10px] text-mist-500">
        <span>0%</span>
        <span className="ml-[6%]">15</span>
        <span className="mr-[40%]">33</span>
        <span>100%</span>
      </div>
    </div>
  );
}

export function ToothPanel({ tooth, coverage }: { tooth: Tooth | null; coverage: number }) {
  return (
    <AnimatePresence mode="wait">
      {!tooth ? (
        <motion.div key="none" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex h-full min-h-[300px] flex-col items-center justify-center text-center text-sm text-mist-400">
          <Target className="mb-3 h-8 w-8 text-mist-500" />
          Select a tooth on the radiograph, the chart or the 3D arch.
        </motion.div>
      ) : (
        <motion.div key={tooth.tooth_id} initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -12 }} className="space-y-5">
          <div className="flex items-start justify-between">
            <div>
              <p className="label">Tooth {tooth.tooth_id_source === "model_fdi_class" ? "(FDI)" : `(${tooth.tooth_id_source.replace(/_/g, " ")})`}</p>
              <p className="font-display text-4xl font-bold">{tooth.tooth_id}</p>
            </div>
            <div className="rounded-2xl px-4 py-2 text-center" style={{ background: `${stageColor(tooth.stage)}18`, color: stageColor(tooth.stage) }}>
              <p className="text-[10px] uppercase tracking-widest">Stage</p>
              <p className="font-display text-2xl font-bold">{tooth.stage ?? "–"}</p>
            </div>
          </div>

          <div className="grid grid-cols-[110px_1fr] items-center gap-4">
            <ToothCrossSection boneLossPct={tooth.bone_loss_pct ?? 0} showLabels={false} className="h-32 w-auto" />
            <div>
              <p className="label">Radiographic bone loss</p>
              <p className="font-display text-4xl font-bold" style={{ color: stageColor(tooth.stage) }}>
                {fmtPct(tooth.bone_loss_pct)}
              </p>
              {tooth.cej_to_crest_mm != null && (
                <p className="flex items-center gap-1 text-xs text-mist-400"><Ruler className="h-3 w-3" /> CEJ→crest {tooth.cej_to_crest_mm} mm</p>
              )}
            </div>
          </div>

          <div>
            <p className="label mb-2">Conformal interval ({Math.round(coverage * 100)}% target coverage)</p>
            <IntervalBar value={tooth.bone_loss_pct} interval={tooth.uncertainty.interval} />
            <div className="mt-3 flex flex-wrap items-center gap-1.5">
              <span className="text-xs text-mist-400">Stage set:</span>
              {tooth.uncertainty.stage_set.map((s) => (
                <span key={s} className="rounded-md px-2 py-0.5 text-xs font-semibold" style={{ background: `${stageColor(s)}20`, color: stageColor(s) }}>
                  {s}
                </span>
              ))}
              {!tooth.uncertainty.calibrated && <Badge tone="review">uncalibrated</Badge>}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2 text-sm">
            <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
              <p className="label">Detection confidence</p>
              <p className="mt-1 font-mono">{tooth.confidence === null ? "demo" : fmtNum(tooth.confidence)}</p>
            </div>
            <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
              <p className="label flex items-center gap-1"><Eye className="h-3 w-3" /> ROI attention</p>
              <p className="mt-1 font-mono">{tooth.roi_attention === null ? "n/a" : `${Math.round(tooth.roi_attention * 100)}%`}</p>
            </div>
            <div className="col-span-2 rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
              <p className="label">Landmarks</p>
              <p className="mt-1 capitalize">{tooth.landmark_source.replace(/_/g, " ")}</p>
            </div>
          </div>

          {Object.entries(tooth.flags).some(([, v]) => v) && (
            <div className="space-y-1.5">
              {Object.entries(tooth.flags).filter(([, v]) => v).map(([k]) => (
                <div key={k} className="rounded-lg border border-review-500/30 bg-review-500/[0.08] px-3 py-1.5 text-xs text-review-400">
                  {FLAG_LABEL[k] ?? k}
                </div>
              ))}
            </div>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
