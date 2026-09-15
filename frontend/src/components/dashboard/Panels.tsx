/**
 * Dashboard panels: Risk breakdown, anomaly lists, observation feeds.
 * Re-styled to match the premium design system.
 */

import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  AlertTriangle,
  BadgeCheck,
  BellRing,
  CheckCircle2,
  Info,
  Lightbulb,
  ShieldAlert,
  Waves,
} from "lucide-react";
import type { Alert, Anomaly, Observation, RiskAssessment, SensorHealth } from "../../types";
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
    <div className="space-y-6">
      <div className="flex flex-wrap gap-2">
        <Chip severity={risk.level >= 4 ? "critical" : risk.level === 3 ? "watch" : "good"}>
          {risk.label} · {risk.score.toFixed(0)}/100
        </Chip>
        <Chip severity="info">model v{risk.model_version}</Chip>
        <Chip severity={risk.data_coverage >= 0.99 ? "good" : risk.data_coverage >= 0.6 ? "watch" : "warning"}>
          data coverage {Math.round(risk.data_coverage * 100)}%
        </Chip>
      </div>

      {risk.reasons.length > 0 && (
        <div className="p-4 rounded-xl bg-orange-50 dark:bg-orange-500/10 border border-orange-100 dark:border-orange-500/20">
          <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-orange-600 dark:text-orange-400">
            Active Risk Drivers
          </p>
          <ul className="space-y-2">
            {risk.reasons.map((reason) => (
              <li key={reason} className="flex items-start gap-2 text-sm text-orange-800 dark:text-orange-200">
                <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                {reason}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <p className="mb-3 text-[10px] font-bold uppercase tracking-widest text-slate-400">
          Factor Contributions
        </p>
        <div className="space-y-4">
          {increasing.length ? (
            increasing.map((item) => (
              <div key={item.key} className="space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold text-slate-700 dark:text-slate-200">{item.label}</span>
                  <span className="tabular text-slate-500 dark:text-slate-400">
                    <span className="font-bold text-slate-700 dark:text-slate-300">+{item.points.toFixed(1)}</span> / {item.max_points.toFixed(0)}
                  </span>
                </div>
                <ProgressBar
                  value={item.points}
                  max={item.max_points}
                  color={riskColor(risk.level)}
                  className="bg-slate-100 dark:bg-surface-800 h-2 shadow-inner"
                />
              </div>
            ))
          ) : (
            <div className="p-4 rounded-xl border border-dashed border-emerald-200 dark:border-emerald-500/20 bg-emerald-50/50 dark:bg-emerald-500/5">
              <p className="text-sm font-medium text-emerald-600 dark:text-emerald-400 text-center">
                All factors within safe operational bounds.
              </p>
            </div>
          )}
        </div>
      </div>

      {reducing.length > 0 && (
        <div>
          <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-slate-400">
            Protective Factors
          </p>
          <div className="flex flex-wrap gap-2">
            {reducing.map((item) => (
              <span
                key={item.key}
                className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-500/20 bg-emerald-500/5 px-2.5 py-1 text-[11px] font-medium text-emerald-700 dark:text-emerald-400"
              >
                <BadgeCheck size={12} />
                {item.label}
              </span>
            ))}
          </div>
        </div>
      )}

      {!compact && risk.recommended_actions.length > 0 && (
        <div className="pt-4 border-t border-slate-200/50 dark:border-white/5">
          <p className="mb-3 text-[10px] font-bold uppercase tracking-widest text-cyan-600 dark:text-cyan-400">
            Recommended Action
          </p>
          <ul className="space-y-2">
            {risk.recommended_actions.map((action) => (
              <li key={action} className="flex items-start gap-2.5 text-sm text-slate-700 dark:text-slate-200">
                <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-cyan-500" />
                <span className="leading-relaxed">{action}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function AnomalyList({ anomalies, className }: { anomalies: Anomaly[]; className?: string }) {
  if (!anomalies.length) {
    return (
      <EmptyState
        icon={<Activity size={24} className="text-slate-300 dark:text-slate-600" />}
        title="No Anomalies"
        message="System operating within expected baseline parameters."
      />
    );
  }
  return (
    <ul className={classNames("space-y-3", className)}>
      <AnimatePresence initial={false}>
        {anomalies.map((anomaly) => (
          <motion.li
            key={`${anomaly.sensor}-${anomaly.kind}-${anomaly.detected_at}`}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, height: 0 }}
            className={classNames(
              "rounded-xl border p-4 transition-all",
              SEVERITY_CLASSES[anomaly.severity === "high" ? "critical" : anomaly.severity === "medium" ? "warning" : "watch"]
            )}
          >
            <div className="flex items-start justify-between gap-2 mb-2">
              <span className="text-sm font-bold tracking-wide">{anomaly.label}</span>
              <span className="px-2 py-0.5 rounded text-[10px] uppercase font-bold tracking-widest bg-current opacity-75 text-white mix-blend-hard-light">
                {anomaly.severity}
              </span>
            </div>
            <p className="text-sm font-medium opacity-90 mb-3">{anomaly.message}</p>
            <div className="flex flex-wrap gap-2 text-[10px] uppercase tracking-widest opacity-70">
              <span className="font-semibold">{anomaly.kind.replace("_", " ")}</span>
              <span>•</span>
              <span className="tabular">Base: {anomaly.expected_value?.toFixed(1) ?? "—"} {anomaly.unit}</span>
              {anomaly.z_score !== null && (
                <><span>•</span><span className="tabular">Z: {anomaly.z_score.toFixed(2)}</span></>
              )}
            </div>
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
        icon={<Waves size={24} className="text-slate-300 dark:text-slate-600" />}
        title="No Insights"
        message="Gathering data to build statistical observations."
      />
    );
  }
  return (
    <ul className="space-y-3">
      {observations.map((obs) => {
        const Icon = IMPORTANCE_ICON[obs.importance] ?? Info;
        return (
          <li key={obs.id} className="flex items-start gap-3 p-3 rounded-xl hover:bg-slate-50 dark:hover:bg-surface-900/40 transition-colors">
            <span className={classNames(
              "mt-0.5 w-6 h-6 shrink-0 flex items-center justify-center rounded-lg border",
              SEVERITY_CLASSES[obs.importance === "warning" ? "warning" : obs.importance === "critical" ? "critical" : "info"]
            )}>
              <Icon size={12} />
            </span>
            <p className="text-sm leading-relaxed text-slate-700 dark:text-slate-300 font-medium">{obs.text}</p>
          </li>
        );
      })}
    </ul>
  );
}

export function AlertFeed({ alerts, limit = 6 }: { alerts: Alert[]; limit?: number }) {
  if (!alerts.length) return <EmptyState icon={<BellRing size={20} />} title="All Clear" message="No active alerts." />;
  return (
    <ul className="space-y-2">
      {alerts.slice(0, limit).map((alert) => (
        <li key={`${alert.id}-${alert.last_seen_at}`} className={classNames("rounded-xl border px-4 py-3 transition-colors", ALERT_CLASSES[String(alert.severity)] ?? ALERT_CLASSES.info)}>
          <div className="flex items-center justify-between gap-2 mb-1.5">
            <span className="flex items-center gap-2 text-sm font-bold text-slate-800 dark:text-slate-100">
              <StatusDot severity={alert.severity === "critical" ? "critical" : alert.severity === "warning" ? "warning" : "info"} pulse={alert.severity === "critical"} />
              {alert.title}
            </span>
            <span className="text-[10px] font-semibold uppercase tracking-widest opacity-60">
              {relativeTime(alert.last_seen_at ?? alert.triggered_at)}
            </span>
          </div>
          <p className="text-xs text-slate-600 dark:text-slate-300 opacity-90 leading-relaxed mb-2">{alert.message}</p>
          {alert.recommended_action && <p className="text-[11px] font-medium opacity-75">Tip: {alert.recommended_action}</p>}
        </li>
      ))}
    </ul>
  );
}

export function SensorHealthTable({ sensors }: { sensors: SensorHealth[] }) {
  if (!sensors.length) return <EmptyState icon={<Activity size={20} />} title="Status Unknown" message="Waiting for sensor telemetry." />;
  
  const statusLabel: Record<string, { label: string; severity: string; dot: string }> = {
    ok: { label: "Online", severity: "good", dot: "bg-emerald-500" },
    degraded: { label: "Degraded", severity: "watch", dot: "bg-amber-500" },
    stale: { label: "Stale", severity: "warning", dot: "bg-amber-500" },
    suspect: { label: "Suspect", severity: "warning", dot: "bg-amber-500" },
    failed: { label: "Failed", severity: "critical", dot: "bg-rose-500" },
    unknown: { label: "Unknown", severity: "unknown", dot: "bg-slate-400" },
  };

  return (
    <ul className="divide-y divide-slate-100 dark:divide-white/5">
      {sensors.map((sensor) => {
        const meta = statusLabel[sensor.status] ?? statusLabel.unknown;
        const healthy = sensor.status === "ok";
        const explained = ["degraded", "suspect", "failed"].includes(sensor.status);
        
        return (
          <li key={sensor.key} className="py-3 flex items-center gap-4 hover:bg-slate-50/50 dark:hover:bg-white/[0.02] px-2 rounded-xl transition-colors">
            <span className={classNames("w-2 h-2 rounded-full shrink-0", meta.dot)} />
            
            <div className="flex-1 min-w-0">
              <span className="block font-semibold text-sm text-slate-800 dark:text-slate-200">{sensor.label}</span>
              {(!healthy && explained) && <span className="block text-xs text-slate-500 truncate mt-0.5">{sensor.message}</span>}
            </div>

            <div className="hidden sm:block text-right">
              <div className="tabular text-sm font-medium text-slate-700 dark:text-slate-300">
                {sensor.last_value !== null ? sensor.last_value.toFixed(1) : "—"}
              </div>
              <div className="text-[10px] text-slate-400 font-medium">
                {sensor.last_seen_at ? secondsAgo(sensor.age_seconds) + 's ago' : "never"}
              </div>
            </div>

            <div className="hidden lg:flex w-24 flex-col gap-1 items-end">
              <span className="text-[10px] font-medium text-slate-400">Coverage</span>
              <div className="w-full h-1.5 bg-slate-100 dark:bg-surface-800 rounded-full overflow-hidden">
                <div className={classNames("h-full", meta.dot)} style={{ width: `${Math.max(4, Math.min(100, sensor.coverage_pct ?? 0))}%` }} />
              </div>
            </div>

            <Chip severity={meta.severity} className={classNames("w-20 justify-center", healthy ? "opacity-70" : "")}>{meta.label}</Chip>
          </li>
        );
      })}
    </ul>
  );
}

export function TrendStrip({ items }: { items: { label: string; value: number | null; unit: string; trend: string; change: number | null }[] }) {
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
      {items.map((item) => (
        <div key={item.label} className="panel-muted px-4 py-3 rounded-xl">
          <div className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-1 truncate">{item.label}</div>
          <div className="tabular text-lg font-bold text-slate-800 dark:text-slate-100 mb-1">
            {item.value !== null ? item.value.toFixed(1) : "—"} <span className="text-xs font-medium text-slate-400">{item.unit}</span>
          </div>
          <div className="text-[10px] font-medium text-slate-500 flex items-center gap-1">
            {trendGlyph(item.trend)} {item.change !== null ? item.change.toFixed(2) : "—"}
          </div>
        </div>
      ))}
    </div>
  );
}
