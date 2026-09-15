/**
 * Forecast teaser — three "now → next" pairs, nothing more.
 *
 * Forecasts are statistical estimates, so the horizon and confidence are part
 * of the visual language (horizon in the header, confidence per row) rather
 * than buried in prose. The full method/reasoning lives on the forecast page.
 */

import { Link } from "react-router-dom";
import { ArrowRight, TrendingUp } from "lucide-react";
import type { PredictionResponse } from "../../types";
import { classNames, humanizeMethod, riskColor, unitSymbol } from "../../utils/format";
import { AnimatedNumber } from "../common/AnimatedNumber";
import { SectionHeaderPill } from "./SectionHeaderPill";

const ROWS = [
  { key: "temperature_c", label: "Temperature" },
  { key: "humidity_pct", label: "Humidity" },
  { key: "air_quality_index", label: "Air quality" },
] as const;

export function NextUp({ prediction }: { prediction: PredictionResponse | null }) {
  const risk = prediction?.risk ?? null;

  return (
    <section className="panel flex h-full flex-col p-4">
      <SectionHeaderPill
        icon={<TrendingUp size={14} />}
        title="Next up"
        meta={prediction ? `${prediction.primary_horizon_minutes} min` : undefined}
      />

      {!prediction ? (
        <div className="mt-3 flex flex-1 items-center justify-center rounded-xl border border-dashed border-slate-200 p-4 text-center text-xs text-slate-400 dark:border-slate-800">
          loading forecast…
        </div>
      ) : !prediction.data_sufficient ? (
        <div className="mt-3 flex flex-1 flex-col justify-center rounded-xl border border-dashed border-slate-200 p-4 text-center dark:border-slate-800">
          <p className="text-xs font-medium text-slate-500 dark:text-slate-400">No forecast yet</p>
          <p className="mt-1 text-[11px] text-slate-400">
            {prediction.samples_used} of the samples a reliable projection needs.
          </p>
        </div>
      ) : (
        <>
          <ul className="mt-3 space-y-2.5">
            {ROWS.map(({ key, label }) => {
              const metric = prediction.metrics[key];
              if (!metric || metric.current_value === null || metric.predicted_value === null) return null;
              return (
                <li key={key} className="flex items-center justify-between gap-2">
                  <span className="text-xs text-slate-500 dark:text-slate-400">{label}</span>
                  <span className="flex items-center gap-1.5 text-sm">
                    <span className="tabular text-slate-400">{metric.current_value.toFixed(1)}</span>
                    <ArrowRight size={12} className="text-slate-300 dark:text-slate-600" aria-hidden />
                    <AnimatedNumber
                      value={metric.predicted_value}
                      decimals={1}
                      className="font-semibold text-slate-900 dark:text-white"
                    />
                    <span className="text-[11px] text-slate-400">{unitSymbol(metric.unit)}</span>
                  </span>
                </li>
              );
            })}
          </ul>

          {risk && risk.predicted_score !== null ? (
            <div className="mt-3 flex items-center justify-between gap-2 border-t border-slate-200/70 pt-3 dark:border-slate-800/70">
              <span className="text-xs text-slate-500 dark:text-slate-400">Risk</span>
              <span className="flex items-center gap-1.5 text-sm">
                <span className="tabular text-slate-400">{Math.round(risk.current_score ?? 0)}</span>
                <ArrowRight size={12} className="text-slate-300 dark:text-slate-600" aria-hidden />
                <span
                  className={classNames("tabular font-semibold")}
                  style={{ color: riskColor(risk.predicted_level ?? 1) }}
                >
                  {Math.round(risk.predicted_score)} · {risk.predicted_label ?? `L${risk.predicted_level ?? "?"}`}
                </span>
              </span>
            </div>
          ) : null}

          <p className="mt-3 text-[11px] text-slate-400">
            {humanizeMethod(prediction.metrics.temperature_c?.method)} ·{" "}
            {Math.round((prediction.metrics.temperature_c?.confidence ?? 0) * 100)}% confidence
          </p>
        </>
      )}

      <Link
        to="/predictions"
        className="mt-auto inline-flex items-center gap-1 pt-3 text-[11px] font-medium text-cyan-600 hover:underline dark:text-cyan-300"
      >
        forecast detail <ArrowRight size={11} aria-hidden />
      </Link>
    </section>
  );
}
