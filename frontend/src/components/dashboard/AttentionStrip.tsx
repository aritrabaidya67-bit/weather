/**
 * Attention strip — prioritizing events clearly.
 * 
 * Re-styled for premium aesthetics and clarity.
 */

import { motion } from "framer-motion";
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
      <motion.section 
        className="panel-muted flex items-center justify-between p-4"
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div className="flex items-center gap-3">
          <div className="grid h-8 w-8 place-items-center rounded-full bg-emerald-500/10 text-emerald-500 dark:bg-emerald-400/10 dark:text-emerald-400">
            <CheckCircle2 size={16} strokeWidth={2.5} />
          </div>
          <div>
            <p className="text-sm font-semibold tracking-wide text-slate-800 dark:text-slate-200">Everything looks good</p>
            <p className="text-xs text-slate-500 dark:text-slate-400">No active alerts or anomalies detected.</p>
          </div>
        </div>
      </motion.section>
    );
  }

  return (
    <motion.section 
      className="panel p-5"
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
    >
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
        <SectionHeaderPill
          icon={<AlertTriangle size={14} strokeWidth={2.5} />}
          title="Needs Attention"
          meta={`${rows.length} item${rows.length === 1 ? "" : "s"}`}
        />
        <Link
          to="/alerts"
          className="inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-widest text-rose-600 transition-colors hover:text-rose-700 dark:text-rose-400 dark:hover:text-rose-300"
        >
          View All <ArrowRight size={12} strokeWidth={2.5} />
        </Link>
      </div>

      <ul className="space-y-2">
        {rows.map((row, index) => (
          <motion.li 
            key={row.key}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: index * 0.1 }}
          >
            <Link
              to={row.to}
              className={classNames(
                "group flex items-center gap-3 rounded-2xl border px-4 py-3 transition-all hover:-translate-y-0.5 hover:shadow-md",
                ALERT_CLASSES[row.severity] ?? ALERT_CLASSES.info
              )}
            >
              <div className="flex h-2 w-2 shrink-0 items-center justify-center rounded-full bg-current">
                {row.severity === 'critical' && (
                  <span className="absolute h-4 w-4 animate-ping rounded-full bg-current opacity-40" />
                )}
              </div>
              <div className="flex min-w-0 flex-1 flex-col sm:flex-row sm:items-baseline sm:justify-between gap-1 sm:gap-4">
                <span className="truncate text-sm font-bold tracking-wide">{row.title}</span>
                <span className="shrink-0 text-[11px] font-medium opacity-70 uppercase tracking-wider">{row.meta}</span>
              </div>
            </Link>
          </motion.li>
        ))}
      </ul>
      
      {anomalies.length > 0 && (
        <p className="mt-3 flex items-center justify-center sm:justify-start gap-1.5 text-[11px] font-medium text-slate-400">
          <Sparkles size={12} /> Anomalies flagged against rolling baselines
        </p>
      )}
    </motion.section>
  );
}
