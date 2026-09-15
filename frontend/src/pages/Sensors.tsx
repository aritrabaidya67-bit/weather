/** Sensor index: every channel with live value, statistics, trend and health. */

import { Activity, ChevronRight, Gauge } from "lucide-react";
import { Link } from "react-router-dom";
import { Sparkline } from "../components/charts/Sparkline";
import { Chip, DataBadge, EmptyState, SectionHeader, StatusDot } from "../components/common/Ui";
import { Card } from "../components/common/Ui";
import { SensorHealthTable } from "../components/dashboard/Panels";
import { usePlatform } from "../state/PlatformContext";
import { classNames, formatSigned, unitSymbol } from "../utils/format";

export default function Sensors() {
  const { overview, meta } = usePlatform();
  const catalog = meta?.channels ?? [];

  if (!overview?.has_data) {
    return (
      <Card>
        <EmptyState
          icon={<Activity size={20} />}
          title="No sensor data yet"
          message="Sensor detail pages populate as soon as the Arduino node sends its first payload."
        />
      </Card>
    );
  }

  return (
    <div className="space-y-5">
      <SectionHeader
        title="Sensors"
        subtitle="Six physical channels from the DHT12/AM2302, BMP280, MQ-135, rain sensor and LDR."
        icon={<Activity size={16} />}
        action={<DataBadge source={overview.data_source} />}
      />

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {overview.channels.map((channel) => (
          <Link
            key={channel.channel}
            to={`/sensors/${channel.channel}`}
            className="panel group p-4 transition hover:-translate-y-0.5 hover:shadow-md"
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">{channel.label}</p>
                <p className="text-[11px] text-slate-400">{channel.sensor}</p>
              </div>
              <ChevronRight size={16} className="text-slate-300 transition group-hover:text-slate-500 dark:text-slate-600" />
            </div>

            <div className="mt-3 flex items-end justify-between">
              <div>
                <div className="tabular text-2xl font-semibold text-slate-900 dark:text-slate-50">
                  {channel.value !== null ? channel.value.toFixed(channel.decimals) : "—"}
                  <span className="ml-1 text-xs font-normal text-slate-400">{unitSymbol(channel.unit)}</span>
                </div>
                <div className="mt-1 flex items-center gap-2">
                  <Chip severity={channel.severity}>
                    <StatusDot severity={channel.severity} />
                    {channel.status}
                  </Chip>
                  {channel.change !== null ? (
                    <span className="tabular text-[11px] text-slate-500 dark:text-slate-400">
                      {formatSigned(channel.change, channel.decimals, channel.unit)}
                    </span>
                  ) : null}
                </div>
              </div>
              <div className="w-28">
                <Sparkline points={channel.sparkline} color={channel.color} height={42} />
              </div>
            </div>

            <dl className="mt-3 grid grid-cols-3 gap-2 border-t border-slate-200/70 pt-2 text-[11px] text-slate-500 dark:border-slate-800/70 dark:text-slate-400">
              <div>
                <dt className="text-slate-400">min</dt>
                <dd className="tabular font-medium text-slate-700 dark:text-slate-200">
                  {channel.stats.min?.toFixed(channel.decimals) ?? "—"}
                </dd>
              </div>
              <div>
                <dt className="text-slate-400">mean</dt>
                <dd className="tabular font-medium text-slate-700 dark:text-slate-200">
                  {channel.stats.mean?.toFixed(channel.decimals) ?? "—"}
                </dd>
              </div>
              <div>
                <dt className="text-slate-400">max</dt>
                <dd className="tabular font-medium text-slate-700 dark:text-slate-200">
                  {channel.stats.max?.toFixed(channel.decimals) ?? "—"}
                </dd>
              </div>
            </dl>

            <div className="mt-2 flex items-center justify-between text-[11px] text-slate-400">
              <span className="tabular">
                {channel.trend} · {channel.sample_count} samples
              </span>
              {channel.stale ? <Chip severity="warning">stale</Chip> : null}
            </div>
          </Link>
        ))}
      </div>

      <Card>
        <SectionHeader title="Sensor health" subtitle="Reporting rate, coverage and failure detection per sensor" icon={<Gauge size={16} />} className="mb-3" />
        <SensorHealthTable sensors={overview.sensor_health} />
      </Card>

      <Card>
        <SectionHeader
          title="Registry"
          subtitle="Physical ranges, units and calibration notes as configured on the backend."
          className="mb-3"
        />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[680px] text-left text-sm">
            <thead>
              <tr className="text-[11px] uppercase tracking-wide text-slate-400">
                <th className="pb-2 font-medium">Metric</th>
                <th className="pb-2 font-medium">Unit</th>
                <th className="pb-2 font-medium">Physical range</th>
                <th className="pb-2 font-medium">Calibration</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200/70 dark:divide-slate-800/70">
              {(meta?.sensors ?? [])
                .filter((sensor) => catalog.some((channel) => channel.primary === sensor.key || channel.secondary.includes(sensor.key)))
                .map((sensor) => (
                  <tr key={sensor.key}>
                    <td className="py-2 pr-3">
                      <div className="font-medium text-slate-700 dark:text-slate-200">{sensor.label}</div>
                      <div className="text-[11px] text-slate-400">{sensor.description}</div>
                    </td>
                    <td className="py-2 pr-3 text-slate-500 dark:text-slate-400">{unitSymbol(sensor.unit) || "—"}</td>
                    <td className="tabular py-2 pr-3 text-slate-500 dark:text-slate-400">
                      {sensor.minimum ?? "—"} … {sensor.maximum ?? "—"}
                    </td>
                    <td className={classNames("py-2 text-[11px] text-slate-400")}>
                      {sensor.calibration_notes || "—"}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
