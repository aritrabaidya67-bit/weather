/**
 * Sensor detail: A deep dive into a specific metric.
 * Beautiful large chart, clear statistical breakdowns, and baseline context.
 */


import { Activity, ArrowLeft, TrendingUp, Info } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { TimeSeriesChart } from "../components/charts/TimeSeriesChart";
import { AnomalyList } from "../components/dashboard/Panels";
import { CardSkeleton, Chip, DataBadge, EmptyState, ErrorState, SectionHeaderPill, StatusDot } from "../components/common/Ui";
import { SegmentedToggle, TREND_RANGES } from "../components/dashboard/TrendPanel";
import { api, ApiError } from "../services/api";
import { usePlatform } from "../state/PlatformContext";
import type { HistoryResponse } from "../types";
import { classNames, formatSigned, unitSymbol } from "../utils/format";

export default function SensorDetail() {
  const { channelId } = useParams<{ channelId: string }>();
  const { overview, meta } = usePlatform();
  const channel = overview?.channels.find((item) => item.channel === channelId);
  const channelSpec = meta?.channels.find((item) => item.key === channelId);
  const sensorSpec = meta?.sensors.find((item) => item.key === channelSpec?.primary);
  
  const [rangeLabel, setRangeLabel] = useState("24h");
  const range = TREND_RANGES.find(r => r.label === rangeLabel) ?? TREND_RANGES[3];
  
  const [history, setHistory] = useState<HistoryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [baseline, setBaseline] = useState<{ mean: number | null; sigma: number | null; samples: number } | null>(null);

  const metricKey = channelSpec?.primary ?? channel?.metric ?? "temperature_c";

  useEffect(() => {
    if (!channelSpec) return;
    let cancelled = false;
    setError(null);
    void api.history({ hours: range.hours, bucket: range.bucket, metrics: channelSpec.primary, limit: 500 })
      .then((res) => { if (!cancelled) setHistory(res); })
      .catch((err) => { if (!cancelled) setError(err instanceof ApiError ? err.detail : "History unavailable."); });
    
    void api.baseline()
      .then((res) => { if (!cancelled) setBaseline(res.metrics[channelSpec.primary] ?? null); })
      .catch(() => undefined);
      
    return () => { cancelled = true; };
  }, [channelSpec, range, overview?.latest?.received_at]);

  const series = history?.series?.[metricKey];
  const anomalies = useMemo(() => (overview?.anomalies ?? []).filter((item) => item.sensor === metricKey), [overview?.anomalies, metricKey]);

  if (!channelSpec) {
    return (
      <div className="panel p-12 text-center min-h-[50vh] flex flex-col justify-center items-center">
        <Activity size={32} className="text-slate-400 mb-4" />
        <EmptyState title="Unknown Sensor" message={`No channel named "${channelId}".`} />
      </div>
    );
  }

  if (!overview?.has_data || !channel) {
    return (
      <div className="panel p-12 text-center min-h-[50vh] flex flex-col justify-center items-center">
        <Activity size={32} className="text-slate-400 mb-4" />
        <EmptyState title={`Waiting for ${channelSpec.label}`} message="Data will appear once readings arrive from the device." />
      </div>
    );
  }

  const bands = sensorSpec?.bands ?? [];
  const unit = unitSymbol(channel.unit);
  const color = channel.color || "#38bdf8";

  return (
    <div className="space-y-6 animate-float-in">
      
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <Link to="/sensors" className="inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-widest text-slate-500 hover:text-cyan-500 transition-colors mb-3">
            <ArrowLeft size={14} /> Back to Dashboard
          </Link>
          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-bold tracking-tight text-slate-900 dark:text-white">{channelSpec.label}</h1>
            <Chip severity={channel.severity}>
              <StatusDot severity={channel.severity} pulse={channel.severity === 'critical'} />
              {channel.status}
            </Chip>
          </div>
          <p className="text-sm font-medium text-slate-500 dark:text-slate-400 mt-1 uppercase tracking-widest">
            {channelSpec.sensor}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <DataBadge source={overview.data_source} />
          <SegmentedToggle
            options={TREND_RANGES.map((item) => ({ key: item.label, label: item.label }))}
            value={rangeLabel}
            onChange={setRangeLabel}
            compact
          />
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        
        {/* Main Chart Area */}
        <div className="space-y-6">
          <section className="panel p-6 sm:p-8 relative overflow-hidden">
            <div className="absolute top-0 right-0 p-8 opacity-5 pointer-events-none">
               <Activity size={120} style={{ color }} />
            </div>

            <div className="flex flex-wrap items-end gap-8 mb-8 relative z-10">
              <div>
                <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-1">Live Reading</p>
                <div className="flex items-baseline gap-2">
                  <span className="tabular text-6xl font-bold tracking-tighter text-slate-900 dark:text-white" style={{ color }}>
                    {channel.value !== null ? channel.value.toFixed(channel.decimals) : "—"}
                  </span>
                  <span className="text-2xl font-medium text-slate-400">{unit}</span>
                </div>
                <div className="mt-2 flex items-center gap-2 text-sm font-medium text-slate-500 dark:text-slate-400">
                  <TrendingUp size={16} />
                  {channel.trend} ({formatSigned(channel.change, channel.decimals, channel.unit)})
                </div>
              </div>

              <div className="flex-1 grid grid-cols-2 sm:grid-cols-4 gap-4 bg-slate-50/50 dark:bg-surface-900/50 p-4 rounded-2xl border border-slate-200/50 dark:border-white/5">
                <Stat label="Min" value={channel.stats.min} decimals={channel.decimals} unit={unit} />
                <Stat label="Mean" value={channel.stats.mean} decimals={channel.decimals} unit={unit} />
                <Stat label="Max" value={channel.stats.max} decimals={channel.decimals} unit={unit} />
                <Stat label="Std Dev" value={channel.stats.stdev} decimals={channel.decimals} unit={unit} />
              </div>
            </div>

            <div className="h-[340px] relative z-10">
              {error ? (
                <ErrorState title="Chart unavailable" message={error} />
              ) : series ? (
                <TimeSeriesChart series={series} color={color} rangeHours={range.hours} height={340} decimals={channel.decimals} />
              ) : (
                <CardSkeleton className="h-[340px]" />
              )}
            </div>
            
            {history && !history.sufficient_data && (
              <p className="text-xs text-amber-500 font-medium text-center mt-4">
                {history.notes[0] ?? "Gathering more data for trend statistics..."}
              </p>
            )}
          </section>

          {/* Anomalies */}
          <section className="panel p-6">
            <SectionHeaderPill icon={<Activity size={16} />} title="Detected Anomalies" className="mb-4" />
            <AnomalyList anomalies={anomalies} />
          </section>
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          <section className="panel p-6">
            <SectionHeaderPill icon={<Info size={16} />} title="Interpretation" className="mb-4" />
            <p className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed mb-6">{sensorSpec?.description}</p>
            
            <div className="space-y-2">
              <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-2">Threshold Bands</p>
              <ul className="space-y-1.5">
                {bands.map((band) => {
                  const active = channel.value !== null && channel.value <= band.until && (bands.find(i => channel.value! <= i.until)?.until === band.until);
                  return (
                    <li key={`${band.until}-${band.label}`} className={classNames(
                      "flex items-center justify-between rounded-xl px-3 py-2 text-xs font-medium transition-colors",
                      active ? "bg-cyan-500/10 text-cyan-700 dark:text-cyan-400 border border-cyan-500/20" : "text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-surface-900/40"
                    )}>
                      <span>≤ {band.until} {unit}</span>
                      <span>{band.label}</span>
                    </li>
                  );
                })}
              </ul>
            </div>
            
            {sensorSpec?.calibration_notes && (
              <div className="mt-6 p-4 rounded-xl bg-sky-50 dark:bg-sky-500/10 border border-sky-100 dark:border-sky-500/20">
                <p className="text-xs font-medium text-sky-700 dark:text-sky-300">{sensorSpec.calibration_notes}</p>
              </div>
            )}
          </section>

          <section className="panel p-6">
            <SectionHeaderPill icon={<TrendingUp size={16} />} title="Rolling Baseline" className="mb-4" />
            {baseline && baseline.samples > 0 ? (
              <div className="grid grid-cols-2 gap-4">
                <div className="p-4 rounded-xl bg-slate-50 dark:bg-surface-900/40 border border-slate-100 dark:border-white/5">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-1">Mean</p>
                  <p className="text-xl font-bold tabular text-slate-700 dark:text-slate-200">{baseline.mean?.toFixed(channel.decimals) ?? "—"}</p>
                </div>
                <div className="p-4 rounded-xl bg-slate-50 dark:bg-surface-900/40 border border-slate-100 dark:border-white/5">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-1">Robust σ</p>
                  <p className="text-xl font-bold tabular text-slate-700 dark:text-slate-200">{baseline.sigma?.toFixed(2) ?? "—"}</p>
                </div>
                <div className="col-span-2 p-3 text-center rounded-xl bg-slate-50/50 dark:bg-black/20">
                  <p className="text-xs font-medium text-slate-500">Based on <span className="font-bold text-slate-700 dark:text-slate-300">{baseline.samples}</span> recent samples</p>
                </div>
              </div>
            ) : (
              <p className="text-xs text-center text-slate-500 dark:text-slate-400 py-6 border-dashed border-2 rounded-xl border-slate-200 dark:border-white/10">
                Waiting for at least 12 samples to establish an anomaly baseline.
              </p>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, decimals, unit }: { label: string; value: number | null; decimals: number; unit: string }) {
  return (
    <div>
      <div className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-1">{label}</div>
      <div className="tabular text-base font-bold text-slate-800 dark:text-slate-200">
        {value !== null ? `${value.toFixed(decimals)} ${unit}`.trim() : "—"}
      </div>
    </div>
  );
}
