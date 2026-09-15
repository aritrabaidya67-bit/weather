/**
 * Live trend panel.
 * One beautiful chart replacing multiple dense grids.
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
  { label: "15m", hours: 0.25, bucket: "15m" },
  { label: "1h", hours: 1, bucket: "1h" },
  { label: "6h", hours: 6, bucket: "6h" },
  { label: "24h", hours: 24, bucket: "24h" },
  { label: "7d", hours: 168, bucket: "7d" },
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
    <section className="panel flex h-full flex-col p-6 overflow-hidden relative">
      <div className="glass-overlay" />
      
      <div className="relative z-10 flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <SectionHeaderPill
          icon={<ActiveIcon size={16} strokeWidth={2.5} />}
          title="Live Trend"
          meta={
            series?.latest !== null && series?.latest !== undefined
              ? `${series.latest.toFixed(active.decimals)}${unitSymbol(series.unit)} now`
              : undefined
          }
        />

        <div className="flex items-center justify-end gap-3 flex-wrap">
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
      </div>

      <div className="relative z-10 mt-2 flex-1 min-h-[280px]">
        {error ? (
          <div className="grid h-full place-items-center rounded-xl border border-dashed border-rose-400/30 bg-rose-500/5 text-sm font-medium text-rose-500">
            {error}
          </div>
        ) : loading && !series ? (
          <Skeleton className="h-full w-full opacity-60" />
        ) : series ? (
          <motion.div
            key={`${metric}-${rangeLabel}`}
            initial={{ opacity: 0, filter: "blur(4px)" }}
            animate={{ opacity: 1, filter: "blur(0px)" }}
            transition={{ duration: 0.4, ease: "easeOut" }}
            className="h-full w-full"
          >
            <TimeSeriesChart
              series={series}
              color={active.color}
              rangeHours={rangeHours}
              band={{ low: active.band?.low ?? null, high: active.band?.high ?? null, label: undefined }}
              decimals={active.decimals}
              height={280}
            />
          </motion.div>
        ) : (
          <div className="grid h-full place-items-center rounded-xl border border-dashed border-slate-200/50 bg-slate-50/50 text-sm font-medium text-slate-400 dark:border-white/5 dark:bg-surface-800/30">
            Waiting for sufficient readings...
          </div>
        )}
      </div>
    </section>
  );
}

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
    <div className="inline-flex items-center gap-1 rounded-full border border-slate-200/60 bg-slate-100/50 p-1 backdrop-blur-md dark:border-white/10 dark:bg-surface-900/40 shadow-inner">
      {options.map((option) => {
        const isActive = option.key === value;
        const Icon = option.icon ? channelIcon(option.icon) : null;
        return (
          <button
            key={option.key}
            type="button"
            onClick={() => onChange(option.key)}
            className={classNames(
              "relative inline-flex items-center justify-center gap-1.5 rounded-full font-medium transition-colors outline-none",
              compact ? "px-3 py-1.5 text-xs" : "px-3.5 py-1.5 text-sm",
              isActive
                ? "text-slate-900 dark:text-white"
                : "text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
            )}
            aria-pressed={isActive}
          >
            {isActive && (
              <motion.span
                layoutId={compact ? "segment-range" : "segment-metric"}
                className="absolute inset-0 rounded-full bg-white shadow-sm dark:bg-surface-800 dark:border dark:border-white/5"
                transition={{ type: "spring", stiffness: 500, damping: 40 }}
              />
            )}
            <span className="relative z-10 flex items-center gap-1.5 whitespace-nowrap">
              {Icon && !compact && (
                <Icon size={14} strokeWidth={isActive ? 2.5 : 2} style={{ color: isActive ? option.color : undefined }} aria-hidden />
              )}
              <span>{option.label}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}
