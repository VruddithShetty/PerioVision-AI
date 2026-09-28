import { Link } from "react-router-dom";

export function Logo({ compact = false, to = "/" }: { compact?: boolean; to?: string }) {
  return (
    <Link to={to} className="flex items-center gap-2.5" aria-label="PerioVision AI home">
      <svg viewBox="0 0 64 64" className="h-8 w-8" aria-hidden>
        <defs>
          <linearGradient id="pv-logo" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#67e8f9" />
            <stop offset="1" stopColor="#14b8a6" />
          </linearGradient>
        </defs>
        <path d="M32 4 8 13v17c0 15 10 26 24 30 14-4 24-15 24-30V13L32 4Z" fill="#060d1a" stroke="url(#pv-logo)" strokeWidth="3" />
        <path
          d="M22 22c3-3 7-3 10-1 3-2 7-2 10 1 3 4 1 9-1 13l-2 9c-1 3-4 3-5 0l-2-7-2 7c-1 3-4 3-5 0l-2-9c-2-4-4-9-1-13Z"
          fill="url(#pv-logo)"
        />
      </svg>
      {!compact && (
        <span className="font-display text-lg font-bold tracking-tight text-mist-100">
          Perio<span className="text-brand-400">Vision</span>
          <span className="ml-1 text-xs font-semibold text-mist-500">AI</span>
        </span>
      )}
    </Link>
  );
}
