/**
 * Forecast: A highly visual timeline-based prediction view.
 * Moving away from a dense dashboard into an explorative timeline.
 */

import { motion } from "framer-motion";
import { AlertCircle, CloudRain, Info, TrendingUp, ArrowRight, Activity, Thermometer, Droplets, Wind, ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";
import {
  Chip,
  EmptyState,
  SectionHeaderPill,
} from "../components/common/Ui";
import { api } from "../services/api";
import { usePlatform } from "../state/PlatformContext";
import type { PredictionResponse, RiskForecast } from "../types";
import { classNames, riskColor, unitSymbol } from "../utils/format";

const HORIZONS = [
  { label: "15m", value: "15,30,60", primary: 15 },
  { label: "30m", value: "15,30,60", primary: 30 },
  { label: "1h", value: "30,60,120", primary: 60 },
];

export default function PredictionsPage() {
  const { overview } = usePlatform();
  const [horizon, setHorizon] = useState(HORIZONS[1]);
  const [prediction, setPrediction] = useState<PredictionResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    void api.predictions(undefined, horizon.value)
      .then((res) => { if (!cancelled) setPrediction(res); })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, [horizon, overview?.latest?.received_at]);

  const riskForecast = prediction?.risk as RiskForecast | null | undefined;

  if (!overview?.has_data) {
    return (
      <div className="panel flex flex-col items-center justify-center p-12 text-center min-h-[60vh]">
        <div className="rounded-full bg-slate-100 p-4 dark:bg-surface-800 mb-6 text-slate-400">
          <TrendingUp size={32} />
        </div>
        <EmptyState title="Forecast requires data" message="Waiting for device telemetry to build statistical models." />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-float-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 panel p-5">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-2">
            <TrendingUp size={20} className="text-cyan-500" />
            Forecast Model
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Statistical projection of the near future.
          </p>
        </div>
        <div className="flex items-center gap-3 bg-slate-100/50 dark:bg-surface-900/50 p-1.5 rounded-full border border-slate-200/50 dark:border-white/5">
          {HORIZONS.map((item) => (
            <button
              key={item.label}
              onClick={() => setHorizon(item)}
              className={classNames(
                "rounded-full px-4 py-1.5 text-xs font-semibold transition-all",
                horizon.label === item.label
                  ? "bg-white text-slate-900 shadow-sm dark:bg-surface-800 dark:text-white dark:border dark:border-white/10"
                  : "text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
              )}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {!prediction ? (
        <div className="panel min-h-[400px] flex items-center justify-center">
          <div className="animate-pulse flex flex-col items-center gap-4 text-slate-400">
            <Activity size={32} />
            <p className="text-sm font-medium">Running models...</p>
          </div>
        </div>
      ) : !prediction.data_sufficient ? (
        <div className="panel min-h-[400px] flex flex-col items-center justify-center p-8 text-center">
          <AlertCircle size={48} className="text-amber-500 mb-6" />
          <h2 className="text-xl font-bold text-slate-800 dark:text-slate-200 mb-2">Building Confidence</h2>
          <p className="text-slate-500 max-w-md">
            The prediction engine requires more historical data to generate reliable forecasts. 
            Currently collected {prediction.samples_used} samples.
          </p>
        </div>
      ) : (
        <div className="grid gap-6 xl:grid-cols-3">
          
          {/* Main Visual Timeline Area */}
          <div className="xl:col-span-2 space-y-6">
            {/* Risk Forecast Hero */}
            {riskForecast && riskForecast.predicted_score !== null && (
              <section className="panel-hero p-8 sm:p-10 relative overflow-hidden">
                <motion.div 
                  className="absolute right-0 top-0 w-64 h-64 opacity-20 pointer-events-none mix-blend-screen rounded-full filter blur-[40px] translate-x-1/2 -translate-y-1/2"
                  style={{ backgroundColor: riskColor(riskForecast.predicted_level ?? 1) }}
                  animate={{ scale: [1, 1.2, 1] }}
                  transition={{ duration: 5, repeat: Infinity }}
                />
                
                <SectionHeaderPill icon={<ShieldAlert size={16} />} title="Risk Projection" className="mb-8" />
                
                <div className="flex flex-col sm:flex-row items-center justify-between gap-8 relative z-10">
                  {/* Current */}
                  <div className="text-center sm:text-left flex-1">
                    <p className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-2">Right Now</p>
                    <div className="flex items-baseline justify-center sm:justify-start gap-1">
                      <span className="text-5xl font-bold text-slate-800 dark:text-slate-200 tabular">
                        {Math.round(riskForecast.current_score ?? 0)}
                      </span>
                    </div>
                  </div>

                  {/* Transition Arrow */}
                  <div className="flex flex-col items-center px-4">
                    <span className="text-[10px] uppercase font-bold text-slate-400 mb-2">In {riskForecast.horizon_minutes}m</span>
                    <div className="w-16 sm:w-24 h-[2px] bg-gradient-to-r from-slate-200 to-slate-400 dark:from-white/10 dark:to-white/30 relative rounded-full">
                      <motion.div 
                        className="absolute right-0 top-1/2 -translate-y-1/2 w-4 h-4 bg-slate-400 dark:bg-white/40 rounded-full blur-[2px]"
                        animate={{ x: [-20, 0, -20] }}
                        transition={{ duration: 2, repeat: Infinity }}
                      />
                    </div>
                  </div>

                  {/* Predicted */}
                  <div className="text-center sm:text-right flex-1">
                    <p className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-2">Predicted</p>
                    <div className="flex items-baseline justify-center sm:justify-end gap-1">
                      <span className="text-5xl font-bold tabular" style={{ color: riskColor(riskForecast.predicted_level ?? 1) }}>
                        {Math.round(riskForecast.predicted_score)}
                      </span>
                    </div>
                  </div>
                </div>
              </section>
            )}

            {/* Metric Forecasts */}
            <div className="grid gap-4 sm:grid-cols-2">
              {['temperature_c', 'humidity_pct', 'air_quality_index'].map((key) => {
                const metric = prediction.metrics[key];
                if (!metric || metric.current_value === null || metric.predicted_value === null) return null;
                
                const Icon = key.includes('temp') ? Thermometer : key.includes('humid') ? Droplets : Wind;
                const delta = metric.predicted_value - metric.current_value;
                const color = delta > 0 ? "text-orange-500" : delta < 0 ? "text-sky-500" : "text-slate-500";
                
                return (
                  <div key={key} className="panel p-6 flex flex-col justify-between hover:border-slate-300 dark:hover:border-white/20 transition-colors">
                    <div className="flex justify-between items-start mb-6">
                      <div className="flex items-center gap-2">
                        <Icon size={18} className="text-slate-400" />
                        <span className="font-semibold text-slate-800 dark:text-slate-200">{metric.label}</span>
                      </div>
                      <Chip severity={metric.confidence_label === 'high' ? 'good' : 'warning'}>
                        {Math.round(metric.confidence * 100)}% Conf
                      </Chip>
                    </div>

                    <div className="flex items-center justify-between">
                      <div className="text-center">
                        <span className="block text-xs text-slate-400 mb-1">Now</span>
                        <span className="text-xl font-medium text-slate-600 dark:text-slate-300">{metric.current_value.toFixed(1)}</span>
                      </div>
                      
                      <div className="flex flex-col items-center justify-center px-4">
                        <ArrowRight size={20} className={classNames("opacity-60", color)} />
                        <span className={classNames("text-[10px] font-bold mt-1", color)}>
                          {delta > 0 ? '+' : ''}{delta.toFixed(1)}
                        </span>
                      </div>

                      <div className="text-center">
                        <span className="block text-xs text-slate-400 mb-1">Next</span>
                        <span className="text-2xl font-bold text-slate-900 dark:text-white tabular">{metric.predicted_value.toFixed(1)}</span>
                        <span className="text-[10px] ml-0.5 text-slate-500">{unitSymbol(metric.unit)}</span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Right Sidebar: Context & Rain */}
          <div className="space-y-6">
            
            {prediction.rain && (
              <section className="panel-hero p-6 text-center relative overflow-hidden bg-gradient-to-b from-sky-50 to-white dark:from-sky-900/20 dark:to-surface-900">
                <CloudRain size={32} className="mx-auto text-sky-500 mb-4" />
                <h3 className="text-sm font-bold uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-1">Rain Probability</h3>
                <div className="text-6xl font-bold tracking-tighter text-sky-600 dark:text-sky-400 my-4 tabular">
                  {Math.round(prediction.rain.probability * 100)}%
                </div>
                <p className="text-xs text-slate-500 max-w-[200px] mx-auto">
                  {prediction.rain.reasoning}
                </p>
              </section>
            )}

            <section className="panel p-6 bg-slate-50/50 dark:bg-surface-900/30 border-dashed">
              <SectionHeaderPill icon={<Info size={16} />} title="AI Summary" className="mb-4" />
              {prediction.summary.length ? (
                <ul className="space-y-3">
                  {prediction.summary.map((line, i) => (
                    <li key={i} className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed">
                      {line}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-slate-500">No summary generated.</p>
              )}
            </section>

          </div>

        </div>
      )}
    </div>
  );
}
