/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { 950: "#03070f", 900: "#060d1a", 800: "#0a1628", 700: "#10213a", 600: "#1a3050" },
        cyan: { DEFAULT: "#22d3ee" },
        brand: { 300: "#67e8f9", 400: "#22d3ee", 500: "#06b6d4", 600: "#0891b2" },
        teal: { 400: "#2dd4bf", 500: "#14b8a6" },
        review: { 400: "#fbbf24", 500: "#f59e0b" },
        critical: { 400: "#f87171", 500: "#ef4444" },
        mist: { 100: "#e6f1ff", 300: "#a9bcd6", 400: "#7f93b0", 500: "#5b6f8c" },
      },
      fontFamily: {
        display: ["Syne", "ui-sans-serif", "system-ui", "sans-serif"],
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        glass: "0 1px 0 0 rgba(148,210,255,0.06) inset, 0 20px 40px -24px rgba(0,0,0,0.8)",
        glow: "0 0 0 1px rgba(34,211,238,0.35), 0 0 24px -4px rgba(34,211,238,0.45)",
      },
      backgroundImage: {
        grid: "linear-gradient(rgba(125,211,252,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(125,211,252,0.05) 1px, transparent 1px)",
      },
      keyframes: {
        shimmer: { "100%": { transform: "translateX(100%)" } },
        scan: { "0%": { top: "0%" }, "50%": { top: "100%" }, "100%": { top: "0%" } },
      },
      animation: { shimmer: "shimmer 1.4s infinite" },
    },
  },
  plugins: [],
};
