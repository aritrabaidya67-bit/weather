/** Forecasting: per-metric estimates with confidence, bounds, method and reasoning. */

import { AlertCircle, CloudRain, Info, Target, TrendingUp } from "lucide-react";
import { useEffect, useState } from "react";
import {
  Card,
  CardSkeleton,
  Chip,
  ConfidenceBar,
  DataBadge,
  Disclosure,
  EmptyState,
  InlineNote,
  SectionHeader,
} from "../components/common/Ui";
import { api } from "../services/api";
import { usePlatform } from "../state/PlatformContext";
import type { MetricPrediction, PredictionAccuracy, PredictionResponse, RiskForecast } from "../types";
import { classNames, confidenceLabel, humanizeMethod, trendGlyph, unitSymbol } from "../utils/format";

const HORIZONS = [
  { label: "15 min", value: "15,30,60", primary: 15 },
  { label: "30 min", value: "15,30,60", primary: 30 },
  { label: "60 min", value: "30,60,120", primary: 60 },
];

export default function PredictionsPage() {
  const { overview } = usePlatform();
  const [horizon, setHorizon] = useState(HORIZONS[1]);
  const [prediction, setPrediction] = useState<PredictionResponse | null>(null);
  const [accuracy, setAccuracy] = useState<PredictionAccuracy | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void api
      .predictions(undefined, horizon.value)
      .then((response) => {
        if (!cancelled) setPrediction(response);
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [horizon, overview?.latest?.received_at]);

  useEffect(() => {
    void api.predictionAccuracy().then(setAccuracy).catch(() => undefined);
  }, []);

  const riskForecast = prediction?.risk as RiskForecast | null | undefined;

  return (
    <div className="space-y-5">
      <SectionHeader
        title="Forecast"
        subtitle="Statistical estimates of the near future, each with its method, sample count and confidence."
        icon={<TrendingUp size={16} />}
        action={
          <div className="flex flex-wrap items-center gap-2">
            {prediction?.data_sufficient ? <DataBadge predicted /> : null}
            <div className="flex gap-1">
              {HORIZONS.map((item) => (
                <button
                  key={item.label}
                  type="button"
                  onClick={() => setHorizon(item)}
                  className={classNames(
                    "rounded-lg px-2.5 py-1 text-[11px] font-medium transition",
                    horizon.label === item.label
                      ? "bg-slate-900 text-white dark:bg-cyan-500/20 dark:text-cyan-200"
                      : "text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800",
                  )}
                >
                  next {item.label}
                </button>
              ))}
            </div>
          </div>
        }
      />

      {!prediction?.data_sufficient ? (
        <Card>
          <EmptyState
            icon={<AlertCircle size={20} />}
            title="Insufficient historical data for a reliable prediction"
            message={
              prediction?.notes[0] ??
              "A statistical forecast needs a minimum number of samples in the observation window. The platform deliberately does not guess: collect more readings and the forecast will appear."
            }
          />
          {prediction?.notes.length ? (
            <ul className="mt-3 space-y-1 text-center text-xs text-slate-500 dark:text-slate-400">
              {prediction.notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          ) : null}
        </Card>
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
            <Card>
              <SectionHeader
                title="Environmental risk outlook"
                subtitle={`Horizon: next ${riskForecast?.horizon_minutes ?? horizon.primary} minutes`}
                icon={<Target size={16} />}
                className="mb-3"
              />
              {riskForecast && riskForecast.predicted_score !== null ? (
                <div className="space-y-3">
                  <div className="flex flex-wrap items-end gap-6">
                    <div>
                      <div className="text-[11px] uppercase tracking-wide text-slate-400">now</div>
                      <div className="tabular text-2xl font-semibold text-slate-700 dark:text-slate-200">
                        {riskForecast.current_score?.toFixed(0)}
                        <span className="ml-1 text-xs font-normal text-slate-400">L{riskForecast.current_level}</span>
                      </div>
                    </div>
                    <div className="text-2xl text-slate-300">→</div>
                    <div>
                      <div className="text-[11px] uppercase tracking-wide text-slate-400">forecast</div>
                      <div className="tabular text-2xl font-semibold text-slate-900 dark:text-slate-50">
                        {riskForecast.predicted_score.toFixed(0)}
                        <span className="ml-1 text-xs font-normal text-slate-400">L{riskForecast.predicted_level}</span>
                      </div>
                    </div>
                    <Chip
                      severity={
                        riskForecast.direction === "rising" ? "warning" : riskForecast.direction === "falling" ? "good" : "info"
                      }
                    >
                      {trendGlyph(riskForecast.direction)} {riskForecast.direction} · {riskForecast.predicted_label}
                    </Chip>
                  </div>
                  <ConfidenceBar confidence={riskForecast.confidence} label="Risk forecast confidence" />
                  {riskForecast.drivers.length ? (
                    <div>
                      <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">Projected drivers</p>
                      <ul className="space-y-1">
                        {riskForecast.drivers.map((driver) => (
                          <li key={driver} className="text-xs text-slate-600 dark:text-slate-300">
                            • {driver}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </div>
              ) : (
                <CardSkeleton />
              )}
            </Card>

            <Card>
              <SectionHeader title="Rain outlook" subtitle="Heuristic probability model" icon={<CloudRain size={16} />} className="mb-3" />
              {prediction?.rain ? (
                <div className="space-y-3">
                  <div className="flex items-baseline gap-3">
                    <span className="tabular text-3xl font-semibold text-sky-600 dark:text-sky-400">
                      {Math.round(prediction.rain.probability * 100)}%
                    </span>
                    <span className="text-xs text-slate-500 dark:text-slate-400">
                      within {prediction.rain.horizon_minutes} min
                      {prediction.rain.currently_raining ? " · raining now" : ""}
                    </span>
                  </div>
                  <ConfidenceBar confidence={prediction.rain.confidence} label="Heuristic confidence" />
                  <Disclosure label="How this was estimated">
                    <p className="text-[11px] leading-relaxed text-slate-500 dark:text-slate-400">{prediction.rain.reasoning}</p>
                    {prediction.rain.inputs ? (
                      <ul className="mt-1.5 grid grid-cols-2 gap-1 text-[11px] text-slate-500 dark:text-slate-400">
                        {Object.entries(prediction.rain.inputs).map(([key, value]) => (
                          <li key={key}>
                            {key.replace(/_/g, " ")}: <span className="tabular">{Number(value).toFixed(2)}</span>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </Disclosure>
                </div>
              ) : (
                <InlineNote severity="watch">Rain probability needs at least five recent readings.</InlineNote>
              )}
            </Card>
          </div>

          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {Object.values(prediction?.metrics ?? {}).map((metric: MetricPrediction) => {
              const delta =
                metric.predicted_value !== null && metric.current_value !== null
                  ? metric.predicted_value - metric.current_value
                  : null;
              return (
              <Card key={metric.metric}>
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">{metric.label}</p>
                    <p className="text-[11px] text-slate-400">{humanizeMethod(metric.method)}</p>
                  </div>
                  <Chip severity={metric.confidence_label === "high" ? "good" : metric.confidence_label === "medium" ? "watch" : "warning"}>
                    {metric.confidence_label} confidence
                  </Chip>
                </div>

                {metric.predicted_value !== null ? (
                  <>
                    <div className="mt-3 flex items-baseline gap-2">
                      <span className="tabular text-lg text-slate-500 dark:text-slate-400">
                        {metric.current_value?.toFixed(1) ?? "—"}
                      </span>
                      <span className="text-slate-300">→</span>
                      <span className="tabular text-2xl font-semibold text-slate-900 dark:text-slate-50">
                        {metric.predicted_value.toFixed(1)}
                      </span>
                      <span className="text-xs text-slate-400">{unitSymbol(metric.unit)}</span>
                      {delta !== null && Math.abs(delta) >= 0.05 ? (
                        <span
                          className={classNames(
                            "tabular ml-auto text-xs font-medium",
                            delta > 0 ? "text-orange-600 dark:text-orange-300" : "text-sky-600 dark:text-sky-300",
                          )}
                        >
                          {delta > 0 ? "+" : ""}
                          {delta.toFixed(1)} {unitSymbol(metric.unit)}
                        </span>
                      ) : null}
                    </div>
                    <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                      expected range {metric.lower_bound?.toFixed(1)} – {metric.upper_bound?.toFixed(1)} {unitSymbol(metric.unit)}
                      {metric.expected_status && metric.current_status && metric.expected_status !== metric.current_status
                        ? ` · status ${metric.current_status} → ${metric.expected_status}`
                        : ""}
                    </p>
                    <ConfidenceBar confidence={metric.confidence} label={`confidence (${confidenceLabel(metric.confidence)})`} className="mt-3" />
                    {metric.warnings.length ? (
                      <ul className="mt-2 space-y-0.5">
                        {metric.warnings.map((warning) => (
                          <li key={warning} className="text-[11px] text-amber-600 dark:text-amber-400">
                            ⚠ {warning}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                    <Disclosure label="How this was estimated" className="mt-2">
                      <p className="text-[11px] leading-relaxed text-slate-500 dark:text-slate-400">{metric.reasoning}</p>
                      <p className="mt-1.5 text-[10px] text-slate-400">
                        features: {metric.features.join(" · ") || "—"} · {metric.samples_used} samples ·{" "}
                        {metric.r_squared !== null ? `R² ${metric.r_squared.toFixed(2)}` : "no R²"}
                      </p>
                    </Disclosure>
                  </>
                ) : (
                  <InlineNote severity="watch" className="mt-3">
                    {metric.reasoning || "No forecast available for this metric."}
                  </InlineNote>
                )}
              </Card>
              );
            })}
          </div>

          {prediction?.summary.length ? (
            <Card>
              <SectionHeader title="Plain-language summary" subtitle="Generated from the forecast above" className="mb-3" />
              <ul className="space-y-1.5">
                {prediction.summary.map((line) => (
                  <li key={line} className="text-sm text-slate-700 dark:text-slate-200">
                    • {line}
                  </li>
                ))}
              </ul>
            </Card>
          ) : null}

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <SectionHeader title="Model transparency" subtitle="How these numbers were produced" icon={<Info size={16} />} className="mb-3" />
              <ul className="space-y-2 text-xs text-slate-600 dark:text-slate-300">
                <li>
                  • Continuous metrics use a blend of an ordinary least-squares trend and Holt's linear exponential
                  smoothing, weighted by fit quality ({prediction?.samples_used} samples over{" "}
                  {prediction?.observation_window_minutes.toFixed(0)} minutes).
                </li>
                <li>• Illumination is modelled with a solar cycle, because a straight line cannot describe day and night.</li>
                <li>• Rain uses a logistic heuristic over humidity level, humidity trend, pressure change and current wetness.</li>
                <li>• Confidence combines fit quality, sample count and horizon decay, and is capped at {Math.round(0.92 * 100)}%.</li>
                <li>• {prediction?.disclaimer}</li>
              </ul>
            </Card>

            <Card>
              <SectionHeader
                title="Forecast accuracy"
                subtitle="Stored snapshots are scored against what actually happened"
                className="mb-3"
              />
              {accuracy && accuracy.evaluated_count > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[360px] text-left text-xs">
                    <thead>
                      <tr className="text-[10px] uppercase tracking-wide text-slate-400">
                        <th className="pb-1 font-medium">Metric</th>
                        <th className="pb-1 font-medium">Horizon</th>
                        <th className="pb-1 font-medium">Samples</th>
                        <th className="pb-1 font-medium">Mean abs. error</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200/70 dark:divide-slate-800/70">
                      {Object.entries(accuracy.horizons).flatMap(([metric, values]) =>
                        Object.entries(values)
                          .filter(([key]) => key.endsWith("_mae"))
                          .map(([key, value]) => {
                            const horizonKey = key.replace("m_mae", "m");
                            return (
                              <tr key={`${metric}-${key}`}>
                                <td className="py-1 pr-2 text-slate-600 dark:text-slate-300">{metric.replace(/_/g, " ")}</td>
                                <td className="py-1 pr-2 text-slate-500 dark:text-slate-400">{horizonKey.replace("horizon_", "")}</td>
                                <td className="tabular py-1 pr-2 text-slate-500 dark:text-slate-400">
                                  {String(values[`${horizonKey}_samples`] ?? "—")}
                                </td>
                                <td className="tabular py-1 text-slate-600 dark:text-slate-300">
                                  {value !== null && value !== undefined ? Number(value).toFixed(2) : "—"}
                                </td>
                              </tr>
                            );
                          }),
                      )}
                    </tbody>
                  </table>
                </div>
              ) : (
                <InlineNote severity="info">
                  {accuracy?.notes[accuracy.notes.length - 1] ??
                    "Forecast snapshots are stored and scored once their horizon elapses; this needs the platform to run over time."}
                </InlineNote>
              )}
            </Card>
          </div>
        </>
      )}

      {loading && !prediction ? <CardSkeleton /> : null}
    </div>
  );
}
