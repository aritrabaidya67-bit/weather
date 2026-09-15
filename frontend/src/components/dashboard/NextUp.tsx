/**
 * Forecast teaser — "What happens next?"
 * 
 * Visually focused on the future state, using polished arrows, 
 * bold typography, and smooth transitions.
 */

import { motion } from "framer-motion";
import { Link } from "react-router-dom";
import { ArrowRight, TrendingUp } from "lucide-react";
import type { PredictionResponse } from "../../types";
import { humanizeMethod, riskColor, unitSymbol } from "../../utils/format";
import { AnimatedNumber } from "../common/AnimatedNumber";
import { SectionHeaderPill } from "./SectionHeaderPill";

const ROWS = [
  { key: "temperature_c", label: "Temperature" },
  { key: "humidity_pct", label: "Humidity" },
  { key: "air_quality_index", label: "Air Quality" },
] as const;

export function NextUp({ prediction }: { prediction: PredictionResponse | null }) {
  const risk = prediction?.risk ?? null;

  return (
    <section className="panel flex h-full flex-col p-6 overflow-hidden relative">
      <div className="glass-overlay" />
      
      <div className="relative z-10 mb-6">
        <SectionHeaderPill
          icon={<TrendingUp size={16} strokeWidth={2.5} />}
          title="Next Up"
          meta={prediction ? `in ${prediction.primary_horizon_minutes} minutes` : undefined}
        />
      </div>

      <div className="relative z-10 flex-1 flex flex-col justify-center">
        {!prediction ? (
          <div className="flex h-full items-center justify-center rounded-2xl border border-dashed border-slate-200/60 bg-slate-50/50 p-6 text-sm text-slate-400 dark:border-white/5 dark:bg-surface-800/30">
            loading forecast…
          </div>
        ) : !prediction.data_sufficient ? (
          <div className="flex h-full flex-col items-center justify-center rounded-2xl border border-dashed border-slate-200/60 bg-slate-50/50 p-6 text-center dark:border-white/5 dark:bg-surface-800/30">
            <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">Building Model</p>
            <p className="mt-1 max-w-[200px] text-xs text-slate-400 leading-relaxed">
              Collecting data. {prediction.samples_used} readings found so far.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            <ul className="space-y-4">
              {ROWS.map(({ key, label }, index) => {
                const metric = prediction.metrics[key];
                if (!metric || metric.current_value === null || metric.predicted_value === null) return null;
                return (
                  <motion.li 
                    key={key} 
                    className="flex items-center justify-between"
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.4, delay: index * 0.1 }}
                  >
                    <span className="text-sm font-medium tracking-wide text-slate-500 dark:text-slate-400">{label}</span>
                    <div className="flex items-center gap-3">
                      <span className="text-base tabular text-slate-400">{metric.current_value.toFixed(1)}</span>
                      <ArrowRight size={14} className="text-cyan-500" />
                      <div className="flex items-baseline gap-1">
                        <AnimatedNumber
                          value={metric.predicted_value}
                          decimals={1}
                          className="text-lg font-bold tracking-tight text-slate-900 dark:text-white"
                        />
                        <span className="text-[10px] text-slate-400 font-medium">{unitSymbol(metric.unit)}</span>
                      </div>
                    </div>
                  </motion.li>
                );
              })}
            </ul>

            {risk && risk.predicted_score !== null && (
              <motion.div 
                className="mt-6 flex items-center justify-between border-t border-slate-200/60 pt-5 dark:border-white/10"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.5, delay: 0.3 }}
              >
                <span className="text-sm font-medium tracking-wide text-slate-500 dark:text-slate-400">Risk Score</span>
                <div className="flex items-center gap-3">
                  <span className="text-base tabular text-slate-400">{Math.round(risk.current_score ?? 0)}</span>
                  <ArrowRight size={14} className="text-rose-400" />
                  <span
                    className="text-lg font-bold tracking-tight"
                    style={{ color: riskColor(risk.predicted_level ?? 1) }}
                  >
                    {Math.round(risk.predicted_score)} 
                    <span className="ml-1 text-[10px] uppercase tracking-widest opacity-80">
                      {risk.predicted_label ?? `L${risk.predicted_level ?? "?"}`}
                    </span>
                  </span>
                </div>
              </motion.div>
            )}
          </div>
        )}
      </div>

      <div className="relative z-10 mt-6 pt-4 flex items-center justify-between border-t border-slate-200/40 dark:border-white/5">
        <p className="text-[10px] text-slate-400">
          {prediction && prediction.data_sufficient && (
            <>
              {humanizeMethod(prediction.metrics.temperature_c?.method)} ·{" "}
              {Math.round((prediction.metrics.temperature_c?.confidence ?? 0) * 100)}% confidence
            </>
          )}
        </p>
        <Link
          to="/predictions"
          className="inline-flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-cyan-600 transition-colors hover:text-cyan-700 dark:text-cyan-400 dark:hover:text-cyan-300"
        >
          View Forecast <ArrowRight size={12} strokeWidth={2.5} />
        </Link>
      </div>
    </section>
  );
}
