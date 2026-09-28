import { motion } from "framer-motion";
import { Link } from "react-router-dom";

/** 404 with a missing-tooth gag: tooth "404" is absent from the chart. */
export default function NotFoundPage({ embedded = false }: { embedded?: boolean }) {
  return (
    <div className={embedded ? "py-16" : "flex min-h-screen items-center justify-center px-5"}>
      <div className="text-center">
        <div className="mx-auto mb-8 flex items-end justify-center gap-2">
          {["4", "0", "4"].map((d, i) => (
            <motion.div
              key={i}
              initial={{ y: -20, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              transition={{ delay: i * 0.12, type: "spring" }}
              className={`flex h-24 w-16 items-center justify-center rounded-b-[40%] rounded-t-2xl border-2 font-display text-4xl font-bold ${i === 1 ? "border-dashed border-review-400/60 text-review-400" : "border-mist-100/80 bg-mist-100/90 text-ink-950"}`}
            >
              {d}
            </motion.div>
          ))}
        </div>
        <h1 className="text-3xl font-bold">This tooth is missing</h1>
        <p className="mt-2 text-mist-400">The page you're looking for was extracted, or never erupted.</p>
        <Link to={embedded ? "/app/dashboard" : "/"} className="mt-6 inline-block rounded-xl bg-gradient-to-r from-brand-400 to-teal-400 px-5 py-2.5 font-semibold text-ink-950">
          Back to safety
        </Link>
      </div>
    </div>
  );
}
