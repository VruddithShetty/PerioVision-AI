import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

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
