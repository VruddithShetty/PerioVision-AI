import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// Security headers for the production build served by `vite preview` (`.\run.ps1 frontend-prod`); the same
// policy is in vercel.json. Not applied to the dev server, whose hot reload needs inline scripts and websockets.
const SECURITY_HEADERS: Record<string, string> = {
  "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob:; connect-src 'self'; frame-src 'self' blob:; worker-src 'self' blob:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'",
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
  "Cross-Origin-Opener-Policy": "same-origin",
};

// The dev server proxies /api to the Flask backend, so the browser sees one origin
// (the refresh-token cookie stays SameSite=Strict and no CORS is needed in development).
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: {
    port: 5173,
    strictPort: true,
    proxy: { "/api": { target: process.env.VITE_API_TARGET ?? "http://127.0.0.1:5000", changeOrigin: false } },
  },
  // `vite preview` serves the production build the same way (one origin, /api proxied).
  preview: {
    port: 4173,
    strictPort: true,
    headers: SECURITY_HEADERS,
    proxy: { "/api": { target: process.env.VITE_API_TARGET ?? "http://127.0.0.1:5000", changeOrigin: false } },
  },
  build: {
    sourcemap: false,
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        manualChunks: {
          three: ["three", "@react-three/fiber", "@react-three/drei", "@react-three/postprocessing"],
          charts: ["recharts"],
          react: ["react", "react-dom", "react-router-dom", "@tanstack/react-query", "zustand", "framer-motion"],
        },
      },
    },
  },
});
