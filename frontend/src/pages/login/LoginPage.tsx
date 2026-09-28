import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, ArrowLeft, KeyRound, Lock, Mail, ShieldCheck, Smartphone } from "lucide-react";
import { lazy, useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api, ApiError } from "@/api/client";
import type { User } from "@/api/types";
import { Logo } from "@/components/layout/Logo";
import { Button, Field, Input } from "@/components/ui/primitives";
import { useAuth } from "@/store/auth";
import { SceneGate } from "@/three/SceneGate";

const HeroScene = lazy(() => import("@/three/HeroScene"));

interface LoginResponse {
  access_token?: string;
  user?: User;
  mfa_required?: boolean;
  mfa_token?: string;
}

function OtpInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const refs = useRef<(HTMLInputElement | null)[]>([]);
  useEffect(() => refs.current[0]?.focus(), []);
  return (
    <div className="flex justify-between gap-2" role="group" aria-label="6-digit code">
      {Array.from({ length: 6 }).map((_, i) => (
        <input
          key={i}
          ref={(el) => (refs.current[i] = el)}
          inputMode="numeric"
          maxLength={1}
          aria-label={`Digit ${i + 1}`}
          value={value[i] ?? ""}
          onChange={(e) => {
            const d = e.target.value.replace(/\D/g, "").slice(-1);
            const next = (value.slice(0, i) + d + value.slice(i + 1)).slice(0, 6);
            onChange(next);
            if (d && i < 5) refs.current[i + 1]?.focus();
          }}
          onKeyDown={(e) => {
            if (e.key === "Backspace" && !value[i] && i > 0) refs.current[i - 1]?.focus();
          }}
          onPaste={(e) => {
            const digits = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6);
            if (digits) {
              e.preventDefault();
              onChange(digits);
              refs.current[Math.min(digits.length, 5)]?.focus();
            }
          }}
          className="h-14 w-12 rounded-xl border border-white/10 bg-ink-900/70 text-center font-mono text-2xl text-mist-100 focus:border-brand-400/60 focus:outline-none focus:ring-2 focus:ring-brand-400/30"
        />
      ))}
    </div>
  );
}

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/app/dashboard";
  const { setSession, setUser } = useAuth();
  const [step, setStep] = useState<"password" | "mfa">("password");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [mfaToken, setMfaToken] = useState("");
  const [error, setError] = useState<{ message: string; locked?: boolean } | null>(null);
  const [busy, setBusy] = useState(false);

  const finish = async (token: string) => {
    setSession(token);
    const { data } = await api<User>("/api/auth/me");
    setUser(data);
    navigate(from, { replace: true });
  };

  const submitPassword = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { data } = await api<LoginResponse>("/api/auth/login", { body: { email, password }, auth: false });
      if (data.mfa_required && data.mfa_token) {
        setMfaToken(data.mfa_token);
        setStep("mfa");
      } else if (data.access_token) {
        await finish(data.access_token);
      }
    } catch (err) {
      const e2 = err as ApiError;
      setError({ message: e2.status === 422 ? "Enter a valid email and password." : e2.message, locked: e2.status === 423 });
    } finally {
      setBusy(false);
    }
  };

  const submitCode = async (e?: FormEvent) => {
    e?.preventDefault();
    if (code.length !== 6) return;
    setBusy(true);
    setError(null);
    try {
      const { data } = await api<LoginResponse>("/api/auth/mfa", { body: { mfa_token: mfaToken, code }, auth: false });
      if (data.access_token) await finish(data.access_token);
    } catch (err) {
      setError({ message: (err as ApiError).message });
      setCode("");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (step === "mfa" && code.length === 6) void submitCode();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code, step]);

  return (
    <div className="relative grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
      <div className="relative hidden overflow-hidden border-r border-white/[0.05] lg:block">
        <div className="absolute inset-0 opacity-70">
          <SceneGate fallback={<div className="h-full w-full bg-gradient-to-br from-brand-400/10 to-teal-400/5" />}>
            <HeroScene interactive={false} />
          </SceneGate>
        </div>
        <div className="absolute inset-0 bg-gradient-to-t from-ink-950 via-ink-950/40 to-transparent" />
        <div className="absolute bottom-0 p-12">
          <p className="label text-brand-300">Secure clinical workspace</p>
          <h2 className="mt-3 max-w-md text-4xl font-bold">Every request re-verified. Every finding explained.</h2>
          <ul className="mt-6 space-y-2 text-sm text-mist-300">
            <li className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-teal-400" /> Zero Trust session checks on every call</li>
            <li className="flex items-center gap-2"><Smartphone className="h-4 w-4 text-teal-400" /> Authenticator-app second factor</li>
            <li className="flex items-center gap-2"><Lock className="h-4 w-4 text-teal-400" /> Five failed attempts lock the account for 15 minutes</li>
          </ul>
        </div>
      </div>

      <div className="flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-md">
          <div className="mb-10 flex items-center justify-between">
            <Logo />
            <Link to="/" className="flex items-center gap-1 text-xs text-mist-400 hover:text-mist-100">
              <ArrowLeft className="h-3.5 w-3.5" /> Home
            </Link>
          </div>
          <AnimatePresence mode="wait">
            {step === "password" ? (
              <motion.form key="pw" onSubmit={submitPassword} initial={{ opacity: 0, x: -16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 16 }} className="space-y-5">
                <div>
                  <h1 className="text-3xl font-bold">Welcome back</h1>
                  <p className="mt-1 text-sm text-mist-400">Sign in to your PerioVision clinic account.</p>
                </div>
                <Field label="Email" htmlFor="email">
                  <div className="relative">
                    <Mail className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-mist-500" />
                    <Input id="email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} className="pl-10" placeholder="you@clinic.org" />
                  </div>
                </Field>
                <Field label="Password" htmlFor="password">
                  <div className="relative">
                    <KeyRound className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-mist-500" />
                    <Input id="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} className="pl-10" />
                  </div>
                </Field>
                {error && (
                  <div role="alert" className={`flex gap-2 rounded-xl border p-3 text-sm ${error.locked ? "border-review-500/40 bg-review-500/10 text-review-400" : "border-critical-500/30 bg-critical-500/10 text-critical-400"}`}>
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /> {error.message}
                  </div>
                )}
                <Button type="submit" size="lg" className="w-full" loading={busy}>
                  Continue
                </Button>
                <p className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3 text-xs text-mist-500">
                  Demo mode: sign in with a <span className="font-mono text-mist-300">DEMO_*_EMAIL</span> account from your
                  <span className="font-mono text-mist-300"> .env</span> (dentist, technician, auditor or admin). Demo accounts are for presentations only.
                </p>
              </motion.form>
            ) : (
              <motion.form key="mfa" onSubmit={submitCode} initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -16 }} className="space-y-6">
                <div>
                  <div className="mb-4 inline-flex rounded-2xl bg-brand-400/10 p-3 text-brand-300 ring-1 ring-brand-400/20">
                    <Smartphone className="h-6 w-6" />
                  </div>
                  <h1 className="text-3xl font-bold">Two-step verification</h1>
                  <p className="mt-1 text-sm text-mist-400">Enter the 6-digit code from your authenticator app. Each code works once.</p>
                </div>
                <OtpInput value={code} onChange={setCode} />
                {error && (
                  <div role="alert" className="flex gap-2 rounded-xl border border-critical-500/30 bg-critical-500/10 p-3 text-sm text-critical-400">
                    <AlertTriangle className="mt-0.5 h-4 w-4" /> {error.message}
                  </div>
                )}
                <Button type="submit" size="lg" className="w-full" loading={busy} disabled={code.length !== 6}>
                  Verify and sign in
                </Button>
                <button type="button" onClick={() => { setStep("password"); setCode(""); setError(null); }} className="w-full text-center text-xs text-mist-400 hover:text-mist-100">
                  Use a different account
                </button>
              </motion.form>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
