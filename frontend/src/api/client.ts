import { useAuth } from "@/store/auth";
import type { Envelope } from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public details?: unknown,
  ) {
    super(message);
  }
}

let refreshing: Promise<boolean> | null = null;

/** Ask for a new access token using the httpOnly refresh cookie. Concurrent callers share one request. */
export function refreshAccessToken(): Promise<boolean> {
  if (!refreshing) {
    refreshing = fetch("/api/auth/refresh", { method: "POST", credentials: "include" })
      .then(async (res) => {
        if (!res.ok) return false;
        const body = (await res.json()) as Envelope<{ access_token: string }>;
        useAuth.getState().setSession(body.data.access_token);
        useAuth.getState().setMode(body.mode);
        return true;
      })
      .catch(() => false)
      .finally(() => {
        refreshing = null;
      });
  }
  return refreshing;
}

interface Options {
  method?: string;
  body?: unknown;
  form?: FormData;
  auth?: boolean;
  signal?: AbortSignal;
}

async function raw(path: string, opts: Options, retry = true): Promise<Response> {
  const headers: Record<string, string> = {};
  const token = useAuth.getState().accessToken;
  if (opts.auth !== false && token) headers.Authorization = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  const res = await fetch(path, {
    method: opts.method ?? (body ? "POST" : "GET"),
    headers,
    body,
    credentials: "include",
    signal: opts.signal,
  });
  if (res.status === 401 && retry && opts.auth !== false && !path.startsWith("/api/auth/")) {
    if (await refreshAccessToken()) return raw(path, opts, false);
    useAuth.getState().clear();
  }
  return res;
}

export async function api<T>(path: string, opts: Options = {}): Promise<{ data: T; meta: Record<string, unknown> }> {
  let res: Response;
  try {
    res = await raw(path, opts);
  } catch {
    throw new ApiError(0, "Cannot reach the PerioVision server. Is the backend running on port 5000?");
  }
  let body: Envelope<T> | null = null;
  try {
    body = (await res.json()) as Envelope<T>;
  } catch {
    /* non-JSON response */
  }
  if (body?.mode) useAuth.getState().setMode(body.mode);
  if (!res.ok || body?.error) {
    throw new ApiError(res.status, body?.error?.message ?? `Request failed (${res.status})`, body?.error?.details);
  }
  return { data: (body as Envelope<T>).data, meta: (body as Envelope<T>).meta ?? {} };
}

/** Fetch a protected binary (radiograph layer, PDF) and return an object URL. */
export async function apiBlob(path: string): Promise<Blob> {
  const res = await raw(path, {});
  if (!res.ok) throw new ApiError(res.status, `Could not load file (${res.status})`);
  return res.blob();
}

export async function downloadFile(path: string, filename: string): Promise<void> {
  const blob = await apiBlob(path);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
