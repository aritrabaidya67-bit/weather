/**
 * Hero status orb — the one element a user should register first.
 *
 * Status is encoded four ways so it never depends on colour alone: the word
 * (GOOD / ATTENTION / ALERT / CRITICAL), an icon, the ring's fill, and motion
 * (calm breathing when healthy, a firmer pulse when the situation is serious).
 */

import { motion, useReducedMotion } from "framer-motion";
import { AlertTriangle, CheckCircle2, ShieldAlert, Waves } from "lucide-react";
import type { ReactNode } from "react";
import { AnimatedNumber } from "../common/AnimatedNumber";
import { classNames, riskColor } from "../../utils/format";

export type StatusWord = "GOOD" | "ATTENTION" | "ALERT" | "CRITICAL" | "NO DATA";

export function statusWordFor(level: number | null | undefined): StatusWord {
  if (!level) return "NO DATA";
  if (level <= 2) return "GOOD";
  if (level === 3) return "ATTENTION";
  if (level === 4) return "ALERT";
  return "CRITICAL";
}

export function statusIcon(word: StatusWord): ReactNode {
  if (word === "GOOD") return <CheckCircle2 size={18} />;
  if (word === "ATTENTION") return <Waves size={18} />;
  if (word === "ALERT") return <AlertTriangle size={18} />;
  if (word === "CRITICAL") return <ShieldAlert size={18} />;
  return <Waves size={18} />;
}

export function StatusOrb({
  level,
  score,
  levelLabel,
  word,
  confidence,
  stale = false,
  size = 208,
  className,
}: {
  level: number | null;
  score: number | null;
  levelLabel?: string | null;
  word: StatusWord;
  confidence?: number | null;
  stale?: boolean;
  size?: number;
  className?: string;
}) {
  const reduceMotion = useReducedMotion();
  const color = level ? riskColor(level) : "#94a3b8";
  const radius = 82;
  const circumference = 2 * Math.PI * radius;
  const progress = Math.max(0, Math.min(100, score ?? 0));
  const serious = (level ?? 1) >= 4;

  return (
    <div
      className={classNames("relative grid place-items-center", className)}
      style={{ width: size, height: size }}
      role="img"
      aria-label={`Environmental status ${word}${score !== null ? `, risk score ${Math.round(score)} out of 100` : ""}`}
    >
      {/* tinted aura: gives the status depth without becoming a neon poster */}
      <span
        className="aura pointer-events-none absolute inset-2 rounded-full"
        style={{ background: `radial-gradient(circle at 50% 50%, ${color}55, transparent 68%)` }}
        aria-hidden
      />

      {/* slow rotating ring: a quiet sign that the system is live */}
      {reduceMotion ? null : (
        <span
          className="pointer-events-none absolute inset-0 animate-[drift_26s_linear_infinite] rounded-full"
          style={{
            background: `conic-gradient(from 0deg, transparent 0deg, ${color}22 90deg, transparent 200deg)`,
          }}
          aria-hidden
        />
      )}

      <svg viewBox="0 0 200 200" className="absolute inset-0 h-full w-full -rotate-90" aria-hidden>
        <circle cx="100" cy="100" r={radius} fill="none" strokeWidth="8" className="stroke-slate-200/70 dark:stroke-slate-800" />
        <motion.circle
          cx="100"
          cy="100"
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: circumference * (1 - progress / 100) }}
          transition={{ duration: 1.1, ease: [0.22, 1, 0.36, 1] }}
          style={{ filter: `drop-shadow(0 0 6px ${color}66)` }}
        />
      </svg>

      <motion.div
        className="relative flex flex-col items-center justify-center"
        animate={reduceMotion || !serious ? undefined : { scale: [1, 1.03, 1] }}
        transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
      >
        <span
          className="inline-flex items-center gap-1.5 text-[11px] font-semibold tracking-[0.18em]"
          style={{ color }}
        >
          {statusIcon(word)}
          {word}
        </span>

        <div className="mt-1 flex items-baseline gap-1">
          <AnimatedNumber
            value={score}
            decimals={0}
            className="text-5xl font-semibold leading-none text-slate-900 dark:text-white"
          />
          <span className="text-sm text-slate-400">/100</span>
        </div>

        <span className="mt-1 text-xs font-medium text-slate-500 dark:text-slate-400">
          {levelLabel ?? "Risk"}
          {level ? ` · L${level}` : ""}
        </span>

        {typeof confidence === "number" ? (
          <span className="mt-1 text-[10px] uppercase tracking-wider text-slate-400">
            {Math.round(confidence * 100)}% confidence
          </span>
        ) : null}

        {stale ? (
          <span className="mt-2 rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-amber-600 dark:text-amber-300">
            stale reading
          </span>
        ) : null}
      </motion.div>
    </div>
  );
}
