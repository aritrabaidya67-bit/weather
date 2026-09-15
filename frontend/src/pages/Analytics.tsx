/**
 * Analytics: Re-architected for progressive disclosure.
 * Users explore through tabs instead of being overwhelmed by data dumps.
 */

import { motion, AnimatePresence } from "framer-motion";
import { BarChart3, GitCompare, Layers, LineChart, Sparkles, Activity } from "lucide-react";
import { useEffect, useState } from "react";
import { TimeSeriesChart } from "../components/charts/TimeSeriesChart";
import { ObservationList } from "../components/dashboard/Panels";
import { CardSkeleton, Chip, DataBadge, EmptyState, SectionHeaderPill } from "../components/common/Ui";
import { SegmentedToggle, TREND_RANGES } from "../components/dashboard/TrendPanel";
import { api } from "../services/api";
import { usePlatform } from "../state/PlatformContext";
import type { HistoryResponse, Observation, SummaryResponse } from "../types";
import { classNames, formatSigned, unitSymbol } from "../utils/format";

type Tab = "trends" | "comparisons" | "patterns" | "summary";

export default function Analytics() {
  const { overview } = usePlatform();
  const [activeTab, setActiveTab] = useState<Tab>("trends");
  const [rangeLabel, setRangeLabel] = useState("24h");
  const range = TREND_RANGES.find(r => r.label === rangeLabel) ?? TREND_RANGES[2];

  const [history, setHistory] = useState<HistoryResponse | null>(null);
  const [trends, setTrends] = useState<any>(null);
  const [compare, setCompare] = useState<any>(null);
  const [observations, setObservations] = useState<Observation[]>([]);
  const [summary, setSummary] = useState<SummaryResponse | null>(null);

  useEffect(() => {
    void api.history({ hours: range.hours, bucket: range.bucket, limit: 600 }).then(setHistory).catch(() => setHistory(null));
    void api.trends(undefined, range.hours).then((res) => setTrends(res.metrics)).catch(() => setTrends(null));
    void api.compare(undefined, Math.max(0.5, range.hours)).then((res) => setCompare(res.metrics)).catch(() => setCompare(null));
    void api.observations(undefined, range.hours).then((res) => setObservations(res.observations as Observation[])).catch(() => setObservations([]));
    void api.summary("day").then(setSummary).catch(() => setSummary(null));
  }, [range, overview?.latest?.received_at]);

  if (!overview?.has_data) {
    return (
      <div className="panel flex flex-col items-center justify-center p-12 text-center min-h-[60vh]">
        <div className="rounded-full bg-slate-100 p-4 dark:bg-surface-800 mb-6 text-slate-400">
          <LineChart size={32} />
        </div>
        <EmptyState
          title="No data to analyze"
          message="Analytics requires stored readings. The system will populate this automatically once devices report data."
        />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-float-in">
      
      {/* Header and Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 panel p-5">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-2">
            <BarChart3 size={20} className="text-cyan-500" />
            Analytics
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Deep dive into environmental patterns and historical data.
          </p>
        </div>
        <div className="flex flex-col sm:flex-row items-end sm:items-center gap-3">
          <DataBadge source={overview.data_source} />
          <SegmentedToggle
            options={TREND_RANGES.map((item) => ({ key: item.label, label: item.label }))}
            value={rangeLabel}
            onChange={setRangeLabel}
            compact
          />
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-hide">
        {[
          { id: "trends", label: "Trends & Charts", icon: LineChart },
          { id: "comparisons", label: "Comparisons", icon: GitCompare },
          { id: "patterns", label: "Patterns", icon: Layers },
          { id: "summary", label: "Daily Summary", icon: Activity },
        ].map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as Tab)}
            className={classNames(
              "flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition-all whitespace-nowrap",
              activeTab === tab.id 
                ? "bg-slate-900 text-white shadow-md dark:bg-white dark:text-slate-900" 
                : "bg-white/60 text-slate-500 hover:bg-white hover:text-slate-900 dark:bg-surface-900/60 dark:text-slate-400 dark:hover:bg-surface-800 dark:hover:text-white"
            )}
          >
            <tab.icon size={16} />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content Area */}
      <div className="relative">
        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.3 }}
          >
            {activeTab === "trends" && <TrendsTab trends={trends} history={history} range={range} />}
            {activeTab === "comparisons" && <ComparisonsTab compare={compare} range={range} />}
            {activeTab === "patterns" && <PatternsTab correlations={overview.correlations} observations={observations} />}
            {activeTab === "summary" && <SummaryTab summary={summary} />}
          </motion.div>
        </AnimatePresence>
      </div>

    </div>
  );
}

// ============================================================================
// TAB COMPONENTS
// ============================================================================

function TrendsTab({ trends, history, range }: any) {
  return (
    <div className="space-y-6">
      <section className="panel p-6">
        <SectionHeaderPill icon={<LineChart size={16} />} title="Historical Multi-Chart" className="mb-6" />
        <div className="grid gap-6 lg:grid-cols-3">
          {["temperature_c", "humidity_pct", "air_quality_index"].map((metric) => {
            const series = history?.series?.[metric];
            const color = metric === "temperature_c" ? "#f97316" : metric === "humidity_pct" ? "#38bdf8" : "#22c55e";
            return (
              <div key={metric} className="panel-muted p-4">
                <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-4">
                  {metric.replace("_c", "").replace("_pct", "").replace("_index", "").replace("_", " ")}
                </p>
                {series ? (
                  <TimeSeriesChart series={series} color={color} rangeHours={range.hours} height={160} />
                ) : (
                  <CardSkeleton className="h-[160px]" />
                )}
              </div>
            );
          })}
        </div>
      </section>

      <section className="panel p-6">
        <SectionHeaderPill icon={<Activity size={16} />} title="Statistical Trends" className="mb-6" />
        {trends ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[800px] text-left text-sm">
              <thead>
                <tr className="text-[11px] uppercase tracking-wider text-slate-400 border-b border-slate-200/50 dark:border-white/10">
                  <th className="pb-3 font-medium">Channel</th>
                  <th className="pb-3 font-medium">Current</th>
                  <th className="pb-3 font-medium">State</th>
                  <th className="pb-3 font-medium">Change</th>
                  <th className="pb-3 font-medium">Velocity (per hr)</th>
                  <th className="pb-3 font-medium">Avg</th>
                  <th className="pb-3 font-medium">Range</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-white/5">
                {Object.entries(trends).map(([key, row]: any) => (
                  <tr key={key} className="hover:bg-slate-50/50 dark:hover:bg-white/[0.02] transition-colors">
                    <td className="py-3 pr-4 font-semibold text-slate-800 dark:text-slate-200">{row.label}</td>
                    <td className="tabular py-3 pr-4 text-slate-600 dark:text-slate-300">
                      {row.latest?.toFixed(1) ?? "—"} <span className="text-[10px] text-slate-400">{unitSymbol(row.unit)}</span>
                    </td>
                    <td className="py-3 pr-4">
                      <Chip severity={row.trend === "stable" ? "info" : row.trend === "rising" ? "watch" : "info"}>
                        {row.trend}
                      </Chip>
                    </td>
                    <td className="tabular py-3 pr-4 font-medium text-slate-700 dark:text-slate-200">
                      {formatSigned(row.change, 2, row.unit)}
                    </td>
                    <td className="tabular py-3 pr-4 text-slate-500">
                      {row.rate_of_change_per_hour !== null ? `${row.rate_of_change_per_hour.toFixed(2)}/h` : "—"}
                    </td>
                    <td className="tabular py-3 pr-4 text-slate-600 dark:text-slate-400">{row.mean?.toFixed(1) ?? "—"}</td>
                    <td className="tabular py-3 text-slate-500">
                      {row.min?.toFixed(1) ?? "—"} <span className="opacity-50">to</span> {row.max?.toFixed(1) ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <CardSkeleton />}
      </section>
    </div>
  );
}

function ComparisonsTab({ compare, range }: any) {
  return (
    <div className="panel p-6">
      <SectionHeaderPill icon={<GitCompare size={16} />} title={`Comparison vs Previous ${range.label}`} className="mb-6" />
      {compare ? (
        <div className="grid gap-4 sm:grid-cols-2">
          {Object.entries(compare).map(([key, row]: any) => (
            <div key={key} className="flex flex-col justify-between rounded-2xl border border-slate-200/50 bg-slate-50/50 p-5 dark:border-white/5 dark:bg-surface-900/50">
              <p className="text-sm font-semibold tracking-wide text-slate-700 dark:text-slate-200 mb-4">{row.label}</p>
              
              <div className="flex items-end justify-between">
                <div>
                  {row.sufficient_comparison ? (
                    <div className="flex items-center gap-2 text-xs font-medium text-slate-400">
                      <span className="tabular">{row.previous_mean?.toFixed(1) ?? "—"}</span>
                      <GitCompare size={12} className="opacity-50" />
                      <span className="tabular text-slate-600 dark:text-slate-300">{row.current_mean?.toFixed(1) ?? "—"} {row.unit}</span>
                    </div>
                  ) : (
                    <span className="text-xs text-slate-400">Insufficient history</span>
                  )}
                </div>
                
                <span
                  className={classNames(
                    "tabular text-xl font-bold tracking-tight",
                    row.delta === null ? "text-slate-400" : row.delta > 0 ? "text-orange-500" : "text-sky-500"
                  )}
                >
                  {row.delta !== null ? formatSigned(row.delta, 2, row.unit) : "—"}
                </span>
              </div>
            </div>
          ))}
        </div>
      ) : <CardSkeleton />}
    </div>
  );
}

function PatternsTab({ correlations, observations }: any) {
  return (
    <div className="grid gap-6 md:grid-cols-2">
      <section className="panel p-6">
        <SectionHeaderPill icon={<Sparkles size={16} />} title="System Observations" className="mb-6" />
        <ObservationList observations={observations} />
      </section>

      <section className="panel p-6">
        <SectionHeaderPill icon={<Layers size={16} />} title="Detected Correlations" className="mb-6" />
        {correlations?.length ? (
          <ul className="space-y-3">
            {correlations.map((correlation: any) => (
              <li key={`${correlation.left}-${correlation.right}`} className="rounded-xl border border-slate-200/50 bg-slate-50/50 p-4 text-sm text-slate-600 dark:border-white/5 dark:bg-surface-900/50 dark:text-slate-300 leading-relaxed">
                {correlation.message}
              </li>
            ))}
          </ul>
        ) : (
          <div className="flex h-32 flex-col items-center justify-center text-center">
            <Layers size={24} className="text-slate-300 mb-2" />
            <p className="text-sm text-slate-500">No strong correlations detected in this timeframe.</p>
          </div>
        )}
      </section>
    </div>
  );
}

function SummaryTab({ summary }: any) {
  if (!summary) return <CardSkeleton />;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div className="panel p-5 text-center">
          <p className="text-[10px] uppercase tracking-widest text-slate-400 font-bold mb-2">Readings Processed</p>
          <p className="text-3xl font-bold text-slate-900 dark:text-white">{summary.reading_count}</p>
        </div>
        <div className="panel p-5 text-center">
          <p className="text-[10px] uppercase tracking-widest text-slate-400 font-bold mb-2">Uptime Coverage</p>
          <p className="text-3xl font-bold text-slate-900 dark:text-white">{summary.coverage_pct ?? "—"}%</p>
        </div>
        <div className="panel p-5 text-center">
          <p className="text-[10px] uppercase tracking-widest text-slate-400 font-bold mb-2">Avg Risk</p>
          <p className="text-3xl font-bold text-slate-900 dark:text-white">{summary.risk?.mean ? Number(summary.risk.mean).toFixed(1) : "—"}</p>
        </div>
        <div className="panel p-5 text-center">
          <p className="text-[10px] uppercase tracking-widest text-slate-400 font-bold mb-2">Worst Level</p>
          <p className="text-3xl font-bold text-rose-500">{summary.risk?.worst_level ?? "—"}</p>
        </div>
      </div>
      
      <section className="panel p-6">
        <SectionHeaderPill icon={<Activity size={16} />} title="Highlights" className="mb-4" />
        {summary.highlights?.length ? (
          <ul className="space-y-3">
            {summary.highlights.map((highlight: string, i: number) => (
              <li key={i} className="flex items-start gap-3 text-sm text-slate-600 dark:text-slate-300">
                <span className="mt-1 h-1.5 w-1.5 rounded-full bg-cyan-500 shrink-0" />
                {highlight}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-400">No major highlights for this period.</p>
        )}
      </section>
    </div>
  );
}
