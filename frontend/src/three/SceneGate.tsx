import { Component, Suspense, type ReactNode } from "react";
import { useLowPower, useReducedMotion } from "@/hooks";

/**
 * Wraps every 3D scene. The three.js bundle is only downloaded when a scene is actually shown
 * (scenes are React.lazy imports), and on weak devices, without WebGL, or with
 * prefers-reduced-motion the static fallback is rendered instead. A WebGL crash also falls back.
 */
class SceneErrorBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

export function SceneGate({ children, fallback, allowReducedMotion = false }: {
  children: ReactNode;
  fallback: ReactNode;
  allowReducedMotion?: boolean;
}) {
  const reduced = useReducedMotion();
  const low = useLowPower();
  if (low || (reduced && !allowReducedMotion)) return <>{fallback}</>;
  return (
    <SceneErrorBoundary fallback={fallback}>
      <Suspense fallback={fallback}>{children}</Suspense>
    </SceneErrorBoundary>
  );
}

/** Static stand-in: a glowing tooth silhouette drawn with SVG. */
export function StaticToothArt({ className = "" }: { className?: string }) {
  return (
    <div className={`relative flex items-center justify-center ${className}`}>
      <div className="absolute h-64 w-64 rounded-full bg-brand-400/10 blur-3xl" />
      <svg viewBox="0 0 200 240" className="relative h-64 w-auto drop-shadow-[0_0_30px_rgba(34,211,238,0.35)]" aria-hidden>
        <defs>
          <linearGradient id="tooth-g" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#e6f1ff" />
            <stop offset="0.55" stopColor="#67e8f9" />
            <stop offset="1" stopColor="#14b8a6" stopOpacity="0.6" />
          </linearGradient>
        </defs>
        <path
          d="M40 40c20-26 50-24 60-10 10-14 40-16 60 10 18 24 6 60-4 84l-12 80c-3 18-22 18-26 0l-12-60c-2-8-10-8-12 0l-12 60c-4 18-23 18-26 0l-12-80c-10-24-22-60-4-84Z"
          fill="url(#tooth-g)"
          opacity="0.9"
        />
        <path d="M30 118h140" stroke="#fbbf24" strokeDasharray="6 6" strokeWidth="2" opacity="0.7" />
      </svg>
    </div>
  );
}
