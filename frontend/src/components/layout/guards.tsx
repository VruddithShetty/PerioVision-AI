import { useEffect, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { api, refreshAccessToken } from "@/api/client";
import type { User } from "@/api/types";
import { Spinner } from "@/components/ui/primitives";
import { useAuth } from "@/store/auth";
import AccessDeniedPage from "@/pages/errors/AccessDeniedPage";

/** Restore a session after reload (refresh cookie), then load the user and their permissions. */
// eslint-disable-next-line react-refresh/only-export-components
export function useBootstrapSession() {
  const { bootstrapped, markBootstrapped, setUser } = useAuth();
  useEffect(() => {
    if (bootstrapped) return;
    (async () => {
      try {
        if (!useAuth.getState().accessToken) await refreshAccessToken();
        if (useAuth.getState().accessToken) {
          const { data } = await api<User>("/api/auth/me");
          setUser(data);
        }
      } catch {
        useAuth.getState().clear();
      } finally {
        markBootstrapped();
      }
    })();
  }, [bootstrapped, markBootstrapped, setUser]);
  return bootstrapped;
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const ready = useBootstrapSession();
  const token = useAuth((s) => s.accessToken);
  const user = useAuth((s) => s.user);
  const location = useLocation();
  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner label="Checking your session" />
      </div>
    );
  }
  if (!token || !user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <>{children}</>;
}

/** Hide routes the role cannot use. The backend enforces the same rule on every request. */
export function RequirePermission({ permission, children }: { permission: string; children: ReactNode }) {
  const allowed = useAuth((s) => s.permissions.includes(permission));
  return allowed ? <>{children}</> : <AccessDeniedPage embedded permission={permission} />;
}
