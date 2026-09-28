import { useRef, useState } from "react";
import { Skeleton } from "@/components/ui/primitives";
import { useAuthedImage } from "@/hooks";

/** Drag the handle to compare two visits' radiographs (annotated layers) side by side. */
export function BeforeAfterSlider({ beforeUrl, afterUrl, beforeLabel, afterLabel }: {
  beforeUrl?: string;
  afterUrl?: string;
  beforeLabel: string;
  afterLabel: string;
}) {
  const before = useAuthedImage(beforeUrl);
  const after = useAuthedImage(afterUrl);
  const [pos, setPos] = useState(50);
  const ref = useRef<HTMLDivElement>(null);
  const move = (x: number) => {
    const box = ref.current?.getBoundingClientRect();
    if (box) setPos(Math.min(100, Math.max(0, ((x - box.left) / box.width) * 100)));
  };
  if (!before.url || !after.url) return <Skeleton className="aspect-[2/1] w-full" />;
  return (
    <div
      ref={ref}
      className="relative aspect-[2/1] w-full cursor-ew-resize select-none overflow-hidden rounded-2xl border border-white/[0.06] bg-black"
      onPointerDown={(e) => move(e.clientX)}
      onPointerMove={(e) => e.buttons === 1 && move(e.clientX)}
      role="slider"
      tabIndex={0}
      aria-label="Compare visits"
      aria-valuenow={Math.round(pos)}
      aria-valuemin={0}
      aria-valuemax={100}
      onKeyDown={(e) => {
        if (e.key === "ArrowLeft") setPos((p) => Math.max(0, p - 5));
        if (e.key === "ArrowRight") setPos((p) => Math.min(100, p + 5));
      }}
    >
      <img src={after.url} alt={`Radiograph ${afterLabel}`} className="absolute inset-0 h-full w-full object-contain" draggable={false} />
      <div className="absolute inset-0 overflow-hidden" style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }}>
        <img src={before.url} alt={`Radiograph ${beforeLabel}`} className="absolute inset-0 h-full w-full object-contain" draggable={false} />
      </div>
      <div className="absolute inset-y-0 w-0.5 bg-brand-300 shadow-[0_0_16px_#22d3ee]" style={{ left: `${pos}%` }}>
        <div className="absolute left-1/2 top-1/2 flex h-9 w-9 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border-2 border-brand-300 bg-ink-950 text-brand-300">
          ⇆
        </div>
      </div>
      <span className="absolute left-3 top-3 rounded-lg bg-ink-950/80 px-2 py-1 text-xs text-mist-300">{beforeLabel}</span>
      <span className="absolute right-3 top-3 rounded-lg bg-ink-950/80 px-2 py-1 text-xs text-brand-300">{afterLabel}</span>
    </div>
  );
}
