import clsx from "clsx";
import type { Tooth } from "@/api/types";
import { stageColor } from "@/lib/format";

const UPPER_RIGHT = ["18", "17", "16", "15", "14", "13", "12", "11"];
const UPPER_LEFT = ["21", "22", "23", "24", "25", "26", "27", "28"];
const LOWER_RIGHT = ["48", "47", "46", "45", "44", "43", "42", "41"];
const LOWER_LEFT = ["31", "32", "33", "34", "35", "36", "37", "38"];

/** FDI dental chart. Detected teeth are coloured by stage; missing/undetected teeth are faint. */
export function Odontogram({ teeth, selected, onSelect }: { teeth: Tooth[]; selected: string | null; onSelect: (id: string) => void }) {
  const byId = new Map(teeth.map((t) => [t.tooth_id, t]));
  const nonFdi = teeth.filter((t) => !/^[1-4][1-8]$/.test(t.tooth_id));

  const cell = (id: string, upper: boolean) => {
    const t = byId.get(id);
    const molar = Number(id[1]) >= 6;
    const active = selected === id;
    return (
      <button
        key={id}
        disabled={!t}
        onClick={() => t && onSelect(id)}
        title={t ? `Tooth ${id}: ${t.bone_loss_pct ?? "n/a"}% · Stage ${t.stage ?? "–"}` : `Tooth ${id}: not detected`}
        className={clsx("group flex flex-col items-center gap-1 transition", !t && "cursor-default opacity-25", t && "hover:-translate-y-0.5")}
      >
        {!upper && <span className={clsx("font-mono text-[10px]", active ? "text-brand-300" : "text-mist-500")}>{id}</span>}
        <svg viewBox="0 0 24 34" className={clsx(molar ? "w-7" : "w-5", "h-9")} aria-hidden>
          <g transform={upper ? "" : "rotate(180 12 17)"}>
            <path
              d={molar ? "M3 13c0-7 4-10 9-10s9 3 9 10c0 3-1 5-2 6l-1 12c0 2-3 2-3 0l-1-8h-4l-1 8c0 2-3 2-3 0l-1-12c-1-1-2-3-2-6Z" : "M5 12c0-6 3-9 7-9s7 3 7 9c0 3-1 5-2 6l-2 13c0 2-4 2-4 0l-2-13c-1-1-2-3-2-6Z"}
              fill={t ? stageColor(t.stage) : "#1a3050"}
              fillOpacity={t ? (active ? 1 : 0.75) : 1}
              stroke={active ? "#e6f1ff" : "transparent"}
              strokeWidth="1.4"
            />
            {t?.bone_loss_pct != null && (
              <line x1="2" x2="22" y1={13 + (t.bone_loss_pct / 100) * 18} y2={13 + (t.bone_loss_pct / 100) * 18} stroke="#03070f" strokeWidth="1.2" strokeDasharray="2 1.5" />
            )}
          </g>
        </svg>
        {upper && <span className={clsx("font-mono text-[10px]", active ? "text-brand-300" : "text-mist-500")}>{id}</span>}
      </button>
    );
  };

  return (
    <div>
      <div className="overflow-x-auto">
        <div className="mx-auto w-fit min-w-[560px] space-y-3">
          <div className="flex items-end justify-center gap-1">
            {UPPER_RIGHT.map((id) => cell(id, true))}
            <span className="mx-2 h-10 w-px bg-white/10" />
            {UPPER_LEFT.map((id) => cell(id, true))}
          </div>
          <div className="h-px bg-gradient-to-r from-transparent via-white/15 to-transparent" />
          <div className="flex items-start justify-center gap-1">
            {LOWER_RIGHT.map((id) => cell(id, false))}
            <span className="mx-2 h-10 w-px bg-white/10" />
            {LOWER_LEFT.map((id) => cell(id, false))}
          </div>
        </div>
      </div>
      {nonFdi.length > 0 && (
        <div className="mt-4">
          <p className="label mb-2">Teeth without a model-assigned FDI number</p>
          <div className="flex flex-wrap gap-1.5">
            {nonFdi.map((t) => (
              <button
                key={t.tooth_id}
                onClick={() => onSelect(t.tooth_id)}
                className={clsx("rounded-lg border px-2 py-1 font-mono text-xs transition", selected === t.tooth_id ? "border-brand-400 text-brand-300" : "border-white/10 text-mist-300 hover:border-white/25")}
                style={{ boxShadow: `inset 3px 0 0 ${stageColor(t.stage)}` }}
              >
                {t.tooth_id}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
