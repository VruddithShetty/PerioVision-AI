import { motion, useScroll, useTransform } from "framer-motion";
import {
  ArrowRight,
  BadgeCheck,
  Brain,
  FileSignature,
  Fingerprint,
  KeyRound,
  Link2,
  Lock,
  Microscope,
  ScanLine,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { lazy, useRef } from "react";
import { Link } from "react-router-dom";
import { PanoramicScanner } from "@/components/dental/PanoramicScanner";
import { StagingExplorer } from "@/components/dental/StagingExplorer";
import { Logo } from "@/components/layout/Logo";
import { SceneGate, StaticToothArt } from "@/three/SceneGate";

const HeroScene = lazy(() => import("@/three/HeroScene"));

const STEPS = [
  {
    icon: ScanLine,
    k: "01",
    title: "Detect",
    text: "YOLOv8 finds every tooth and names it by FDI number, then locates the cemento-enamel junction, alveolar crest and root apex.",
    chip: "CLAHE · quality gate · FDI 11–48",
  },
  {
    icon: Brain,
    k: "02",
    title: "Explain",
    text: "Grad-CAM shows where the model looked. If attention drifts away from the periodontal band, the case is flagged instead of trusted.",
    chip: "Grad-CAM · ROI attention check",
  },
  {
    icon: Microscope,
    k: "03",
    title: "Verify",
    text: "Split-conformal prediction puts an honest interval on every measurement. Ambiguous stages go straight to a dentist for sign-off.",
    chip: "Conformal 90 % · mandatory review",
  },
  {
    icon: ShieldCheck,
    k: "04",
    title: "Secure",
    text: "Encrypted radiographs, signed models and reports, and a tamper-evident audit chain. Every request is re-checked (Zero Trust).",
    chip: "AES-256-GCM · RSA-PSS · Merkle",
  },
];

const CONTROLS = [
  { icon: Lock, title: "AES-256-GCM", text: "Radiographs, reports and identities encrypted with rotating keys." },
  { icon: FileSignature, title: "RSA-PSS signatures", text: "Unsigned or altered models are refused; reports carry a QR you can verify." },
  { icon: Link2, title: "Hash-chained audit", text: "Edit one log entry and verification points to it. Merkle roots are anchored off-database." },
  { icon: Fingerprint, title: "MFA + short-lived JWT", text: "TOTP second factor, 15-minute tokens bound to your device, replay detection." },
  { icon: KeyRound, title: "Four roles", text: "Dentist, technician, auditor, admin, each with an explicit permission matrix." },
  { icon: BadgeCheck, title: "Honest by design", text: "No invented metrics. Uncalibrated or demo results say so, loudly." },
];

function Section({ id, eyebrow, title, subtitle, children }: {
  id?: string;
  eyebrow: string;
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="mx-auto max-w-7xl px-5 py-24 md:px-8">
      <motion.div
        initial={{ opacity: 0, y: 24 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-80px" }}
        transition={{ duration: 0.6 }}
        className="mb-12 max-w-3xl"
      >
        <p className="label text-brand-300">{eyebrow}</p>
        <h2 className="mt-3 text-3xl font-bold md:text-5xl">{title}</h2>
        {subtitle && <p className="mt-4 text-lg text-mist-400">{subtitle}</p>}
      </motion.div>
      {children}
    </section>
  );
}

export default function LandingPage() {
  const heroRef = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: heroRef, offset: ["start start", "end start"] });
  const sceneY = useTransform(scrollYProgress, [0, 1], [0, 120]);
  const sceneOpacity = useTransform(scrollYProgress, [0, 0.8], [1, 0.2]);

  return (
    <div className="min-h-screen overflow-x-hidden">
      <header className="fixed inset-x-0 top-0 z-40 border-b border-white/[0.04] bg-ink-950/60 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-3 md:px-8">
          <Logo />
          <nav className="hidden items-center gap-7 text-sm text-mist-400 md:flex" aria-label="Sections">
            <a href="#scanner" className="hover:text-mist-100">Live scan</a>
            <a href="#workflow" className="hover:text-mist-100">How it works</a>
            <a href="#staging" className="hover:text-mist-100">Staging</a>
            <a href="#security" className="hover:text-mist-100">Security</a>
            <Link to="/verify" className="hover:text-mist-100">Verify a report</Link>
          </nav>
          <Link
            to="/login"
            className="rounded-xl bg-gradient-to-r from-brand-400 to-teal-400 px-4 py-2 text-sm font-semibold text-ink-950 shadow-glow transition hover:brightness-110"
          >
            Sign in
          </Link>
        </div>
      </header>

      {/* HERO */}
      <div ref={heroRef} className="relative isolate pt-20">
        <div className="absolute inset-0 -z-10 bg-grid bg-[size:56px_56px] [mask-image:radial-gradient(ellipse_at_center,black_30%,transparent_75%)]" />
        <div className="mx-auto grid min-h-[92vh] max-w-7xl items-center gap-10 px-5 md:grid-cols-2 md:px-8">
          <motion.div initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7 }}>
            <span className="inline-flex items-center gap-2 rounded-full border border-brand-400/25 bg-brand-400/10 px-3 py-1 text-xs text-brand-300">
              <Sparkles className="h-3.5 w-3.5" /> Explainable periodontal AI · clinician in the loop
            </span>
            <h1 className="mt-6 text-5xl font-extrabold leading-[1.02] md:text-6xl xl:text-7xl">
              See bone loss
              <br />
              <span className="bg-gradient-to-r from-brand-300 via-brand-400 to-teal-400 bg-clip-text text-transparent">
                before it's lost.
              </span>
            </h1>
            <p className="mt-6 max-w-xl text-lg text-mist-400">
              PerioVision reads dental radiographs tooth by tooth, measures alveolar bone loss from the CEJ to the crest,
              tracks it across visits, and hands every uncertain finding to a dentist, inside a system built like a bank vault.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link
                to="/login"
                className="group inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-brand-400 to-teal-400 px-6 py-3 font-semibold text-ink-950 shadow-glow transition hover:brightness-110"
              >
                Enter the clinic <ArrowRight className="h-4 w-4 transition group-hover:translate-x-1" />
              </Link>
              <a href="#scanner" className="inline-flex items-center gap-2 rounded-xl border border-white/12 px-6 py-3 text-mist-100 transition hover:border-brand-400/50">
                <ScanLine className="h-4 w-4 text-brand-400" /> Try the live scan
              </a>
            </div>
            <div className="mt-10 grid max-w-lg grid-cols-3 gap-3 text-xs">
              {[
                ["32", "FDI tooth classes"],
                ["4", "clinical roles"],
                ["7/7", "attacks defended in the lab"],
              ].map(([v, l]) => (
                <div key={l} className="glass px-3 py-3">
                  <p className="font-display text-2xl font-bold text-mist-100">{v}</p>
                  <p className="mt-0.5 text-mist-500">{l}</p>
                </div>
              ))}
            </div>
          </motion.div>

          <motion.div style={{ y: sceneY, opacity: sceneOpacity }} className="relative h-[460px] md:h-[620px]">
            <SceneGate fallback={<StaticToothArt className="h-full" />}>
              <HeroScene />
            </SceneGate>
            <motion.div
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.8 }}
              className="glass-strong absolute right-2 top-16 hidden px-4 py-3 text-xs md:block"
            >
              <p className="label">Tooth 36</p>
              <p className="mt-1 font-display text-lg font-semibold text-review-400">Stage II · 24%</p>
              <p className="text-mist-500">interval 19–29% · 90% coverage</p>
            </motion.div>
            <motion.div
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 1.1 }}
              className="glass-strong absolute bottom-20 left-0 hidden px-4 py-3 text-xs md:block"
            >
              <p className="label">Model integrity</p>
              <p className="mt-1 flex items-center gap-1.5 text-teal-400">
                <BadgeCheck className="h-4 w-4" /> RSA-PSS signature valid
              </p>
            </motion.div>
          </motion.div>
        </div>
      </div>

      <Section
        id="scanner"
        eyebrow="Interactive · drag across the X-ray"
        title="Watch the AI read a panoramic radiograph"
        subtitle="Drag the scan bar. Behind it: FDI tooth numbers, the cemento-enamel junction (cyan), the alveolar crest (amber), the measured bone loss, and where the model focused its attention."
      >
        <div className="glass-strong p-3 md:p-5">
          <PanoramicScanner />
        </div>
        <p className="mt-3 text-center text-xs text-mist-500">Illustration only. Real analyses run on uploaded radiographs inside the clinic app.</p>
      </Section>

      <Section id="workflow" eyebrow="The workflow" title="Detect → Explain → Verify → Secure">
        <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((s, i) => (
            <motion.div
              key={s.title}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ delay: i * 0.1, duration: 0.5 }}
              whileHover={{ y: -6 }}
              className="glass group relative overflow-hidden p-6"
            >
              <div className="absolute -right-6 -top-6 font-display text-8xl font-extrabold text-white/[0.03]">{s.k}</div>
              <div className="inline-flex rounded-xl bg-brand-400/10 p-3 text-brand-300 ring-1 ring-brand-400/20 transition group-hover:bg-brand-400/20">
                <s.icon className="h-6 w-6" />
              </div>
              <h3 className="mt-5 text-xl font-bold">{s.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-mist-400">{s.text}</p>
              <p className="mt-5 font-mono text-[11px] text-brand-300/80">{s.chip}</p>
            </motion.div>
          ))}
        </div>
      </Section>

      <Section
        id="staging"
        eyebrow="Periodontology, made visible"
        title="How much bone is left around the root?"
        subtitle="Radiographic bone loss is the distance from the CEJ down to the alveolar crest, as a share of root length. It drives the periodontitis stage."
      >
        <StagingExplorer />
      </Section>

      <Section
        id="security"
        eyebrow="Built for a cybersecurity thesis"
        title="Clinical data deserves a vault, not a folder"
      >
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {CONTROLS.map((c, i) => (
            <motion.div
              key={c.title}
              initial={{ opacity: 0, scale: 0.97 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.06 }}
              className="glass flex gap-4 p-5"
            >
              <div className="h-fit rounded-xl bg-teal-400/10 p-2.5 text-teal-400 ring-1 ring-teal-400/20">
                <c.icon className="h-5 w-5" />
              </div>
              <div>
                <p className="font-display font-semibold">{c.title}</p>
                <p className="mt-1 text-sm text-mist-400">{c.text}</p>
              </div>
            </motion.div>
          ))}
        </div>
        <div className="mt-10 flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-brand-400/20 bg-gradient-to-r from-brand-400/10 to-teal-400/5 p-6">
          <div>
            <p className="font-display text-xl font-semibold">Got a PerioVision report?</p>
            <p className="text-sm text-mist-400">Check its RSA-PSS signature. No login, no patient data revealed.</p>
          </div>
          <Link to="/verify" className="inline-flex items-center gap-2 rounded-xl bg-white/10 px-5 py-2.5 text-sm font-medium hover:bg-white/15">
            <BadgeCheck className="h-4 w-4 text-teal-400" /> Verify a report
          </Link>
        </div>
      </Section>

      <footer className="border-t border-white/[0.05] py-10">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-4 px-5 text-xs text-mist-500 md:flex-row md:px-8">
          <Logo />
          <p className="max-w-xl text-center md:text-right">
            Clinical decision support. Not a certified medical device. Security controls are aligned with
            HIPAA safeguards, not certified. Findings must be confirmed by a qualified dentist.{" "}
            <Link to="/about" className="text-brand-300 hover:underline">About the project</Link>
          </p>
        </div>
      </footer>
    </div>
  );
}
