/**
 * Hero state visualization.
 * 
 * "The user should understand the state before reading the data."
 * Instead of a thin ring, this uses a layered animated aura that pulses 
 * according to the environment's state, accompanied by a clean, premium readout.
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
  if (word === "GOOD") return <CheckCircle2 size={16} strokeWidth={2.5} />;
  if (word === "ATTENTION") return <Waves size={16} strokeWidth={2.5} />;
  if (word === "ALERT") return <AlertTriangle size={16} strokeWidth={2.5} />;
  if (word === "CRITICAL") return <ShieldAlert size={16} strokeWidth={2.5} />;
  return <Waves size={16} />;
}

export function StatusOrb({
  level,
  score,
  levelLabel,
  word,
  stale = false,
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
  
  // High risk states breathe faster and more aggressively.
  const serious = (level ?? 1) >= 3;
  const pulseDuration = serious ? 2.5 : 4.5;
  const scaleTarget = serious ? 1.08 : 1.04;

  return (
    <div className={classNames("relative flex flex-col items-center justify-center p-8", className)}>
      
      {/* Layered Animated Aura Background */}
      <div className="absolute inset-0 grid place-items-center pointer-events-none">
        
        {/* Deep ambient glow */}
        <motion.div 
          className="absolute rounded-full aura"
          style={{ width: "120%", height: "120%", background: `radial-gradient(circle at center, ${color}33 0%, transparent 70%)` }}
          animate={reduceMotion ? {} : { scale: [1, scaleTarget, 1], opacity: [0.6, 0.8, 0.6] }}
          transition={{ duration: pulseDuration, repeat: Infinity, ease: "easeInOut" }}
        />
        
        {/* Sharp inner core ring */}
        <motion.div
          className="absolute rounded-full border border-white/20 dark:border-white/5"
          style={{ width: "65%", height: "65%", boxShadow: `0 0 30px ${color}44, inset 0 0 20px ${color}22` }}
          animate={reduceMotion ? {} : { scale: [1, scaleTarget - 0.02, 1] }}
          transition={{ duration: pulseDuration, repeat: Infinity, ease: "easeInOut", delay: 0.2 }}
        />
        
        {/* Core solid ambient backdrop for text contrast */}
        <div 
          className="absolute rounded-full backdrop-blur-3xl"
          style={{ width: "55%", height: "55%", background: `radial-gradient(circle at center, ${color}11 0%, transparent 100%)` }}
        />
      </div>

      <motion.div 
        className="relative z-10 flex flex-col items-center text-center"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
      >
        {/* Status Badge */}
        <div 
          className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-bold tracking-widest uppercase mb-4 shadow-sm backdrop-blur-md"
          style={{ 
            backgroundColor: `${color}1A`, 
            color,
            border: `1px solid ${color}33`,
            textShadow: `0 0 8px ${color}88`
          }}
        >
          {statusIcon(word)}
          <span>{word}</span>
        </div>

        {/* Primary Score */}
        <div className="flex items-start gap-1">
          <AnimatedNumber
            value={score}
            decimals={0}
            className="text-7xl sm:text-8xl font-medium tracking-tighter text-slate-900 dark:text-white"
          />
        </div>

        {/* Context */}
        <p className="mt-2 text-sm font-medium tracking-wide text-slate-500 dark:text-slate-400">
          {levelLabel ?? "Risk Score"} {level ? `· Level ${level}` : ""}
        </p>

        {stale && (
          <span className="mt-4 inline-flex animate-pulse items-center rounded-full bg-amber-500/10 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-amber-600 dark:text-amber-400">
            Stale Data
          </span>
        )}
      </motion.div>
    </div>
  );
}

