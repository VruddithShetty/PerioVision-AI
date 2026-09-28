import { create } from "zustand";
import type { Mode, Role, User } from "@/api/types";

/**
 * Auth state lives in memory only. The short-lived access token is never written to
 * localStorage (so an XSS bug cannot steal it from storage); after a page reload the app
 * asks /api/auth/refresh, which uses the httpOnly refresh cookie, for a new one.
 */
interface AuthState {
  accessToken: string | null;
  user: User | null;
  permissions: string[];
  mode: Mode | null;
  bootstrapped: boolean;
  setSession: (token: string, user?: User | null) => void;
  setUser: (user: User) => void;
  setMode: (mode: Mode) => void;
  clear: () => void;
  markBootstrapped: () => void;
}

export const useAuth = create<AuthState>((set) => ({
  accessToken: null,
  user: null,
  permissions: [],
  mode: null,
  bootstrapped: false,
  setSession: (token, user) =>
    set((s) => ({ accessToken: token, user: user ?? s.user, permissions: user?.permissions ?? s.permissions })),
  setUser: (user) => set({ user, permissions: user.permissions ?? [] }),
  setMode: (mode) => set({ mode }),
  clear: () => set({ accessToken: null, user: null, permissions: [] }),
  markBootstrapped: () => set({ bootstrapped: true }),
}));

export function useCan(permission: string): boolean {
  return useAuth((s) => s.permissions.includes(permission));
}

export const ROLE_LABEL: Record<Role, string> = {
  admin: "Administrator",
  dentist: "Dentist",
  technician: "Technician",
  auditor: "Auditor",
};
