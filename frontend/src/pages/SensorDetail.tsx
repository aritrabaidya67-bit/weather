/** Sensor detail: live value, chart with ranges, statistics, anomalies and interpretation. */

import { Activity, ArrowLeft, TrendingUp } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { TimeSeriesChart } from "../components/charts/TimeSeriesChart";
import { AnomalyList } from "../components/dashboard/Panels";
import { Card, CardSkeleton, Chip, DataBadge, EmptyState, ErrorState, InlineNote, SectionHeader, StatusDot } from "../components/common/Ui";
import { api, ApiError } from "../services/api";
import { usePlatform } from "../state/PlatformContext";
import type { HistoryResponse } from "../types";
import { classNames, formatSigned, relativeTime, unitSymbol } from "../utils/format";

const RANGES = [
  { label: "15 min", hours: 0.25, bucket: "15m" },
  { label: "1 h", hours: 1, bucket: "1h" },
  { label: "6 h", hours: 6, bucket: "6h" },
  { label: "24 h", hours: 24, bucket: "24h" },
  { label: "7 d", hours: 168, bucket: "7d" },
];

export default function SensorDetail() {
  const { channelId } = useParams<{ channelId: string }>();
  const { overview, meta } = usePlatform();
  const channel = overview?.channels.find((item) => item.channel === channelId);
  const channelSpec = meta?.channels.find((item) => item.key === channelId);
  const sensorSpec = meta?.sensors.find((item) => item.key === channelSpec?.primary);
  const [range, setRange] = useState(RANGES[2]);
  const [history, setHistory] = useState<HistoryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [baseline, setBaseline] = useState<{ mean: number | null; sigma: number | null; samples: number } | null>(null);

  const metricKey = channelSpec?.primary ?? channel?.metric ?? "temperature_c";

  useEffect(() => {
    if (!channelSpec) return;
    let cancelled = false;
    setError(null);
    void api
      .history({ hours: range.hours, bucket: range.bucket, metrics: channelSpec.primary, limit: 500 })
      .then((response) => {
        if (!cancelled) setHistory(response);
      })
      .catch((caught) => {
        if (!cancelled) setError(caught instanceof ApiError ? caught.detail : "History unavailable.");
      });
    void api
      .baseline()
      .then((response) => {
        if (!cancelled) setBaseline(response.metrics[channelSpec.primary] ?? null);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [channelSpec, range, overview?.latest?.received_at]);

  const series = history?.series?.[metricKey];
  const anomalies = useMemo(
    () => (overview?.anomalies ?? []).filter((item) => item.sensor === metricKey),
    [overview?.anomalies, metricKey],
  );

  if (!channelSpec) {
    return (
      <Card>
        <EmptyState
          icon={<Activity size={20} />}
          title="Unknown sensor"
          message={`There is no channel named "${channelId}". Known channels: temperature, humidity, pressure, air_quality, light, rain.`}
        />
      </Card>
    );
  }

  if (!overview?.has_data || !channel) {
    return (
      <Card>
        <EmptyState
          icon={<Activity size={20} />}
          title={`No data for ${channelSpec.label}`}
          message="Waiting for the Arduino UNO R4 Wi-Fi to send sensor data. Values, statistics and anomaly history appear once readings arrive."
        />
      </Card>
    );
  }

  const bands = sensorSpec?.bands ?? [];
  const unit = unitSymbol(channel.unit);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link to="/sensors" className="inline-flex items-center gap-1 text-xs text-slate-500 hover:underline dark:text-slate-400">
            <ArrowLeft size={12} /> all sensors
          </Link>
          <h1 className="mt-1 text-xl font-semibold text-slate-900 dark:text-slate-100">{channelSpec.label}</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            {channelSpec.sensor} · metric <code className="text-[11px]">{channelSpec.primary}</code>
          </p>
        </div>
        <div className="flex items-center gap-2">
          {overview.data_source === "simulation" ? <DataBadge source="simulation" /> : <DataBadge source={overview.data_source} />}
          <Chip severity={channel.severity}>
            <StatusDot severity={channel.severity} />
            {channel.status}
          </Chip>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Card>
          <SectionHeader
            title="Live value"
            subtitle={`Interpretation bands from the backend registry · updated ${relativeTime(overview.latest.received_at)}`}
            action={
              <div className="flex flex-wrap gap-1">
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
          <div className="flex flex-wrap items-end gap-6">
            <div>
              <div className="tabular text-4xl font-semibold tracking-tight text-slate-900 dark:text-slate-50">
                {channel.value !== null ? channel.value.toFixed(channel.decimals) : "—"}
                <span className="ml-1.5 text-sm font-normal text-slate-400">{unit}</span>
              </div>
              <div className="mt-1 flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                <TrendingUp size={12} />
                {channel.trend} · {formatSigned(channel.change, channel.decimals, channel.unit)} in this window
                {channel.rate_of_change_per_hour !== null ? ` · ${channel.rate_of_change_per_hour.toFixed(2)} ${unit}/h` : ""}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs sm:grid-cols-4">
              <Stat label="min" value={channel.stats.min} decimals={channel.decimals} unit={unit} />
              <Stat label="mean" value={channel.stats.mean} decimals={channel.decimals} unit={unit} />
              <Stat label="median" value={channel.stats.median} decimals={channel.decimals} unit={unit} />
              <Stat label="max" value={channel.stats.max} decimals={channel.decimals} unit={unit} />
              <Stat label="std dev" value={channel.stats.stdev} decimals={channel.decimals} unit={unit} />
              <Stat label="p95" value={channel.stats.p95} decimals={channel.decimals} unit={unit} />
              <Stat label="samples" value={channel.sample_count} decimals={0} unit="" />
              <Stat label="sensor age" value={null} decimals={0} unit="" extra={relativeTime(overview.latest.received_at)} />
            </div>
          </div>

          <div className="mt-4">
            {error ? (
              <ErrorState title="Chart unavailable" message={error} />
            ) : series ? (
              <TimeSeriesChart
                series={series}
                color={channel.color}
                rangeHours={range.hours}
                height={300}
                decimals={channel.decimals}
              />
            ) : (
              <CardSkeleton />
            )}
          </div>
          {history && !history.sufficient_data ? (
            <InlineNote severity="watch" className="mt-3">
              {history.notes[0] ?? "Insufficient history in this range for trend statistics."}
            </InlineNote>
          ) : null}
        </Card>

        <div className="space-y-4">
          <Card>
            <SectionHeader title="Interpretation" subtitle="What the current value means" className="mb-2" />
            <p className="text-sm text-slate-600 dark:text-slate-300">{sensorSpec?.description}</p>
            <ul className="mt-3 space-y-1.5">
              {bands.map((band) => {
                const active =
                  channel.value !== null &&
                  channel.value <= band.until &&
                  (bands.find((item) => channel.value! <= item.until)?.until === band.until);
                return (
                  <li
                    key={`${band.until}-${band.label}`}
                    className={classNames(
                      "flex items-center justify-between rounded-lg px-2.5 py-1.5 text-xs",
                      active ? "bg-cyan-500/10 font-medium text-cyan-700 dark:text-cyan-300" : "text-slate-500 dark:text-slate-400",
                    )}
                  >
                    <span>≤ {band.until} {unit}</span>
                    <span>{band.label}</span>
                  </li>
                );
              })}
            </ul>
            {sensorSpec?.calibration_notes ? (
              <InlineNote severity="info" className="mt-3">
                {sensorSpec.calibration_notes}
              </InlineNote>
            ) : null}
          </Card>

          <Card>
            <SectionHeader title="Recent baseline" subtitle="Rolling window used by anomaly detection" className="mb-2" />
            {baseline && baseline.samples > 0 ? (
              <dl className="grid grid-cols-3 gap-3 text-xs">
                <div>
                  <dt className="text-slate-400">mean</dt>
                  <dd className="tabular font-medium text-slate-700 dark:text-slate-200">
                    {baseline.mean?.toFixed(channel.decimals) ?? "—"}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-400">robust σ</dt>
                  <dd className="tabular font-medium text-slate-700 dark:text-slate-200">
                    {baseline.sigma?.toFixed(2) ?? "—"}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-400">samples</dt>
                  <dd className="tabular font-medium text-slate-700 dark:text-slate-200">{baseline.samples}</dd>
                </div>
              </dl>
            ) : (
              <p className="text-xs text-slate-500 dark:text-slate-400">
                The anomaly baseline needs at least 12 samples for this sensor before it can report deviations.
              </p>
            )}
          </Card>

          <Card>
            <SectionHeader title="Anomalies" subtitle="Deviations from the recent baseline" className="mb-2" />
            <AnomalyList anomalies={anomalies} />
          </Card>
        </div>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  decimals,
  unit,
  extra,
}: {
  label: string;
  value: number | null;
  decimals: number;
  unit: string;
  extra?: string;
}) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-slate-400">{label}</div>
      <div className="tabular font-medium text-slate-700 dark:text-slate-200">
        {extra ?? (value !== null ? `${value.toFixed(decimals)} ${unit}`.trim() : "—")}
      </div>
    </div>
  );
}
