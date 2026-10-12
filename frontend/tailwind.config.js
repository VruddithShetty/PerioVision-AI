const v = (name) => `rgb(var(--${name}) / <alpha-value>)`;

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      // Every palette colour is a CSS variable (src/styles/index.css), so the whole app follows the light / dark theme.
      colors: {
        ink: { 950: v("ink-950"), 900: v("ink-900"), 800: v("ink-800"), 700: v("ink-700"), 600: v("ink-600") },
        cyan: { DEFAULT: v("brand-400") },
        brand: { 300: v("brand-300"), 400: v("brand-400"), 500: v("brand-500"), 600: v("brand-600") },
        teal: { 400: v("teal-400"), 500: v("teal-500") },
        review: { 400: v("review-400"), 500: v("review-500") },
        critical: { 400: v("critical-400"), 500: v("critical-500") },
        mist: { 100: v("mist-100"), 300: v("mist-300"), 400: v("mist-400"), 500: v("mist-500") },
        // "white" is used as a translucent overlay (borders, hover tints): white on dark, navy on light
        white: v("overlay"),
        onaccent: v("on-accent"), // text on the sky / cyan buttons: white on light, near-black on dark
      },
      fontFamily: {
        display: ["Syne", "ui-sans-serif", "system-ui", "sans-serif"],
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        glass: "var(--shadow-glass)",
        glow: "0 0 0 1px rgba(34,211,238,0.35), 0 0 24px -4px rgba(34,211,238,0.45)",
      },
      backgroundImage: {
        grid: "linear-gradient(var(--grid-line) 1px, transparent 1px), linear-gradient(90deg, var(--grid-line) 1px, transparent 1px)",
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
