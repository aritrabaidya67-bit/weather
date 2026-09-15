/**
 * Attention strip — everything that needs a human, one line each.
 *
 * Severity is carried by a dot (shape+colour), the label, and ordering, so a
 * critical item reads as critical without a wall of warning text.
 */

import { AlertTriangle, ArrowRight, CheckCircle2, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import type { Alert, Anomaly } from "../../types";
import { ALERT_CLASSES, classNames, relativeTime } from "../../utils/format";
import { SectionHeaderPill } from "./SectionHeaderPill";

export function AttentionStrip({
  alerts,
  anomalies,
}: {
  alerts: Alert[];
  anomalies: Anomaly[];
}) {
  const rows: { key: string; severity: string; title: string; meta: string; to: string }[] = [
    ...alerts.slice(0, 3).map((alert) => ({
      key: `alert-${alert.id ?? alert.fingerprint ?? alert.title}`,
      severity: alert.severity === "critical" ? "critical" : alert.severity === "warning" ? "warning" : "info",
      title: alert.title,
      meta: alert.sensor ? `${alert.sensor} · ${relativeTime(alert.triggered_at)}` : relativeTime(alert.triggered_at),
      to: "/alerts",
    })),
    ...anomalies.slice(0, 2).map((anomaly) => ({
      key: `anomaly-${anomaly.sensor}-${anomaly.detected_at}-${anomaly.kind}`,
      severity: anomaly.severity === "high" ? "critical" : anomaly.severity === "medium" ? "warning" : "info",
      title: `${anomaly.label} ${anomaly.kind.replace(/_/g, " ")}`,
      meta: anomaly.direction === "above" ? "above baseline" : "below baseline",
      to: "/sensors",
    })),
  ];

  if (!rows.length) {
    return (
      <section className="panel flex items-center gap-2.5 p-4 text-sm text-slate-500 dark:text-slate-400">
        <CheckCircle2 size={16} className="text-emerald-500" aria-hidden />
        <span className="font-medium text-slate-700 dark:text-slate-200">Nothing needs attention</span>
        <span className="hidden text-[11px] sm:inline">no active alerts or anomalies</span>
      </section>
    );
  }

  return (
    <section className="panel p-4">
      <SectionHeaderPill
        icon={<AlertTriangle size={14} />}
        title="Needs attention"
        meta={`${rows.length} item${rows.length === 1 ? "" : "s"}`}
        action={
          <Link
            to="/alerts"
            className="inline-flex items-center gap-1 text-[11px] font-medium text-cyan-600 hover:underline dark:text-cyan-300"
          >
            all alerts <ArrowRight size={11} aria-hidden />
          </Link>
        }
      />
      <ul className="mt-3 space-y-1.5">
        {rows.map((row) => (
          <li key={row.key}>
            <Link
              to={row.to}
              className={classNames(
                "flex items-center gap-2.5 rounded-xl border px-3 py-2 transition-colors",
                ALERT_CLASSES[row.severity] ?? ALERT_CLASSES.info,
              )}
            >
              <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-current" aria-hidden />
              <span className="min-w-0 flex-1">
                <span className="flex items-baseline gap-2">
                  <span className="truncate text-[13px] font-medium">{row.title}</span>
                  <span className="ml-auto shrink-0 text-[10px] opacity-70">{row.meta}</span>
                </span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
      {anomalies.length > 0 ? (
        <p className="mt-2 flex items-center gap-1 text-[11px] text-slate-400">
          <Sparkles size={11} aria-hidden /> anomalies are flagged against each sensor's rolling baseline
        </p>
      ) : null}
    </section>
  );
}
