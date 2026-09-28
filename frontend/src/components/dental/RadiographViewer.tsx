import clsx from "clsx";
import { Crosshair, Layers, Maximize2, Minus, Plus } from "lucide-react";
import { useCallback, useRef, useState, type PointerEvent, type WheelEvent } from "react";
import type { Tooth } from "@/api/types";
import { Skeleton, Toggle } from "@/components/ui/primitives";
import { useAuthedImage } from "@/hooks";
import { stageColor } from "@/lib/format";

export interface LayerState {
  detections: boolean;
  landmarks: boolean;
  boneLines: boolean;
  roi: boolean;
  heatmap: boolean;
}

/** Pan/zoom radiograph with toggleable AI layers drawn in image coordinates. */
export function RadiographViewer({ radiographUrl, gradcamUrl, width, height, teeth, selected, onSelect }: {
  radiographUrl?: string;
  gradcamUrl?: string;
  width: number;
  height: number;
  teeth: Tooth[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const base = useAuthedImage(radiographUrl);
  const heat = useAuthedImage(gradcamUrl);
  const [layers, setLayers] = useState<LayerState>({ detections: true, landmarks: true, boneLines: true, roi: false, heatmap: !!gradcamUrl });
  const [opacity, setOpacity] = useState(0.55);
  const [view, setView] = useState({ scale: 1, x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number; vx: number; vy: number } | null>(null);

  const zoom = useCallback((factor: number) => setView((v) => ({ ...v, scale: Math.min(6, Math.max(1, v.scale * factor)) })), []);
  const reset = () => setView({ scale: 1, x: 0, y: 0 });
  const onWheel = (e: WheelEvent) => {
    e.preventDefault();
    zoom(e.deltaY < 0 ? 1.15 : 1 / 1.15);
  };
  const onDown = (e: PointerEvent) => {
    (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
    drag.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y };
  };
  const onMove = (e: PointerEvent) => {
    if (!drag.current || view.scale === 1) return;
    setView((v) => ({ ...v, x: drag.current!.vx + (e.clientX - drag.current!.x), y: drag.current!.vy + (e.clientY - drag.current!.y) }));
  };
  const stroke = Math.max(2, width / 500);

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_220px]">
      <div className="relative overflow-hidden rounded-2xl border border-white/[0.06] bg-black" style={{ aspectRatio: `${width} / ${height}` }}>
        {!base.url && !base.error && <Skeleton className="absolute inset-0 rounded-none" />}
        {base.error && <p className="absolute inset-0 flex items-center justify-center text-sm text-critical-400">{base.error}</p>}
        <div
          className={clsx("absolute inset-0 touch-none", view.scale > 1 ? "cursor-grab active:cursor-grabbing" : "cursor-crosshair")}
          onWheel={onWheel}
          onPointerDown={onDown}
          onPointerMove={onMove}
          onPointerUp={() => (drag.current = null)}
          onDoubleClick={reset}
        >
          <div
            className="absolute inset-0 origin-center transition-transform duration-75"
            style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})` }}
          >
            {base.url && <img src={base.url} alt="Radiograph" className="absolute inset-0 h-full w-full object-contain" draggable={false} />}
            {layers.heatmap && heat.url && (
              <img src={heat.url} alt="Grad-CAM attention map" className="absolute inset-0 h-full w-full object-contain mix-blend-screen" style={{ opacity }} draggable={false} />
            )}
            <svg viewBox={`0 0 ${width} ${height}`} className="absolute inset-0 h-full w-full" preserveAspectRatio="xMidYMid meet">
              {teeth.map((t) => {
                const [x1, y1, x2, y2] = t.bbox;
                const active = t.tooth_id === selected;
                const color = stageColor(t.stage);
                return (
                  <g key={t.tooth_id} onClick={(e) => { e.stopPropagation(); onSelect(t.tooth_id); }} className="cursor-pointer">
                    {layers.roi && (
                      <rect x={t.roi[0]} y={t.roi[1]} width={t.roi[2] - t.roi[0]} height={t.roi[3] - t.roi[1]} fill="#fbbf24" fillOpacity={0.08} stroke="#fbbf24" strokeDasharray={`${stroke * 3} ${stroke * 2}`} strokeWidth={stroke * 0.6} />
                    )}
                    {layers.detections && (
                      <>
                        <rect x={x1} y={y1} width={x2 - x1} height={y2 - y1} rx={stroke * 2} fill={active ? `${color}22` : "transparent"} stroke={color} strokeWidth={active ? stroke * 1.8 : stroke} />
                        <rect x={x1} y={y1 - stroke * 14} width={stroke * 26} height={stroke * 12} rx={stroke * 2} fill={color} />
                        <text x={x1 + stroke * 13} y={y1 - stroke * 5} textAnchor="middle" fontSize={stroke * 8} fontWeight={700} fill="#03070f" fontFamily="JetBrains Mono, monospace">
                          {t.tooth_id}
                        </text>
                      </>
                    )}
                    {layers.boneLines && t.bone_loss_pct !== null && (
                      <line x1={t.cej[0]} y1={t.cej[1]} x2={t.abc[0]} y2={t.abc[1]} stroke="#fbbf24" strokeWidth={stroke * 1.4} />
                    )}
                    {layers.landmarks && (
                      <>
                        <circle cx={t.cej[0]} cy={t.cej[1]} r={stroke * 2.4} fill="#22d3ee" stroke="#03070f" strokeWidth={stroke * 0.5} />
                        <circle cx={t.abc[0]} cy={t.abc[1]} r={stroke * 2.4} fill="#fbbf24" stroke="#03070f" strokeWidth={stroke * 0.5} />
                        <circle cx={t.root_apex[0]} cy={t.root_apex[1]} r={stroke * 2} fill="#f472b6" stroke="#03070f" strokeWidth={stroke * 0.5} />
                      </>
                    )}
                  </g>
                );
              })}
            </svg>
          </div>
        </div>
        <div className="absolute bottom-3 right-3 flex gap-1 rounded-xl border border-white/10 bg-ink-950/80 p-1 backdrop-blur">
          <button className="rounded-lg p-1.5 hover:bg-white/10" onClick={() => zoom(1.25)} aria-label="Zoom in"><Plus className="h-4 w-4" /></button>
          <button className="rounded-lg p-1.5 hover:bg-white/10" onClick={() => zoom(0.8)} aria-label="Zoom out"><Minus className="h-4 w-4" /></button>
          <button className="rounded-lg p-1.5 hover:bg-white/10" onClick={reset} aria-label="Reset view"><Maximize2 className="h-4 w-4" /></button>
        </div>
        <div className="pointer-events-none absolute left-3 top-3 rounded-lg bg-ink-950/70 px-2 py-1 font-mono text-[10px] text-mist-400">
          {width}×{height} · {view.scale.toFixed(1)}×
        </div>
      </div>

      <div className="glass space-y-3 p-4">
        <p className="label flex items-center gap-1.5"><Layers className="h-3.5 w-3.5" /> Layers</p>
        <Toggle label="Tooth detections" checked={layers.detections} onChange={(v) => setLayers({ ...layers, detections: v })} />
        <Toggle label="CEJ / crest / apex" checked={layers.landmarks} onChange={(v) => setLayers({ ...layers, landmarks: v })} />
        <Toggle label="Bone-loss lines" checked={layers.boneLines} onChange={(v) => setLayers({ ...layers, boneLines: v })} />
        <Toggle label="Periodontal ROI" checked={layers.roi} onChange={(v) => setLayers({ ...layers, roi: v })} />
        <div className={clsx(!gradcamUrl && "opacity-40")}>
          <Toggle label="Grad-CAM heatmap" checked={layers.heatmap && !!gradcamUrl} onChange={(v) => gradcamUrl && setLayers({ ...layers, heatmap: v })} />
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={opacity}
            disabled={!gradcamUrl || !layers.heatmap}
            onChange={(e) => setOpacity(Number(e.target.value))}
            className="mt-2 w-full accent-cyan-400"
            aria-label="Heatmap opacity"
          />
          <p className="text-[11px] text-mist-500">{gradcamUrl ? `Opacity ${Math.round(opacity * 100)}%` : "Not available (no verified model in this run)"}</p>
        </div>
        <div className="border-t border-white/[0.06] pt-3 text-[11px] text-mist-400">
          <p className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full bg-brand-400" /> CEJ</p>
          <p className="mt-1 flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full bg-review-400" /> Alveolar crest</p>
          <p className="mt-1 flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full bg-pink-400" /> Root apex</p>
          <p className="mt-3 flex items-center gap-1.5 text-mist-500"><Crosshair className="h-3 w-3" /> Scroll to zoom · drag to pan · double-click to reset</p>
        </div>
      </div>
    </div>
  );
}
