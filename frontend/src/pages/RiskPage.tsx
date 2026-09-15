/**
 * Risk analysis: visual breakdown of the score, contributors, and the model.
 * Highly visual and progressive.
 */

import { motion, AnimatePresence } from "framer-motion";
import { Gauge, ShieldAlert, Sliders, ChevronDown } from "lucide-react";
import { useEffect, useState } from "react";
import { RiskTrendChart } from "../components/charts/RiskGauge";
import { EmptyState, SectionHeaderPill } from "../components/common/Ui";
import { AnimatedNumber } from "../components/common/AnimatedNumber";
import { api } from "../services/api";
import { usePlatform } from "../state/PlatformContext";
import type { RiskModel, RiskContribution } from "../types";
import { riskColor } from "../utils/format";

export default function RiskPage() {
  const { overview } = usePlatform();
  const [model, setModel] = useState<RiskModel | null>(null);
  const [trend, setTrend] = useState<{ timestamp: string; score: number; level: number }[]>([]);
  const [showModel, setShowModel] = useState(false);

  useEffect(() => {
    void api.riskModel().then(setModel).catch(() => setModel(null));
    void api.riskAnalysis(undefined, 6).then((res) => setTrend(res.trend ?? [])).catch(() => undefined);
  }, [overview?.latest?.received_at]);

  if (!overview?.has_data) {
    return (
      <div className="panel flex flex-col items-center justify-center p-12 text-center min-h-[60vh]">
        <div className="rounded-full bg-slate-100 p-4 dark:bg-surface-800 mb-6 text-slate-400">
          <ShieldAlert size={32} />
        </div>
        <EmptyState
          title="No risk assessment yet"
          message="Risk is calculated from real readings. Once the Arduino node sends data, this page will explain exactly which factors drive the score."
        />
      </div>
    );
  }

  const risk = overview.risk;
  const color = riskColor(risk.level);

  return (
    <div className="space-y-6 animate-float-in">
      
      {/* Visual Hero */}
      <section className="panel-hero p-8 sm:p-12 text-center relative overflow-hidden flex flex-col items-center justify-center min-h-[400px]">
        {/* Animated Background Aura */}
        <motion.div 
          className="absolute inset-0 opacity-20 pointer-events-none mix-blend-screen"
          style={{ background: `radial-gradient(circle at center, ${color}, transparent 60%)` }}
          animate={{ scale: [1, 1.1, 1], opacity: [0.15, 0.25, 0.15] }}
          transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
        />

        <div className="relative z-10">
          <p className="text-sm font-bold tracking-widest uppercase mb-4 opacity-80" style={{ color }}>
            Current Risk Score
          </p>
          <div className="flex items-baseline justify-center gap-2 mb-2">
            <AnimatedNumber
              value={risk.score}
              decimals={0}
              className="text-8xl sm:text-[9rem] font-bold tracking-tighter text-slate-900 dark:text-white leading-none"
            />
            <span className="text-2xl font-medium text-slate-400">/ 100</span>
          </div>
          <p className="text-2xl font-medium tracking-tight text-slate-800 dark:text-slate-200 mt-2">
            {risk.label}
          </p>
          <p className="max-w-md mx-auto mt-4 text-sm text-slate-500 dark:text-slate-400 leading-relaxed">
            {risk.description}
          </p>
        </div>
      </section>

      {/* What is driving this? */}
      <section className="panel p-6 sm:p-8">
        <SectionHeaderPill icon={<Gauge size={16} />} title="What is driving this?" className="mb-8" />
        
        <div className="space-y-6 max-w-3xl mx-auto">
          {risk.contributions.length === 0 ? (
            <p className="text-center text-slate-500">All metrics are within completely normal baseline ranges.</p>
          ) : (
            risk.contributions.sort((a, b) => b.points - a.points).map(contribution => (
              <ContributionBar key={contribution.key} contribution={contribution} />
            ))
          )}
        </div>
      </section>

      {/* Historical Trend */}
      <section className="panel p-6">
        <SectionHeaderPill icon={<Gauge size={16} />} title="Risk Trend (Last 6 Hours)" className="mb-6" />
        <RiskTrendChart data={trend} rangeHours={6} height={240} />
      </section>

      {/* Progressive Disclosure: Technical Model */}
      <section className="panel overflow-hidden">
        <button 
          onClick={() => setShowModel(!showModel)}
          className="w-full flex items-center justify-between p-6 hover:bg-slate-50 dark:hover:bg-white/5 transition-colors"
        >
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-xl bg-slate-100 dark:bg-surface-800 text-slate-500">
              <Sliders size={20} />
            </div>
            <div className="text-left">
              <h3 className="text-base font-semibold text-slate-900 dark:text-white">Underlying Risk Model</h3>
              <p className="text-xs text-slate-500">View configuration weights, bands, and cross-sensor rules.</p>
            </div>
          </div>
          <motion.div animate={{ rotate: showModel ? 180 : 0 }}>
            <ChevronDown size={20} className="text-slate-400" />
          </motion.div>
        </button>

        <AnimatePresence>
          {showModel && model && (
            <motion.div 
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="border-t border-slate-200/50 dark:border-white/10 p-6 bg-slate-50/30 dark:bg-black/10"
            >
              <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-5 mb-8">
                {model.levels.map(level => (
                  <div key={level.level} className="rounded-2xl border border-slate-200/60 p-4 dark:border-white/10 bg-white/40 dark:bg-surface-900/40 shadow-sm">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="h-3 w-3 rounded-full shadow-sm" style={{ backgroundColor: level.color }} />
                      <span className="text-sm font-bold text-slate-800 dark:text-slate-200">Level {level.level}</span>
                    </div>
                    <p className="text-xs font-medium text-slate-600 dark:text-slate-300 mb-1">{level.label}</p>
                    <p className="text-[10px] text-slate-400">Score {level.min_score}–{level.max_score}</p>
                  </div>
                ))}
              </div>

              <div className="space-y-4">
                <h4 className="text-xs font-bold uppercase tracking-widest text-slate-400">Cross-Sensor Rules</h4>
                <div className="grid gap-3 sm:grid-cols-2">
                  {model.combination_rules.map(rule => (
                    <div key={rule.id} className="rounded-xl border border-slate-200/50 p-4 dark:border-white/5 bg-white/20 dark:bg-surface-900/20">
                      <div className="flex justify-between items-start mb-2">
                        <span className="font-semibold text-sm text-slate-700 dark:text-slate-200">{rule.label}</span>
                        <span className="text-xs font-bold text-rose-500 bg-rose-500/10 px-2 py-0.5 rounded-full">+{rule.points} pts</span>
                      </div>
                      <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">{rule.reason || "Configured on backend"}</p>
                    </div>
                  ))}
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </section>

    </div>
  );
}

function ContributionBar({ contribution }: { contribution: RiskContribution }) {
  if (contribution.points <= 0) return null;

  const pct = Math.min(100, Math.max(0, (contribution.points / contribution.max_points) * 100));
  
  return (
    <div className="group relative">
      <div className="flex items-end justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold tracking-wide text-slate-700 dark:text-slate-200">
            {contribution.label}
          </span>
          <span className="text-xs font-medium text-slate-500 bg-slate-100 dark:bg-surface-800 px-2 py-0.5 rounded-md">
            {contribution.reading?.toFixed(1) ?? "—"} {contribution.unit}
          </span>
        </div>
        <div className="text-right">
          <span className="text-sm font-bold text-slate-900 dark:text-white">+{contribution.points.toFixed(0)}</span>
          <span className="text-xs text-slate-400 ml-1">pts</span>
        </div>
      </div>
      
      {/* Background track */}
      <div className="h-4 w-full rounded-full bg-slate-100 dark:bg-surface-800 overflow-hidden relative shadow-inner">
        {/* Fill bar */}
        <motion.div 
          className="absolute top-0 left-0 h-full rounded-full bg-gradient-to-r from-orange-400 to-rose-500 shadow-sm"
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 1, ease: "easeOut" }}
        />
      </div>
      
      {contribution.reason && (
        <p className="mt-2 text-xs text-slate-500 dark:text-slate-400 pl-1">{contribution.reason}</p>
      )}
    </div>
  );
}
