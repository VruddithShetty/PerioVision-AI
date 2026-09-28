import clsx from "clsx";
import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  CalendarClock,
  FileCheck2,
  FlaskConical,
  Gauge,
  Info,
  LogOut,
  Menu,
  ScanLine,
  ShieldCheck,
  Stethoscope,
  UserCog,
  Users,
  X,
} from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api } from "@/api/client";
import { useReviewQueue } from "@/api/hooks";
import { Badge } from "@/components/ui/primitives";
import { ROLE_LABEL, useAuth, useCan } from "@/store/auth";
import { Logo } from "./Logo";

const NAV = [
  { to: "/app/dashboard", label: "Dashboard", icon: Gauge, perm: "self:manage" },
  { to: "/app/patients", label: "Patients", icon: Users, perm: "patient:read" },
  { to: "/app/analysis/new", label: "New analysis", icon: ScanLine, perm: "analysis:run" },
  { to: "/app/review", label: "Review queue", icon: Stethoscope, perm: "review:read", badge: true },
  { to: "/app/recall", label: "Recall board", icon: CalendarClock, perm: "care:read" },
  { to: "/app/reports", label: "Reports", icon: FileCheck2, perm: "report:read" },
  { to: "/app/model-trust", label: "Model trust", icon: Activity, perm: "model:read" },
  { to: "/app/security", label: "Security center", icon: ShieldCheck, perm: "self:manage" },
  { to: "/app/security-lab", label: "Security lab", icon: FlaskConical, perm: "security_lab:run" },
  { to: "/app/admin", label: "Admin", icon: UserCog, perm: "admin:users" },
  { to: "/app/about", label: "About", icon: Info, perm: "self:manage" },
];

function QueueCount() {
  const { data } = useReviewQueue();
  if (!data?.length) return null;
  return <Badge tone="review">{data.length}</Badge>;
}

function NavItems({ onNavigate }: { onNavigate?: () => void }) {
  const permissions = useAuth((s) => s.permissions);
  const canReview = useCan("review:read");
  return (
    <nav aria-label="Main" className="space-y-1">
      {NAV.filter((n) => permissions.includes(n.perm)).map(({ to, label, icon: Icon, badge }) => (
        <NavLink
          key={to}
          to={to}
          onClick={onNavigate}
          className={({ isActive }) =>
            clsx(
              "group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition",
              isActive
                ? "bg-gradient-to-r from-brand-400/15 to-transparent text-brand-300 shadow-[inset_2px_0_0_0_#22d3ee]"
                : "text-mist-400 hover:bg-white/[0.04] hover:text-mist-100",
            )
          }
        >
          <Icon className="h-[18px] w-[18px]" aria-hidden />
          <span className="flex-1">{label}</span>
          {badge && canReview && <QueueCount />}
        </NavLink>
      ))}
    </nav>
  );
}

export function DemoBanner() {
  const mode = useAuth((s) => s.mode);
  if (mode !== "demo") return null;
  return (
    <div role="status" className="border-b border-review-500/30 bg-review-500/10 px-4 py-2 text-center text-xs text-review-400">
      <strong className="font-semibold">DEMO MODE</strong> · synthetic data in an in-memory database · results are not
      clinical output · nothing is saved after restart
    </div>
  );
}

export function AppLayout() {
  const user = useAuth((s) => s.user);
  const clear = useAuth((s) => s.clear);
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);

  const logout = async () => {
    try {
      await api("/api/auth/logout", { method: "POST" });
    } catch {
      /* session may already be gone */
    }
    clear();
    navigate("/login");
  };

  const sidebar = (
    <div className="flex h-full flex-col">
      <div className="px-4 pb-6 pt-5">
        <Logo />
      </div>
      <div className="flex-1 overflow-y-auto px-3">
        <NavItems onNavigate={() => setMobileOpen(false)} />
      </div>
      <div className="m-3 rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
        <p className="truncate text-sm font-medium text-mist-100">{user?.name}</p>
        <p className="truncate text-xs text-mist-500">{user?.email}</p>
        <div className="mt-2 flex items-center justify-between">
          <Badge tone="brand">{user ? ROLE_LABEL[user.role] : ""}</Badge>
          <button onClick={logout} className="flex items-center gap-1 text-xs text-mist-400 hover:text-critical-400">
            <LogOut className="h-3.5 w-3.5" /> Sign out
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="flex min-h-screen flex-col">
      <DemoBanner />
      <div className="flex flex-1">
        <aside className="sticky top-0 hidden h-screen w-64 shrink-0 border-r border-white/[0.05] bg-ink-900/60 backdrop-blur-xl lg:block">
          {sidebar}
        </aside>
        <AnimatePresence>
          {mobileOpen && (
            <motion.div className="fixed inset-0 z-40 lg:hidden" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              <div className="absolute inset-0 bg-ink-950/70" onClick={() => setMobileOpen(false)} />
              <motion.aside
                className="absolute left-0 top-0 h-full w-72 border-r border-white/[0.06] bg-ink-900"
                initial={{ x: -300 }}
                animate={{ x: 0 }}
                exit={{ x: -300 }}
              >
                <button className="absolute right-3 top-4 p-1 text-mist-400" onClick={() => setMobileOpen(false)} aria-label="Close menu">
                  <X className="h-5 w-5" />
                </button>
                {sidebar}
              </motion.aside>
            </motion.div>
          )}
        </AnimatePresence>
        <main className="min-w-0 flex-1">
          <div className="flex items-center gap-3 border-b border-white/[0.05] px-4 py-3 lg:hidden">
            <button onClick={() => setMobileOpen(true)} className="rounded-lg p-1.5 text-mist-300 hover:bg-white/5" aria-label="Open menu">
              <Menu className="h-5 w-5" />
            </button>
            <Logo compact />
          </div>
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.18 }}
              className="mx-auto w-full max-w-7xl px-4 py-6 md:px-8 md:py-8"
            >
              <Outlet />
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
    </div>
  );
}
