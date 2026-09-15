/** Dashboard panels: explainable risk breakdown, alert feed, observations, device and sensor health. */

import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  AlertTriangle,
  Antenna,
  BadgeCheck,
  BellRing,
  CheckCircle2,
  Cpu,
  Gauge,
  Info,
  Lightbulb,
  ShieldAlert,
  Waves,
  Wifi,
} from "lucide-react";
import { Link } from "react-router-dom";
import type { Alert, Anomaly, DeviceStatus, Observation, RiskAssessment, SensorHealth } from "../../types";
import {
  ALERT_CLASSES,
  SEVERITY_CLASSES,
  classNames,
  relativeTime,
  riskColor,
  secondsAgo,
  trendGlyph,
} from "../../utils/format";
import { Chip, EmptyState, ProgressBar, StatusDot } from "../common/Ui";

const IMPORTANCE_ICON: Record<string, typeof Info> = {
  critical: ShieldAlert,
  warning: AlertTriangle,
  notice: Lightbulb,
  info: Info,
};

export function RiskBreakdown({ risk, compact = false }: { risk: RiskAssessment; compact?: boolean }) {
  const increasing = risk.contributions.filter((item) => item.points > 0.5);
  const reducing = risk.contributions.filter((item) => item.points <= 0.5);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <Chip severity={risk.level >= 4 ? "critical" : risk.level === 3 ? "watch" : "good"}>
          {risk.label} · {risk.score.toFixed(0)}/100
        </Chip>
        <Chip severity="info">model v{risk.model_version}</Chip>
        <Chip severity={risk.data_coverage >= 0.99 ? "good" : risk.data_coverage >= 0.6 ? "watch" : "warning"}>
          data coverage {Math.round(risk.data_coverage * 100)}%
        </Chip>
      </div>

      {risk.reasons.length ? (
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Factors increasing risk
          </p>
          <ul className="space-y-1.5">
            {risk.reasons.map((reason) => (
              <li key={reason} className="flex items-start gap-2 text-sm text-slate-700 dark:text-slate-200">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-orange-500" />
                {reason}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Score contribution
        </p>
        <div className="space-y-2">
          {increasing.length ? (
            increasing.map((item) => (
              <div key={item.key} className="space-y-1">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-medium text-slate-700 dark:text-slate-200">{item.label}</span>
                  <span className="tabular text-slate-500 dark:text-slate-400">
                    +{item.points.toFixed(1)} / {item.max_points.toFixed(0)}
                    {item.reading !== null ? (
                      <span className="ml-2 text-slate-400">
                        ({item.reading.toFixed(1)} {item.unit ?? ""})
                      </span>
                    ) : null}
                  </span>
                </div>
                <ProgressBar
                  value={item.points}
                  max={item.max_points}
                  color={riskColor(risk.level)}
                  className="bg-slate-200/60 dark:bg-slate-800"
                />
              </div>
            ))
          ) : (
            <p className="text-sm text-emerald-600 dark:text-emerald-400">
              No factor is contributing risk right now - everything is inside its comfort band.
            </p>
          )}
        </div>
      </div>

      {reducing.length ? (
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Factors reducing risk
          </p>
          <ul className="flex flex-wrap gap-1.5">
            {reducing.map((item) => (
              <li
                key={item.key}
                className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/5 px-2.5 py-0.5 text-[11px] text-emerald-700 dark:text-emerald-300"
              >
                <BadgeCheck size={11} />
                {item.label}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {!compact && risk.recommended_actions.length ? (
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Recommended actions
          </p>
          <ul className="space-y-1.5">
            {risk.recommended_actions.map((action) => (
              <li key={action} className="flex items-start gap-2 text-sm text-slate-700 dark:text-slate-200">
                <CheckCircle2 size={14} className="mt-0.5 shrink-0 text-cyan-500" />
                {action}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

export function AnomalyList({ anomalies, className }: { anomalies: Anomaly[]; className?: string }) {
  if (!anomalies.length) {
    return (
      <EmptyState
        icon={<Activity size={18} />}
        title="No anomalies detected"
        message="Detections require a rolling baseline (at least 12 samples per sensor). Nothing currently deviates significantly from its recent baseline."
      />
    );
  }
  return (
    <ul className={classNames("space-y-2", className)}>
      <AnimatePresence initial={false}>
        {anomalies.map((anomaly) => (
          <motion.li
            key={`${anomaly.sensor}-${anomaly.kind}-${anomaly.detected_at}`}
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0 }}
            className={classNames(
              "rounded-xl border px-3 py-2",
              SEVERITY_CLASSES[anomaly.severity === "high" ? "critical" : anomaly.severity === "medium" ? "warning" : "watch"],
            )}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-semibold">{anomaly.label}</span>
              <span className="text-[10px] uppercase tracking-wide opacity-80">
                {anomaly.severity} · {anomaly.kind.replace("_", " ")}
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-700 dark:text-slate-200">{anomaly.message}</p>
            <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
              baseline {anomaly.expected_value?.toFixed(1) ?? "—"} {anomaly.unit}
              {anomaly.z_score !== null ? ` · z = ${anomaly.z_score.toFixed(2)}` : ""} ·{" "}
              {relativeTime(anomaly.detected_at)}
            </p>
          </motion.li>
        ))}
      </AnimatePresence>
    </ul>
  );
}

export function ObservationList({ observations }: { observations: Observation[] }) {
  if (!observations.length) {
    return (
      <EmptyState
        icon={<Waves size={18} />}
        title="No observations yet"
        message="Insights are only generated when the data supports them. Collect a few more readings and the analysis will appear here."
      />
    );
  }
  return (
    <ul className="space-y-2.5">
      {observations.map((observation) => {
        const Icon = IMPORTANCE_ICON[observation.importance] ?? Info;
        return (
          <li key={observation.id} className="flex items-start gap-2.5">
            <span
              className={classNames(
                "mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-md border",
                SEVERITY_CLASSES[observation.importance === "warning" ? "warning" : observation.importance === "critical" ? "critical" : "info"],
              )}
            >
              <Icon size={12} />
            </span>
            <p className="text-sm leading-relaxed text-slate-700 dark:text-slate-200">{observation.text}</p>
          </li>
        );
      })}
    </ul>
  );
}

export function AlertFeed({ alerts, limit = 6 }: { alerts: Alert[]; limit?: number }) {
  if (!alerts.length) {
    return (
      <EmptyState
        icon={<BellRing size={18} />}
        title="No active alerts"
        message="All monitored conditions are inside their configured thresholds."
      />
    );
  }
  return (
    <ul className="space-y-2">
      {alerts.slice(0, limit).map((alert) => (
        <li
          key={`${alert.id}-${alert.last_seen_at}`}
          className={classNames("rounded-xl border px-3 py-2", ALERT_CLASSES[String(alert.severity)] ?? ALERT_CLASSES.info)}
        >
          <div className="flex items-center justify-between gap-2">
            <span className="flex items-center gap-1.5 text-xs font-semibold text-slate-800 dark:text-slate-100">
              <StatusDot severity={alert.severity === "critical" ? "critical" : alert.severity === "warning" ? "warning" : "info"} pulse={alert.severity === "critical"} />
              {alert.title}
            </span>
            <span className="text-[10px] uppercase tracking-wide text-slate-500 dark:text-slate-400">
              {alert.severity} · {relativeTime(alert.last_seen_at ?? alert.triggered_at)}
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">{alert.message}</p>
          {alert.recommended_action ? (
            <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">→ {alert.recommended_action}</p>
          ) : null}
          {alert.occurrence_count > 1 ? (
            <p className="mt-1 text-[10px] text-slate-400">seen {alert.occurrence_count}×</p>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

export function DeviceStatusCard({ device }: { device: DeviceStatus | null }) {
  if (!device) {
    return (
      <EmptyState
        icon={<Cpu size={18} />}
        title="Arduino offline"
        message="Waiting for the Arduino UNO R4 Wi-Fi to send sensor data. This is expected until the firmware is flashed and the node reaches this backend."
      />
    );
  }
  const rows: { label: string; value: string; icon: typeof Wifi }[] = [
    { label: "State", value: device.online ? "Online" : device.status.replace("_", " "), icon: Activity },
    { label: "Last payload", value: relativeTime(device.last_payload_at), icon: Activity },
    { label: "Source", value: device.source, icon: Cpu },
    { label: "Firmware", value: device.firmware_version ?? "not reported", icon: Cpu },
    { label: "IP address", value: device.ip_address ?? "not reported", icon: Antenna },
    {
      label: "Wi-Fi signal",
      value: device.rssi !== null ? `${device.rssi} dBm (${device.rssi_quality})` : "not reported",
      icon: Wifi,
    },
    {
      label: "Transmit interval",
      value: `${device.transmission_interval_seconds ?? device.expected_interval_seconds ?? 15} s`,
      icon: Gauge,
    },
    { label: "Uptime", value: device.uptime_human ?? "not reported", icon: Activity },
  ];

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <StatusDot severity={device.online ? "good" : "critical"} pulse={device.online} />
        <span className="text-sm font-medium text-slate-800 dark:text-slate-100">
          {device.device_id}
        </span>
        <Chip severity={device.online ? "good" : "critical"}>{device.online ? "online" : "offline"}</Chip>
      </div>
      <p className="text-xs text-slate-500 dark:text-slate-400">{device.status_message}</p>
      <dl className="grid grid-cols-2 gap-x-3 gap-y-2">
        {rows.map((row) => (
          <div key={row.label} className="flex items-start gap-2">
            <row.icon size={13} className="mt-0.5 text-slate-400" />
            <div className="min-w-0">
              <dt className="text-[10px] uppercase tracking-wide text-slate-400">{row.label}</dt>
              <dd className="tabular truncate text-xs font-medium text-slate-700 dark:text-slate-200">{row.value}</dd>
            </div>
          </div>
        ))}
      </dl>
      {device.notes.length ? (
        <ul className="space-y-1">
          {device.notes.map((note) => (
            <li key={note} className="text-[11px] text-amber-600 dark:text-amber-400">
              {note}
            </li>
          ))}
        </ul>
      ) : null}
      <Link
        to="/device"
        className="inline-flex items-center gap-1 text-xs font-medium text-cyan-600 hover:underline dark:text-cyan-400"
      >
        Hardware details →
      </Link>
    </div>
  );
}

export function SensorHealthTable({ sensors }: { sensors: SensorHealth[] }) {
  if (!sensors.length) {
    return (
      <EmptyState
        icon={<Activity size={18} />}
        title="Sensor health unknown"
        message="Health is evaluated from the reporting rate, staleness and stuck-value detection once readings arrive."
      />
    );
  }
  const statusLabel: Record<string, { label: string; severity: string }> = {
    ok: { label: "healthy", severity: "good" },
    degraded: { label: "degraded", severity: "watch" },
    stale: { label: "stale", severity: "warning" },
    suspect: { label: "suspect", severity: "warning" },
    failed: { label: "failed", severity: "critical" },
    unknown: { label: "unknown", severity: "unknown" },
  };
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[520px] text-left text-sm">
        <thead>
          <tr className="text-[11px] uppercase tracking-wide text-slate-400">
            <th className="pb-2 font-medium">Sensor</th>
            <th className="pb-2 font-medium">Status</th>
            <th className="pb-2 font-medium">Last value</th>
            <th className="pb-2 font-medium">Rate</th>
            <th className="pb-2 font-medium">Coverage</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-200/70 dark:divide-slate-800/70">
          {sensors.map((sensor) => {
            const meta = statusLabel[sensor.status] ?? statusLabel.unknown;
            return (
              <tr key={sensor.key}>
                <td className="py-2 pr-3">
                  <div className="font-medium text-slate-700 dark:text-slate-200">{sensor.label}</div>
                  <div className="text-[11px] text-slate-400">{sensor.message}</div>
                </td>
                <td className="py-2 pr-3">
                  <Chip severity={meta.severity}>{meta.label}</Chip>
                </td>
                <td className="tabular py-2 pr-3 text-slate-600 dark:text-slate-300">
                  {sensor.last_value !== null ? sensor.last_value.toFixed(1) : "—"}
                  <span className="ml-1 text-[11px] text-slate-400">
                    {sensor.last_seen_at ? `(${secondsAgo(sensor.age_seconds)} ago)` : ""}
                  </span>
                </td>
                <td className="tabular py-2 pr-3 text-slate-600 dark:text-slate-300">
                  {sensor.observed_rate_per_minute?.toFixed(1) ?? "—"} / {sensor.expected_rate_per_minute?.toFixed(1) ?? "—"} per min
                </td>
                <td className="tabular py-2 text-slate-600 dark:text-slate-300">
                  {sensor.coverage_pct !== null ? `${sensor.coverage_pct.toFixed(0)}%` : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function TrendStrip({
  items,
}: {
  items: { label: string; value: number | null; unit: string; trend: string; change: number | null }[];
}) {
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
      {items.map((item) => (
        <div key={item.label} className="panel-muted px-3 py-2">
          <div className="text-[10px] uppercase tracking-wide text-slate-400">{item.label}</div>
          <div className="tabular text-sm font-semibold text-slate-800 dark:text-slate-100">
            {item.value !== null ? item.value.toFixed(1) : "—"}
            <span className="ml-1 text-[11px] font-normal text-slate-400">{item.unit}</span>
          </div>
          <div className="text-[11px] text-slate-500 dark:text-slate-400">
            {trendGlyph(item.trend)} {item.change !== null ? item.change.toFixed(2) : "—"} over the window
          </div>
        </div>
      ))}
    </div>
  );
}
