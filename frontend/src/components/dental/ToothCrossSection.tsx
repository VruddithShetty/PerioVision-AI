import { motion } from "framer-motion";

/**
 * Anatomical tooth cross-section (crown, CEJ, root, pulp, periodontal ligament, alveolar bone, gingiva).
 * `boneLossPct` moves the alveolar crest down the root, which is exactly what radiographic bone loss measures.
 */
export function ToothCrossSection({ boneLossPct, className = "", showLabels = true }: {
  boneLossPct: number;
  className?: string;
  showLabels?: boolean;
}) {
  const cejY = 118;
  const apexY = 300;
  const crestY = cejY + 8 + ((apexY - cejY - 8) * Math.min(Math.max(boneLossPct, 0), 90)) / 100;
  const gumY = crestY - 14;
  return (
    <svg viewBox="0 0 320 340" className={className} role="img" aria-label={`Tooth with ${boneLossPct.toFixed(0)}% bone loss`}>
      <defs>
        <linearGradient id="enamel" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#f8fdff" />
          <stop offset="1" stopColor="#cfe9f5" />
        </linearGradient>
        <linearGradient id="dentin" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#f3e7c9" />
          <stop offset="1" stopColor="#d9c393" />
        </linearGradient>
        <pattern id="trabecular" width="10" height="10" patternUnits="userSpaceOnUse">
          <rect width="10" height="10" fill="#b9a27a" />
          <circle cx="3" cy="3" r="1.6" fill="#8e7a55" />
          <circle cx="8" cy="7" r="1.1" fill="#8e7a55" />
        </pattern>
        <clipPath id="below-crest">
          <motion.rect initial={false} x="0" width="320" height="340" animate={{ y: crestY }} transition={{ type: "spring", damping: 20 }} />
        </clipPath>
      </defs>

      {/* alveolar bone (only below the crest) */}
      <g clipPath="url(#below-crest)">
        <rect x="20" y="0" width="280" height="330" rx="18" fill="url(#trabecular)" opacity="0.95" />
      </g>
      <motion.line initial={false} x1="20" x2="300" animate={{ y1: crestY, y2: crestY }} stroke="#fbbf24" strokeWidth="2" strokeDasharray="6 5" />

      {/* gingiva */}
      <motion.path
        initial={false}
        animate={{ d: `M20 ${gumY} Q80 ${gumY - 26} 112 ${gumY - 8} L112 ${gumY + 40} L20 ${gumY + 40} Z` }}
        fill="#f9a8d4"
        opacity="0.75"
      />
      <motion.path
        initial={false}
        animate={{ d: `M300 ${gumY} Q240 ${gumY - 26} 208 ${gumY - 8} L208 ${gumY + 40} L300 ${gumY + 40} Z` }}
        fill="#f9a8d4"
        opacity="0.75"
      />

      {/* periodontal ligament */}
      <path d="M108 118 C104 200 116 270 150 306 M212 118 C216 200 204 270 170 306" stroke="#fda4af" strokeWidth="5" fill="none" opacity="0.8" />
      {/* root (dentin) */}
      <path d="M112 118 C108 200 120 268 152 300 L168 300 C200 268 212 200 208 118 Z" fill="url(#dentin)" />
      {/* pulp */}
      <path d="M146 60 C140 110 142 200 156 290 L164 290 C178 200 180 110 174 60 Z" fill="#fb7185" opacity="0.8" />
      {/* crown (enamel) */}
      <path d="M92 58 C92 20 120 12 140 24 C150 14 170 14 180 24 C200 12 228 20 228 58 C228 90 214 108 208 118 L112 118 C106 108 92 90 92 58 Z" fill="url(#enamel)" stroke="#a5f3fc" strokeWidth="1.5" />
      {/* CEJ line */}
      <line x1="100" x2="220" y1={cejY} y2={cejY} stroke="#22d3ee" strokeWidth="2" />

      {/* measurement bracket */}
      <line x1="240" x2="240" y1={cejY} y2={apexY} stroke="#7f93b0" strokeWidth="1" />
      <motion.line initial={false} x1="236" x2="244" animate={{ y1: crestY, y2: crestY }} stroke="#fbbf24" strokeWidth="2" />
      <motion.line initial={false} x1="240" x2="240" y1={cejY} animate={{ y2: crestY }} stroke="#fbbf24" strokeWidth="3" />

      {showLabels && (
        <g fontFamily="Inter, sans-serif" fontSize="11" fill="#a9bcd6">
          <text x="250" y={cejY + 4} fill="#67e8f9">CEJ</text>
          <motion.text initial={false} x="250" animate={{ y: crestY + 4 }} fill="#fbbf24">Bone crest</motion.text>
          <text x="250" y={apexY + 4}>Root apex</text>
          <text x="24" y="40" fill="#e6f1ff">Enamel</text>
          <text x="24" y="330">Alveolar bone</text>
        </g>
      )}
    </svg>
  );
}
