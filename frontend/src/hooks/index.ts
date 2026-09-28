import { useEffect, useState } from "react";
import { apiBlob } from "@/api/client";

/** True when the user asked the OS for reduced motion. */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return reduced;
}

/** Heuristic for weak laptops: few CPU cores, low memory, or no WebGL. 3D scenes are skipped then. */
export function useLowPower(): boolean {
  const [low] = useState(() => {
    if (typeof window === "undefined") return true;
    const nav = navigator as Navigator & { deviceMemory?: number };
    const fewCores = (nav.hardwareConcurrency ?? 8) <= 2;
    const lowMemory = (nav.deviceMemory ?? 8) <= 2;
    let webgl = false;
    try {
      const canvas = document.createElement("canvas");
      webgl = !!(canvas.getContext("webgl2") || canvas.getContext("webgl"));
    } catch {
      webgl = false;
    }
    return fewCores || lowMemory || !webgl || localStorage.getItem("pv-3d") === "off";
  });
  return low;
}

/** Load a protected image (needs the Bearer token) and expose it as an object URL. */
export function useAuthedImage(path?: string | null) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!path) return;
    let revoked = false;
    let objectUrl: string | null = null;
    setError(null);
    apiBlob(path)
      .then((blob) => {
        if (revoked) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch((e: Error) => !revoked && setError(e.message));
    return () => {
      revoked = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [path]);
  return { url, error };
}

export function useDebounced<T>(value: T, delay = 300): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return v;
}
