# frontend

The PerioVision AI web app: React 18 + Vite + TypeScript (strict), Tailwind CSS, React Router, TanStack Query, Zustand, Framer Motion, three.js (@react-three/fiber, drei, postprocessing) and Recharts.

```
src/
├── app/          router and providers (App.tsx)
├── pages/        one folder per page (15 pages)
├── components/   ui/ (design system), layout/ (shell, guards), charts/, dental/ (radiograph viewer, odontogram, tooth cross-section…)
├── three/        3D scenes: hero tooth, dental arch, hash chain, trust orb (lazy-loaded, static fallback)
├── api/          typed API client (silent token refresh) + TanStack Query hooks
├── store/        auth state (in memory only)
├── hooks/  lib/  styles/
```

Run (backend must be running on port 5000):

```bash
npm install
npm run dev      # http://localhost:5173 (proxies /api to the backend)
npm run build    # type-check + production bundle in dist/
npm run lint
```

3D scenes are skipped automatically on devices without WebGL, with 2 or fewer CPU cores, or when the OS asks for reduced motion. Force it off with `localStorage.setItem("pv-3d", "off")`.
