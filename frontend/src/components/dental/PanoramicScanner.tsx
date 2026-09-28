import { useMemo, useRef, useState } from "react";
import { stageColor } from "@/lib/format";

/**
 * Interactive illustrated panoramic radiograph. Drag the scan bar (or use the arrow keys) to reveal
 * the AI layer: tooth numbers, CEJ and crest markers, bone-loss lines and an attention heatmap.
 * Pure SVG illustration: no patient data.
 */
const UPPER = ["18", "17", "16", "15", "14", "13", "12", "11", "21", "22", "23", "24", "25", "26", "27", "28"];
const LOWER = ["48", "47", "46", "45", "44", "43", "42", "41", "31", "32", "33", "34", "35", "36", "37", "38"];
const LOSS: Record<string, number> = { "16": 34, "15": 22, "14": 12, "26": 28, "27": 38, "46": 24, "36": 30, "31": 9, "41": 11 };

function stageFor(p: number) {
  return p < 15 ? "I" : p <= 33 ? "II" : "III";
}

export function PanoramicScanner() {
  const [reveal, setReveal] = useState(58);
  const ref = useRef<SVGSVGElement>(null);
  const W = 960;
  const H = 400;

  const teeth = useMemo(() => {
    const make = (ids: string[], upper: boolean) =>
      ids.map((id, i) => {
        const t = i / (ids.length - 1);
        const x = 70 + t * (W - 140);
        const curve = Math.pow(t - 0.5, 2) * 120;
        const molar = Math.abs(t - 0.5) > 0.3;
        const w = molar ? 46 : 34;
        const crownY = upper ? 150 - curve * 0.35 : 250 + curve * 0.35;
        const rootLen = molar ? 92 : 104;
        const loss = LOSS[id] ?? 6 + ((i * 7) % 9);
        return { id, x, w, crownY, rootLen, upper, loss };
      });
    return [...make(UPPER, true), ...make(LOWER, false)];
  }, []);

  const move = (clientX: number) => {
    const box = ref.current?.getBoundingClientRect();
    if (!box) return;
    setReveal(Math.min(100, Math.max(0, ((clientX - box.left) / box.width) * 100)));
  };

  const revealX = (reveal / 100) * W;

  return (
    <div className="relative select-none">
      <svg
        ref={ref}
        viewBox={`0 0 ${W} ${H}`}
        className="w-full cursor-ew-resize touch-none rounded-2xl"
        onPointerMove={(e) => e.buttons === 1 && move(e.clientX)}
        onPointerDown={(e) => move(e.clientX)}
        role="slider"
        aria-label="Reveal the AI analysis layer"
        aria-valuenow={Math.round(reveal)}
        aria-valuemin={0}
        aria-valuemax={100}
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "ArrowLeft") setReveal((r) => Math.max(0, r - 4));
          if (e.key === "ArrowRight") setReveal((r) => Math.min(100, r + 4));
        }}
      >
        <defs>
          <radialGradient id="xray-bg" cx="50%" cy="50%" r="70%">
            <stop offset="0" stopColor="#1b2a3a" />
            <stop offset="1" stopColor="#05080d" />
          </radialGradient>
          <radialGradient id="heat" cx="50%" cy="50%" r="50%">
            <stop offset="0" stopColor="#ef4444" stopOpacity="0.7" />
            <stop offset="0.5" stopColor="#f59e0b" stopOpacity="0.35" />
            <stop offset="1" stopColor="#22d3ee" stopOpacity="0" />
          </radialGradient>
          <filter id="xray-blur">
            <feGaussianBlur stdDeviation="1.4" />
          </filter>
          <clipPath id="ai-clip">
            <rect x="0" y="0" width={revealX} height={H} />
          </clipPath>
        </defs>
        <rect width={W} height={H} fill="url(#xray-bg)" />
        {/* jaw bone silhouettes */}
        <path d={`M40 120 Q${W / 2} 60 ${W - 40} 120 L${W - 40} 200 Q${W / 2} 170 40 200 Z`} fill="#6b7b8c" opacity="0.28" filter="url(#xray-blur)" />
        <path d={`M40 280 Q${W / 2} 340 ${W - 40} 280 L${W - 40} 210 Q${W / 2} 235 40 210 Z`} fill="#6b7b8c" opacity="0.28" filter="url(#xray-blur)" />

        {/* teeth (radiograph look) */}
        <g filter="url(#xray-blur)">
          {teeth.map((t) => {
            const dir = t.upper ? -1 : 1;
            const rootEnd = t.crownY + dir * t.rootLen;
            return (
              <g key={t.id}>
                <path
                  d={`M${t.x - t.w * 0.28} ${t.crownY} L${t.x - t.w * 0.12} ${rootEnd} L${t.x + t.w * 0.12} ${rootEnd} L${t.x + t.w * 0.28} ${t.crownY} Z`}
                  fill="#c9d6e2"
                  opacity="0.55"
                />
                <rect x={t.x - t.w / 2} y={t.upper ? t.crownY : t.crownY - 34} width={t.w} height={34} rx={9} fill="#eef5fb" opacity="0.85" />
              </g>
            );
          })}
        </g>

        {/* AI layer */}
        <g clipPath="url(#ai-clip)">
          <rect width={W} height={H} fill="#22d3ee" opacity="0.04" />
          {teeth.map((t) => {
            const dir = t.upper ? -1 : 1;
            const cej = t.crownY;
            const crest = cej + dir * (6 + (t.rootLen - 6) * (t.loss / 100));
            const color = stageColor(stageFor(t.loss));
            return (
              <g key={`ai-${t.id}`}>
                {t.loss > 20 && <circle cx={t.x} cy={(cej + crest) / 2} r={28} fill="url(#heat)" />}
                <rect
                  x={t.x - t.w / 2 - 3}
                  y={t.upper ? t.crownY - t.rootLen - 4 : t.crownY - 38}
                  width={t.w + 6}
                  height={t.rootLen + 42}
                  rx={6}
                  fill="none"
                  stroke={color}
                  strokeOpacity="0.8"
                  strokeWidth="1.3"
                />
                <line x1={t.x - t.w / 2} x2={t.x + t.w / 2} y1={cej} y2={cej} stroke="#22d3ee" strokeWidth="1.4" />
                <line x1={t.x} x2={t.x} y1={cej} y2={crest} stroke="#fbbf24" strokeWidth="2.2" />
                <circle cx={t.x} cy={crest} r={3} fill="#fbbf24" />
                <text
                  x={t.x}
                  y={t.upper ? t.crownY - t.rootLen - 10 : t.crownY + t.rootLen + 18}
                  textAnchor="middle"
                  fontSize="11"
                  fontFamily="JetBrains Mono, monospace"
                  fill={color}
                >
                  {t.id}·{t.loss}%
                </text>
              </g>
            );
          })}
        </g>

        {/* scan bar */}
        <g>
          <rect x={revealX - 1} y="0" width="2" height={H} fill="#67e8f9" />
          <rect x={revealX - 40} y="0" width="40" height={H} fill="url(#scanglow)" opacity="0.4" />
          <circle cx={revealX} cy={H / 2} r="14" fill="#03070f" stroke="#67e8f9" strokeWidth="2" />
          <path d={`M${revealX - 5} ${H / 2} l-4 0 M${revealX + 5} ${H / 2} l4 0`} stroke="#67e8f9" strokeWidth="2" />
        </g>
        <defs>
          <linearGradient id="scanglow" x1="0" x2="1">
            <stop offset="0" stopColor="#22d3ee" stopOpacity="0" />
            <stop offset="1" stopColor="#22d3ee" stopOpacity="0.6" />
          </linearGradient>
        </defs>
      </svg>
      <div className="pointer-events-none absolute left-4 top-4 flex gap-2 text-[11px]">
        <span className="rounded-full bg-ink-950/80 px-2.5 py-1 text-brand-300">AI layer</span>
        <span className="rounded-full bg-ink-950/80 px-2.5 py-1 text-mist-400">Radiograph</span>
      </div>
    </div>
  );
}
