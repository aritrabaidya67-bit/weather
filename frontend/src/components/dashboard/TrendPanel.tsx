/**
 * Live trend panel — one large chart, switched by metric, instead of several
 * charts competing for attention.
 */

import { motion } from "framer-motion";
import type { HistoryResponse } from "../../types";
import { classNames, unitSymbol } from "../../utils/format";
import { TimeSeriesChart } from "../charts/TimeSeriesChart";
import { Skeleton } from "../common/Ui";
import { channelIcon } from "./channelIcons";
import { SectionHeaderPill } from "./SectionHeaderPill";

export type TrendMetricKey =
  | "temperature_c"
  | "humidity_pct"
  | "air_quality_index"
  | "pressure_hpa"
  | "light_pct"
  | "rain_pct";

export const TREND_METRICS: {
  key: TrendMetricKey;
  label: string;
  icon: string;
  color: string;
  decimals: number;
  band?: { low: number; high: number };
}[] = [
  { key: "temperature_c", label: "Temperature", icon: "thermometer", color: "#f97316", decimals: 1, band: { low: 18, high: 26 } },
  { key: "humidity_pct", label: "Humidity", icon: "droplets", color: "#38bdf8", decimals: 0, band: { low: 30, high: 65 } },
  { key: "air_quality_index", label: "Air", icon: "wind", color: "#22c55e", decimals: 0 },
  { key: "pressure_hpa", label: "Pressure", icon: "gauge", color: "#a78bfa", decimals: 0 },
];

export const TREND_RANGES = [
  { label: "15 m", hours: 0.25, bucket: "15m" },
  { label: "1 h", hours: 1, bucket: "1h" },
  { label: "6 h", hours: 6, bucket: "6h" },
  { label: "24 h", hours: 24, bucket: "24h" },
  { label: "7 d", hours: 168, bucket: "7d" },
];

export function TrendPanel({
  history,
  metric,
  onMetricChange,
  rangeLabel,
  onRangeChange,
  ranges,
  loading,
  error,
}: {
  history: HistoryResponse | null;
  metric: TrendMetricKey;
  onMetricChange: (key: TrendMetricKey) => void;
  rangeLabel: string;
  onRangeChange: (label: string) => void;
  ranges: typeof TREND_RANGES;
  loading?: boolean;
  error?: string | null;
}) {
  const active = TREND_METRICS.find((item) => item.key === metric) ?? TREND_METRICS[0];
  const ActiveIcon = channelIcon(active.icon);
  const series = history?.series?.[metric];
  const rangeHours = ranges.find((item) => item.label === rangeLabel)?.hours ?? 6;

  return (
    <section className="panel flex h-full flex-col p-4">
      <SectionHeaderPill
        icon={<ActiveIcon size={14} />}
        title="Live trend"
        meta={
          series?.latest !== null && series?.latest !== undefined
            ? `${series.latest.toFixed(active.decimals)}${unitSymbol(series.unit)} now`
            : undefined
        }
      />

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
        <SegmentedToggle
          options={TREND_METRICS.map((item) => ({ key: item.key, label: item.label, icon: item.icon, color: item.color }))}
          value={metric}
          onChange={(key) => onMetricChange(key as TrendMetricKey)}
        />
        <SegmentedToggle
          options={ranges.map((item) => ({ key: item.label, label: item.label }))}
          value={rangeLabel}
          onChange={onRangeChange}
          compact
        />
      </div>

      <div className="mt-3 flex-1">
        {error ? (
          <div className="grid h-56 place-items-center rounded-xl border border-dashed border-rose-400/50 text-xs text-rose-500">
            {error}
          </div>
        ) : loading && !series ? (
          <Skeleton className="h-56 w-full" />
        ) : series ? (
          <motion.div
            key={`${metric}-${rangeLabel}`}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.28 }}
          >
            <TimeSeriesChart
              series={series}
              color={active.color}
              rangeHours={rangeHours}
              band={{ low: active.band?.low ?? null, high: active.band?.high ?? null, label: undefined }}
              decimals={active.decimals}
              height={264}
            />
          </motion.div>
        ) : (
          <div className="grid h-56 place-items-center rounded-xl border border-dashed border-slate-200 text-xs text-slate-400 dark:border-slate-800">
            no readings in this range yet
          </div>
        )}
      </div>

      {history && !history.sufficient_data ? (
        <p className="mt-2 text-[11px] text-slate-400">
          limited history in this range — trends sharpen as readings accumulate
        </p>
      ) : null}
    </section>
  );
}

/** Small segmented control: the only "button row" the dashboard needs. */
export function SegmentedToggle({
  options,
  value,
  onChange,
  compact = false,
}: {
  options: { key: string; label: string; icon?: string; color?: string }[];
  value: string;
  onChange: (key: string) => void;
  compact?: boolean;
}) {
  return (
    <div className="inline-flex items-center gap-0.5 rounded-full border border-slate-200/80 bg-slate-100/60 p-0.5 dark:border-slate-800 dark:bg-slate-900/60">
      {options.map((option) => {
        const isActive = option.key === value;
        const Icon = option.icon ? channelIcon(option.icon) : null;
        return (
          <button
            key={option.key}
            type="button"
            onClick={() => onChange(option.key)}
            className={classNames(
              "relative inline-flex items-center gap-1.5 rounded-full font-medium transition-colors",
              compact ? "px-2.5 py-1 text-[11px]" : "px-3 py-1.5 text-xs",
              isActive
                ? "text-slate-900 dark:text-white"
                : "text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-100",
            )}
            aria-pressed={isActive}
          >
            {isActive ? (
              <motion.span
                layoutId={compact ? "segment-range" : "segment-metric"}
                className="absolute inset-0 rounded-full bg-white shadow-sm dark:bg-slate-800"
                transition={{ type: "spring", stiffness: 420, damping: 34 }}
              />
            ) : null}
            <span className="relative flex items-center gap-1.5">
              {Icon ? <Icon size={12} style={{ color: isActive ? option.color : undefined }} aria-hidden /> : null}
              <span>{option.label}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}
