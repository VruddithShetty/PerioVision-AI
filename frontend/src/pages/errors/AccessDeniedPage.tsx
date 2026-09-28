import { ShieldX } from "lucide-react";
import { Link } from "react-router-dom";
import { ROLE_LABEL, useAuth } from "@/store/auth";

export default function AccessDeniedPage({ embedded = false, permission }: { embedded?: boolean; permission?: string }) {
  const role = useAuth((s) => s.user?.role);
  return (
    <div className={embedded ? "py-16" : "flex min-h-screen items-center justify-center px-5"}>
      <div className="mx-auto max-w-md text-center">
        <div className="mx-auto mb-6 inline-flex rounded-3xl bg-critical-500/10 p-5 text-critical-400 ring-1 ring-critical-500/30">
          <ShieldX className="h-10 w-10" />
        </div>
        <h1 className="text-3xl font-bold">Access denied</h1>
        <p className="mt-2 text-mist-400">
          {role ? `Your role (${ROLE_LABEL[role]}) doesn't include` : "You need to sign in with a role that has"}{" "}
          {permission ? <span className="font-mono text-brand-300">{permission}</span> : "this permission"}. Every request is checked on the server
          too, so hiding a button is never the only protection.
        </p>
        <Link to={embedded ? "/app/dashboard" : "/login"} className="mt-6 inline-block rounded-xl border border-white/12 px-5 py-2.5 text-sm hover:border-brand-400/50">
          {embedded ? "Back to dashboard" : "Sign in"}
        </Link>
      </div>
    </div>
  );
}
