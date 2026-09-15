/** Analytics: trends, period comparisons, correlations, summaries and observations. */

import { BarChart3, GitCompare, Layers, LineChart, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { TimeSeriesChart } from "../components/charts/TimeSeriesChart";
import { ObservationList } from "../components/dashboard/Panels";
import { Card, CardSkeleton, Chip, DataBadge, EmptyState, InlineNote, SectionHeader } from "../components/common/Ui";
import { api } from "../services/api";
import { usePlatform } from "../state/PlatformContext";
import type { HistoryResponse, Observation, SummaryResponse } from "../types";
import { classNames, formatSigned, unitSymbol } from "../utils/format";

const RANGES = [
  { label: "1 h", hours: 1, bucket: "1h" },
  { label: "6 h", hours: 6, bucket: "6h" },
  { label: "24 h", hours: 24, bucket: "24h" },
  { label: "7 d", hours: 168, bucket: "7d" },
];

interface TrendRow {
  label: string;
  unit: string;
  trend: string;
  change: number | null;
  change_pct: number | null;
  slope_per_minute: number | null;
  rate_of_change_per_hour: number | null;
  mean: number | null;
  min: number | null;
  max: number | null;
  latest: number | null;
  samples: number;
  r_squared: number | null;
}

export default function Analytics() {
  const { overview } = usePlatform();
  const [range, setRange] = useState(RANGES[1]);
  const [history, setHistory] = useState<HistoryResponse | null>(null);
  const [trends, setTrends] = useState<Record<string, TrendRow> | null>(null);
  const [compare, setCompare] = useState<Record<string, { label: string; unit: string; delta: number | null; current_mean: number | null; previous_mean: number | null; message: string; sufficient_comparison: boolean }> | null>(null);
  const [observations, setObservations] = useState<Observation[]>([]);
  const [summaryPeriod, setSummaryPeriod] = useState<"day" | "week">("day");
  const [summary, setSummary] = useState<SummaryResponse | null>(null);

  useEffect(() => {
    void api.history({ hours: range.hours, bucket: range.bucket, limit: 600 }).then(setHistory).catch(() => setHistory(null));
    void api
      .trends(undefined, range.hours)
      .then((response) => setTrends(response.metrics as unknown as Record<string, TrendRow>))
      .catch(() => setTrends(null));
    void api
      .compare(undefined, Math.max(0.5, range.hours))
      .then((response) => setCompare(response.metrics as unknown as typeof compare))
      .catch(() => setCompare(null));
    void api.observations(undefined, range.hours).then((response) => setObservations(response.observations as Observation[])).catch(() => setObservations([]));
  }, [range, overview?.latest?.received_at]);

  useEffect(() => {
    void api.summary(summaryPeriod).then(setSummary).catch(() => setSummary(null));
  }, [summaryPeriod, overview?.latest?.received_at]);


  if (!overview?.has_data) {
    return (
      <Card>
        <EmptyState
          icon={<LineChart size={20} />}
          title="No data to analyse"
          message="Analytics needs stored readings. It fills in automatically once the Arduino node starts reporting."
        />
      </Card>
    );
  }

  return (
    <div className="space-y-5">
      <SectionHeader
        title="Analytics"
        subtitle="Statistics, trends and comparisons computed from stored readings - never fabricated."
        icon={<BarChart3 size={16} />}
        action={
          <div className="flex flex-wrap items-center gap-2">
            <DataBadge source={overview.data_source} />
            <div className="flex gap-1">
              {RANGES.map((item) => (
                <button
                  key={item.label}
                  type="button"
                  onClick={() => setRange(item)}
                  className={classNames(
                    "rounded-lg px-2.5 py-1 text-[11px] font-medium transition",
                    range.label === item.label
                      ? "bg-slate-900 text-white dark:bg-cyan-500/20 dark:text-cyan-200"
                      : "text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800",
                  )}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
        }
      />

      <Card>
        <SectionHeader title="Trend table" subtitle="Slope, rate of change and fit quality per channel" icon={<LineChart size={16} />} className="mb-3" />
        {trends ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead>
                <tr className="text-[11px] uppercase tracking-wide text-slate-400">
                  <th className="pb-2 font-medium">Channel</th>
                  <th className="pb-2 font-medium">Latest</th>
                  <th className="pb-2 font-medium">Trend</th>
                  <th className="pb-2 font-medium">Change</th>
                  <th className="pb-2 font-medium">Per hour</th>
                  <th className="pb-2 font-medium">Mean</th>
                  <th className="pb-2 font-medium">Range</th>
                  <th className="pb-2 font-medium">R²</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200/70 dark:divide-slate-800/70">
                {Object.entries(trends).map(([key, row]) => (
                  <tr key={key}>
                    <td className="py-2 pr-3 font-medium text-slate-700 dark:text-slate-200">{row.label}</td>
                    <td className="tabular py-2 pr-3 text-slate-600 dark:text-slate-300">
                      {row.latest?.toFixed(1) ?? "—"} {unitSymbol(row.unit)}
                    </td>
                    <td className="py-2 pr-3">
                      <Chip severity={row.trend === "stable" ? "info" : row.trend === "rising" ? "watch" : "info"}>
                        {row.trend}
                      </Chip>
                    </td>
                    <td className="tabular py-2 pr-3 text-slate-600 dark:text-slate-300">
                      {formatSigned(row.change, 2, row.unit)}
                      {row.change_pct !== null ? (
                        <span className="ml-1 text-[11px] text-slate-400">({row.change_pct.toFixed(1)}%)</span>
                      ) : null}
                    </td>
                    <td className="tabular py-2 pr-3 text-slate-600 dark:text-slate-300">
                      {row.rate_of_change_per_hour !== null ? `${row.rate_of_change_per_hour.toFixed(2)} ${unitSymbol(row.unit)}/h` : "—"}
                    </td>
                    <td className="tabular py-2 pr-3 text-slate-600 dark:text-slate-300">{row.mean?.toFixed(1) ?? "—"}</td>
                    <td className="tabular py-2 pr-3 text-slate-500 dark:text-slate-400">
                      {row.min?.toFixed(1) ?? "—"} – {row.max?.toFixed(1) ?? "—"}
                    </td>
                    <td className="tabular py-2 text-slate-500 dark:text-slate-400">{row.r_squared?.toFixed(2) ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <CardSkeleton />
        )}
        <InlineNote severity="info" className="mt-3">
          A trend is only labelled rising/falling when the fitted slope exceeds 5% of the sensor's plausible
          per-minute movement, which keeps sensor noise out of the trend column.
        </InlineNote>
      </Card>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <SectionHeader
            title="Period comparison"
            subtitle={`Last ${range.label} versus the ${range.label} before it`}
            icon={<GitCompare size={16} />}
            className="mb-3"
          />
          {compare ? (
            <ul className="space-y-2">
              {Object.entries(compare).map(([key, row]) => (
                <li key={key} className="flex items-start justify-between gap-3 rounded-xl px-3 py-2 odd:bg-slate-50/70 dark:odd:bg-slate-900/40">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-700 dark:text-slate-200">{row.label}</p>
                    {row.sufficient_comparison ? (
                      <p className="tabular text-[11px] text-slate-500 dark:text-slate-400">
                        {row.previous_mean?.toFixed(1) ?? "—"} → {row.current_mean?.toFixed(1) ?? "—"} {row.unit}
                      </p>
                    ) : null}
                  </div>
                  <span
                    className={classNames(
                      "tabular whitespace-nowrap text-sm font-semibold",
                      row.delta === null
                        ? "text-slate-400"
                        : row.delta > 0
                          ? "text-orange-500"
                          : "text-sky-500",
                    )}
                  >
                    {row.delta !== null ? formatSigned(row.delta, 2, row.unit) : "—"}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <CardSkeleton />
          )}
          {compare && Object.values(compare).some((row) => !row.sufficient_comparison) ? (
            <InlineNote severity="info" className="mt-3">
              Channels shown as — have no earlier window to compare against yet; comparisons fill in as history
              accumulates.
            </InlineNote>
          ) : null}
        </Card>

        <Card>
          <SectionHeader title="Correlations" subtitle="Only reported above |r| = 0.5 with at least 8 samples" icon={<Layers size={16} />} className="mb-3" />
          {overview.correlations.length ? (
            <ul className="space-y-2">
              {overview.correlations.map((correlation) => (
                <li key={`${correlation.left}-${correlation.right}`} className="rounded-xl bg-slate-50/70 px-3 py-2 text-sm text-slate-700 dark:bg-slate-900/40 dark:text-slate-200">
                  {correlation.message}
                </li>
              ))}
            </ul>
          ) : (
            <InlineNote severity="info">
              No pair of metrics currently crosses the |r| = 0.5 threshold, so no correlation is reported. Correlation is not causation.
            </InlineNote>
          )}
        </Card>
      </div>

      <Card>
        <SectionHeader title="Multi-metric chart" subtitle="Temperature, humidity and air quality on one timeline" className="mb-3" />
        <div className="grid gap-4 lg:grid-cols-3">
          {["temperature_c", "humidity_pct", "air_quality_index"].map((metric) => {
            const series = history?.series?.[metric];
            const color = metric === "temperature_c" ? "#f97316" : metric === "humidity_pct" ? "#38bdf8" : "#22c55e";
            return (
              <div key={metric}>
                {series ? (
                  <TimeSeriesChart series={series} color={color} rangeHours={range.hours} height={180} />
                ) : (
                  <CardSkeleton />
                )}
              </div>
            );
          })}
        </div>
      </Card>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Card>
          <SectionHeader title="Observations" subtitle="Evidence-backed statements for this window" icon={<Sparkles size={16} />} className="mb-3" />
          <ObservationList observations={observations} />
        </Card>

        <Card>
          <SectionHeader
            title="Summary"
            subtitle="Aggregated statistics, risk distribution and alert counts"
            icon={<BarChart3 size={16} />}
            action={
              <div className="flex gap-1">
                {(["day", "week"] as const).map((period) => (
                  <button
                    key={period}
                    type="button"
                    onClick={() => setSummaryPeriod(period)}
                    className={classNames(
                      "rounded-lg px-2.5 py-1 text-[11px] font-medium capitalize transition",
                      summaryPeriod === period
                        ? "bg-slate-900 text-white dark:bg-cyan-500/20 dark:text-cyan-200"
                        : "text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800",
                    )}
                  >
                    {period}
                  </button>
                ))}
              </div>
            }
            className="mb-3"
          />
          {summary ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
                <Metric label="Readings" value={String(summary.reading_count)} />
                <Metric label="Coverage" value={summary.coverage_pct !== null ? `${summary.coverage_pct}%` : "—"} />
                <Metric label="Worst risk level" value={String(summary.risk?.worst_level ?? "—")} />
                <Metric label="Mean risk" value={summary.risk?.mean !== null && summary.risk?.mean !== undefined ? Number(summary.risk.mean).toFixed(1) : "—"} />
              </div>
              <div>
                <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400">Per channel</p>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[420px] text-left text-xs">
                    <thead>
                      <tr className="text-[10px] uppercase tracking-wide text-slate-400">
                        <th className="pb-1 font-medium">Metric</th>
                        <th className="pb-1 font-medium">Min</th>
                        <th className="pb-1 font-medium">Mean</th>
                        <th className="pb-1 font-medium">Max</th>
                        <th className="pb-1 font-medium">Trend</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200/70 dark:divide-slate-800/70">
                      {Object.entries(summary.metrics).map(([key, row]) => (
                        <tr key={key}>
                          <td className="py-1 pr-2 text-slate-600 dark:text-slate-300">{key.replace(/_/g, " ")}</td>
                          <td className="tabular py-1 pr-2 text-slate-600 dark:text-slate-300">{Number(row.min ?? 0).toFixed(1)}</td>
                          <td className="tabular py-1 pr-2 text-slate-600 dark:text-slate-300">{Number(row.mean ?? 0).toFixed(1)}</td>
                          <td className="tabular py-1 pr-2 text-slate-600 dark:text-slate-300">{Number(row.max ?? 0).toFixed(1)}</td>
                          <td className="py-1 text-slate-500 dark:text-slate-400">{String(row.trend ?? "—")}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
              {summary.highlights.length ? (
                <ul className="space-y-1">
                  {summary.highlights.map((highlight) => (
                    <li key={highlight} className="text-xs text-slate-600 dark:text-slate-300">
                      • {highlight}
                    </li>
                  ))}
                </ul>
              ) : null}
              {!Boolean(summary.risk?.diagnostics_available) ? (
                <InlineNote severity="watch">
                  Risk diagnostics need at least 10 readings in the period before distribution statistics are meaningful.
                </InlineNote>
              ) : null}
            </div>
          ) : (
            <CardSkeleton />
          )}
        </Card>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="panel-muted px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-slate-400">{label}</div>
      <div className="tabular font-semibold text-slate-800 dark:text-slate-100">{value}</div>
    </div>
  );
}
