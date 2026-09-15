/** Overview dashboard: risk, environment classification, live metrics, charts and insights. */

import { motion } from "framer-motion";
import { Activity, AlertTriangle, CloudRain, Cpu, Droplets, Gauge, Info, Thermometer, Wind, Sun } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { RiskGauge, RiskTrendChart } from "../components/charts/RiskGauge";
import { TimeSeriesChart } from "../components/charts/TimeSeriesChart";
import { MetricCard } from "../components/dashboard/MetricCard";
import { AlertFeed, AnomalyList, DeviceStatusCard, ObservationList, RiskBreakdown, SensorHealthTable } from "../components/dashboard/Panels";
import { Card, CardSkeleton, Chip, DataBadge, EmptyState, ErrorState, InlineNote, SectionHeader, StatusDot } from "../components/common/Ui";
import { api, ApiError } from "../services/api";
import { usePlatform } from "../state/PlatformContext";
import type { HistoryResponse } from "../types";
import { classNames, clockTime, formatPercent, relativeTime, riskColor, secondsAgo } from "../utils/format";

const RANGES = [
  { label: "15 min", hours: 0.25, bucket: "15m" },
  { label: "1 h", hours: 1, bucket: "1h" },
  { label: "6 h", hours: 6, bucket: "6h" },
  { label: "24 h", hours: 24, bucket: "24h" },
  { label: "7 d", hours: 168, bucket: "7d" },
];

const METRIC_TABS = [
  { key: "temperature_c", label: "Temperature", icon: Thermometer, color: "#f97316", band: { low: 18, high: 26, label: "comfort band 18–26 °C" } },
  { key: "humidity_pct", label: "Humidity", icon: Droplets, color: "#38bdf8", band: { low: 30, high: 65, label: "comfort band 30–65 %RH" } },
  { key: "pressure_hpa", label: "Pressure", icon: Gauge, color: "#a78bfa", band: { low: null, high: null } },
  { key: "air_quality_index", label: "Air quality", icon: Wind, color: "#22c55e", band: { low: null, high: null } },
  { key: "light_pct", label: "Light", icon: Sun, color: "#eab308", band: { low: null, high: null } },
  { key: "rain_pct", label: "Rain", icon: CloudRain, color: "#3b82f6", band: { low: null, high: null } },
];

export default function Dashboard() {
  const { overview, status, device, meta, loading, error, connection, refresh } = usePlatform();
  const [range, setRange] = useState(RANGES[2]);
  const [metricKey, setMetricKey] = useState(METRIC_TABS[0].key);
  const [history, setHistory] = useState<HistoryResponse | null>(null);
  const [riskHistory, setRiskHistory] = useState<{ timestamp: string; score: number; level: number }[]>([]);
  const [historyError, setHistoryError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setHistoryError(null);
    void api
      .history({ hours: range.hours, bucket: range.bucket, limit: 300 })
      .then((response) => {
        if (!cancelled) setHistory(response);
      })
      .catch((caught) => {
        if (!cancelled) setHistoryError(caught instanceof ApiError ? caught.detail : "History unavailable.");
      });
    void api
      .riskAnalysis(undefined, range.hours >= 6 ? range.hours : 6)
      .then((response) => {
        if (!cancelled) setRiskHistory(response.trend);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [range, overview?.latest?.received_at]);

  const simulated = overview?.data_source === "simulation" || Boolean(meta?.simulation_mode);
  const activeMetric = METRIC_TABS.find((item) => item.key === metricKey) ?? METRIC_TABS[0];
  const series = history?.series?.[metricKey];

  const metrics = overview?.metrics ?? {};
  const trendStrip = useMemo(
    () =>
      [
        { label: "Heat index", value: metrics.heat_index_c ?? null, icon: Thermometer },
        { label: "Dew point", value: metrics.dew_point_c ?? null, icon: Droplets },
        { label: "BMP280 t°", value: metrics.bmp_temperature_c ?? null, icon: Gauge },
        { label: "Rain raw", value: metrics.rain_raw ?? null, icon: CloudRain },
        { label: "Light raw", value: metrics.ldr_raw ?? null, icon: Sun },
        { label: "Air raw", value: metrics.air_quality_raw ?? null, icon: Wind },
      ].filter((item) => item.value !== null),
    [metrics],
  );

  if (loading && !overview) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 6 }).map((_, index) => (
          <CardSkeleton key={index} />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {error && !overview?.has_data ? (
        <ErrorState
          title="Backend not reachable"
          message={error}
          onRetry={() => void refresh()}
        />
      ) : null}

      {!overview?.has_data ? (
        <Card>
          <EmptyState
            icon={<Cpu size={20} />}
            title="Arduino offline - waiting for first data"
            message={
              overview?.device?.status_message ??
              "Waiting for the Arduino UNO R4 Wi-Fi to send sensor data. Start the simulator (python simulator/run_simulator.py) or flash the firmware to populate the dashboard."
            }
            action={
              <div className="flex flex-wrap items-center justify-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                <Link to="/device" className="rounded-lg border border-slate-200 px-3 py-1.5 transition hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800">
                  Hardware setup
                </Link>
                <Link to="/settings" className="rounded-lg border border-slate-200 px-3 py-1.5 transition hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800">
                  Enable simulation mode
                </Link>
              </div>
            }
          />
        </Card>
      ) : null}

      {overview?.has_data ? (
        <>
          {/* Hero row */}
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
            <Card className="relative overflow-hidden">
              <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
                <RiskGauge
                  score={overview.risk.score}
                  level={overview.risk.level}
                  label={overview.risk.label}
                  confidence={overview.risk.confidence}
                />
                <div className="min-w-0 flex-1 space-y-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Chip severity={overview.risk.level >= 4 ? "critical" : overview.risk.level === 3 ? "watch" : "good"}>
                      {overview.risk.code.replace("_", " ")}
                    </Chip>
                    {simulated ? <DataBadge source="simulation" /> : <DataBadge source={overview.data_source} />}
                    {overview.stale ? <Chip severity="warning">stale reading</Chip> : null}
                  </div>
                  <p className="text-sm leading-relaxed text-slate-600 dark:text-slate-300">
                    {overview.risk.description}
                  </p>
                  <p className="text-sm font-medium text-slate-800 dark:text-slate-100">
                    {overview.classification.label}
                  </p>
                  <ul className="space-y-1">
                    {overview.risk.reasons.slice(0, 3).map((reason) => (
                      <li key={reason} className="flex items-start gap-2 text-xs text-slate-600 dark:text-slate-300">
                        <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-orange-500" />
                        {reason}
                      </li>
                    ))}
                  </ul>
                  <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-500 dark:text-slate-400">
                    <span>Updated {relativeTime(overview.latest.received_at ?? overview.server_time)}</span>
                    <span>· {overview.reading_count} readings in {range.label}</span>
                    <span>· health {overview.risk.context.health_score?.toFixed(0) ?? "—"}%</span>
                    <Link to="/risk" className="font-medium text-cyan-600 hover:underline dark:text-cyan-400">
                      full risk analysis →
                    </Link>
                  </div>
                </div>
              </div>
            </Card>

            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-1">
              <Card>
                <SectionHeader
                  title="Device"
                  subtitle={simulated ? "Simulator source active" : "Arduino UNO R4 Wi-Fi"}
                  icon={<Cpu size={16} />}
                  className="mb-3"
                />
                <DeviceStatusCard device={device} simulated={simulated} />
              </Card>
              <Card>
                <SectionHeader
                  title="Risk trend"
                  subtitle={`Score history over the last ${range.hours >= 6 ? range.label : "6 h"}`}
                  icon={<Activity size={16} />}
                  className="mb-3"
                />
                <RiskTrendChart data={riskHistory} rangeHours={range.hours} height={150} />
              </Card>
            </div>
          </div>

          {/* Metric cards */}
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {overview.channels.map((card, index) => (
              <MetricCard key={card.channel} card={card} simulated={simulated} index={index} />
            ))}
          </div>

          {/* Charts + insights */}
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
            <Card>
              <SectionHeader
                title="Live sensor history"
                subtitle="Bucketed averages from stored readings. Hover for exact values and units."
                icon={<Activity size={16} />}
                action={
                  <div className="flex flex-wrap items-center gap-1">
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
                }
              />
              <div className="mb-3 flex flex-wrap gap-1.5">
                {METRIC_TABS.map((tab) => (
                  <button
                    key={tab.key}
                    type="button"
                    onClick={() => setMetricKey(tab.key)}
                    className={classNames(
                      "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[11px] font-medium transition",
                      metricKey === tab.key
                        ? "border-transparent text-white"
                        : "border-slate-200 text-slate-600 hover:border-slate-300 dark:border-slate-700 dark:text-slate-300",
                    )}
                    style={metricKey === tab.key ? { backgroundColor: tab.color } : undefined}
                  >
                    <tab.icon size={12} />
                    {tab.label}
                  </button>
                ))}
              </div>
              {historyError ? (
                <ErrorState message={historyError} title="Chart unavailable" />
              ) : series ? (
                <TimeSeriesChart
                  series={series}
                  color={activeMetric.color}
                  rangeHours={range.hours}
                  band={{ low: activeMetric.band.low ?? null, high: activeMetric.band.high ?? null, label: activeMetric.band.label }}
                  decimals={metricKey === "pressure_hpa" ? 1 : 1}
                  height={280}
                />
              ) : (
                <CardSkeleton />
              )}
              {history && !history.sufficient_data ? (
                <InlineNote severity="watch" className="mt-3">
                  {history.notes[0] ?? "Limited history in this range: trends need more readings."}
                </InlineNote>
              ) : null}
            </Card>

            <div className="space-y-4">
              <Card>
                <SectionHeader
                  title="Latest observations"
                  subtitle="Generated only when the data supports the claim."
                  icon={<Info size={16} />}
                  className="mb-3"
                />
                <ObservationList observations={overview.observation_list} />
              </Card>
              <Card>
                <SectionHeader
                  title="Anomalies"
                  subtitle={`${overview.anomalies.length} in the analysis window`}
                  icon={<AlertTriangle size={16} />}
                  className="mb-3"
                />
                <AnomalyList anomalies={overview.anomalies.slice(0, 4)} />
              </Card>
            </div>
          </div>

          {/* Secondary metrics strip */}
          {trendStrip.length ? (
            <Card>
              <SectionHeader title="Derived & raw readings" subtitle="Secondary channels and raw ADC values" className="mb-3" />
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
                {trendStrip.map((item) => (
                  <div key={item.label} className="panel-muted px-3 py-2">
                    <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-slate-400">
                      <item.icon size={11} />
                      {item.label}
                    </div>
                    <div className="tabular text-sm font-semibold text-slate-800 dark:text-slate-100">
                      {item.value !== null ? Number(item.value).toFixed(1) : "—"}
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          ) : null}

          {/* Risk + alerts + health */}
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
            <Card>
              <SectionHeader
                title="Why this risk score"
                subtitle="Every factor's contribution, so the number is auditable rather than arbitrary."
                icon={<Gauge size={16} />}
                className="mb-3"
              />
              <RiskBreakdown risk={overview.risk} />
            </Card>
            <div className="space-y-4">
              <Card>
                <SectionHeader
                  title="Active alerts"
                  subtitle={`${overview.active_alert_count} currently active`}
                  icon={<AlertTriangle size={16} />}
                  action={
                    <Link to="/alerts" className="text-xs font-medium text-cyan-600 hover:underline dark:text-cyan-400">
                      alert centre →
                    </Link>
                  }
                  className="mb-3"
                />
                <AlertFeed alerts={overview.alerts} />
              </Card>
              <Card>
                <SectionHeader title="Sensor health" subtitle="Reporting rate, staleness and stuck-value checks" className="mb-3" />
                <SensorHealthTable sensors={overview.sensor_health} />
              </Card>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-400">
            <span className="inline-flex items-center gap-1.5">
              <StatusDot severity={connection === "live" ? "good" : "watch"} pulse={connection === "live"} />
              {connection === "live" ? "Realtime stream active" : connection}
            </span>
            <span>Server time {clockTime(overview.server_time)}</span>
            <span>Last payload {secondsAgo(status?.device_seconds_since_payload)} ago</span>
            <span>Coverage {formatPercent(overview.risk.data_coverage)}</span>
            <span className="inline-flex items-center gap-1">
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: riskColor(overview.risk.level) }} />
              LED level {Math.round(overview.risk.level)} / 5 · buzzer{" "}
              {String(overview.risk.context.buzzer_pattern ?? "silent").replace(/_/g, " ")}
            </span>
          </div>

          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="sr-only"
            aria-live="polite"
          >
            Risk score {overview.risk.score.toFixed(0)} level {overview.risk.level}
          </motion.div>
        </>
      ) : null}
    </div>
  );
}
