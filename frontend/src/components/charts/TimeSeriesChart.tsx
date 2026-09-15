/** Time-series chart with tooltips, units, reference bands and empty states. */

import { useMemo } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { MetricSeries, SeriesPoint } from "../../types";
import { axisTime, unitSymbol } from "../../utils/format";
import { EmptyState } from "../common/Ui";

export interface TimeSeriesChartProps {
  series: MetricSeries | { points: SeriesPoint[]; unit: string; label: string };
  color?: string;
  rangeHours?: number;
  height?: number;
  band?: { low: number | null; high: number | null; color?: string; label?: string };
  decimals?: number;
  comparePoints?: SeriesPoint[];
  compareLabel?: string;
}

interface ChartRow {
  timestamp: number;
  value: number | null;
  compare?: number | null;
}

export function TimeSeriesChart({
  series,
  color = "#38bdf8",
  rangeHours = 6,
  height = 260,
  band,
  decimals = 1,
  comparePoints,
  compareLabel,
}: TimeSeriesChartProps) {
  const rows = useMemo<ChartRow[]>(() => {
    const compareMap = new Map<number, number>();
    (comparePoints ?? []).forEach((point) => {
      if (point.value !== null) compareMap.set(new Date(point.timestamp).getTime(), point.value);
    });
    return series.points
      .map((point) => {
        const timestamp = new Date(point.timestamp).getTime();
        return {
          timestamp,
          value: point.value,
          compare: compareMap.get(timestamp) ?? null,
        };
      })
      .filter((row) => !Number.isNaN(row.timestamp));
  }, [series.points, comparePoints]);

  const stats = "mean" in series ? series : null;
  const gradientId = `grad-${series.label.replace(/\s+/g, "")}-${color.replace("#", "")}`;

  if (rows.length < 2) {
    return (
      <EmptyState
        title="Not enough data for a chart"
        message={`Waiting for at least two readings in this range to draw ${series.label.toLowerCase()}. The dashboard will fill in automatically.`}
      />
    );
  }

  const unit = unitSymbol(series.unit);

  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.35} />
              <stop offset="100%" stopColor={color} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.18)" vertical={false} />
          <XAxis
            dataKey="timestamp"
            type="number"
            domain={["dataMin", "dataMax"]}
            tickFormatter={(value: number) => axisTime(value, rangeHours)}
            tick={{ fontSize: 11, fill: "rgb(148 163 184)" }}
            axisLine={false}
            tickLine={false}
            minTickGap={28}
          />
          <YAxis
            domain={["auto", "auto"]}
            tick={{ fontSize: 11, fill: "rgb(148 163 184)" }}
            axisLine={false}
            tickLine={false}
            width={54}
            tickFormatter={(value: number) => value.toFixed(Math.abs(value) >= 100 ? 0 : decimals)}
          />
          {band && band.low !== null && band.high !== null ? (
            <ReferenceArea
              y1={band.low}
              y2={band.high}
              fill={band.color ?? "#22c55e"}
              fillOpacity={0.08}
              strokeOpacity={0}
              label={{ value: band.label ?? "comfort band", position: "insideTopRight", fontSize: 10, fill: "rgb(148 163 184)" }}
            />
          ) : null}
          <Tooltip
            content={({ active, payload, label }) => {
              if (!active || !payload?.length) return null;
              const row = payload[0]?.payload as ChartRow;
              return (
                <div className="rounded-xl border border-slate-200 bg-white/95 px-3 py-2 text-xs shadow-lg dark:border-slate-700 dark:bg-slate-900/95">
                  <div className="mb-1 font-medium text-slate-500 dark:text-slate-400">
                    {new Date(Number(label)).toLocaleString()}
                  </div>
                  <div className="tabular font-semibold text-slate-900 dark:text-slate-100">
                    {series.label}: {row.value === null ? "no value" : row.value.toFixed(decimals)} {unit}
                  </div>
                  {row.compare !== null && row.compare !== undefined ? (
                    <div className="tabular mt-0.5 text-slate-500 dark:text-slate-400">
                      {compareLabel ?? "comparison"}: {row.compare.toFixed(decimals)} {unit}
                    </div>
                  ) : null}
                  {band && band.label ? (
                    <div className="mt-0.5 text-[11px] text-slate-400">{band.label} reference band shown</div>
                  ) : null}
                </div>
              );
            }}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={2}
            fill={`url(#${gradientId})`}
            connectNulls={false}
            dot={false}
            activeDot={{ r: 3, strokeWidth: 0 }}
            isAnimationActive={false}
          />
          {comparePoints?.length ? (
            <Line
              type="monotone"
              dataKey="compare"
              stroke="rgba(148,163,184,0.75)"
              strokeDasharray="4 3"
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={false}
            />
          ) : null}
        </AreaChart>
      </ResponsiveContainer>
      {stats ? (
        <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] text-slate-500 sm:grid-cols-4 dark:text-slate-400">
          <span className="tabular">
            min <span className="font-medium text-slate-700 dark:text-slate-200">{stats.minimum?.toFixed(decimals) ?? "—"}</span>
          </span>
          <span className="tabular">
            mean <span className="font-medium text-slate-700 dark:text-slate-200">{stats.mean?.toFixed(decimals) ?? "—"}</span>
          </span>
          <span className="tabular">
            max <span className="font-medium text-slate-700 dark:text-slate-200">{stats.maximum?.toFixed(decimals) ?? "—"}</span>
          </span>
          <span className="tabular">
            n <span className="font-medium text-slate-700 dark:text-slate-200">{stats.sample_count}</span>
            {stats.r_squared !== null ? (
              <span className="ml-2">R² {stats.r_squared.toFixed(2)}</span>
            ) : null}
          </span>
        </div>
      ) : null}
    </div>
  );
}
