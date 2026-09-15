/**
 * Alerts & Events Center.
 * Reimagined as an actionable timeline rather than a sterile log table.
 */

import { motion, AnimatePresence } from "framer-motion";
import { BellRing, Check, ShieldCheck, ShieldAlert, AlertTriangle, Info, ShieldX } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { CardSkeleton, Chip, SectionHeaderPill } from "../components/common/Ui";
import { api } from "../services/api";
import { usePlatform } from "../state/PlatformContext";
import type { Alert, AlertList } from "../types";
import { classNames, relativeTime } from "../utils/format";

export default function AlertsPage() {
  const { meta, refresh } = usePlatform();
  const [filter, setFilter] = useState<{ activeOnly: boolean; severity: string | null }>({ activeOnly: false, severity: null });
  const [data, setData] = useState<AlertList | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    void api.alerts({ active_only: filter.activeOnly, severity: filter.severity ?? undefined, limit: 100 })
      .then(setData)
      .catch(() => undefined)
      .finally(() => setLoading(false));
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  const act = async (alert: Alert, action: "acknowledge" | "resolve") => {
    if (alert.id === null) return;
    try {
      if (action === "acknowledge") await api.acknowledgeAlert(alert.id);
      else await api.resolveAlert(alert.id);
      load();
      await refresh({ silent: true });
    } catch {}
  };

  const getSeverityStyles = (severity: string, active: boolean) => {
    if (!active) return "bg-slate-50 dark:bg-surface-900/40 border-slate-200/50 dark:border-white/5 opacity-70";
    switch (severity) {
      case "critical": return "bg-rose-50 border-rose-200 dark:bg-rose-500/10 dark:border-rose-500/20";
      case "warning": return "bg-amber-50 border-amber-200 dark:bg-amber-500/10 dark:border-amber-500/20";
      default: return "bg-sky-50 border-sky-200 dark:bg-sky-500/10 dark:border-sky-500/20";
    }
  };

  const getSeverityIcon = (severity: string) => {
    switch (severity) {
      case "critical": return <ShieldX className="text-rose-500" />;
      case "warning": return <AlertTriangle className="text-amber-500" />;
      default: return <Info className="text-sky-500" />;
    }
  };

  return (
    <div className="space-y-6 animate-float-in">
      {/* Header Area */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 panel p-5">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-2">
            <BellRing size={20} className="text-cyan-500" />
            Event Center
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            {data ? `${data.active_count} active incidents requiring attention.` : 'Loading system events...'}
          </p>
        </div>
        
        <div className="flex items-center gap-2">
          <button
            onClick={() => setFilter(c => ({ ...c, activeOnly: !c.activeOnly }))}
            className={classNames(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold transition-all",
              filter.activeOnly 
                ? "bg-slate-900 text-white shadow-sm dark:bg-white dark:text-slate-900" 
                : "bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-surface-800 dark:text-slate-400"
            )}
          >
            <ShieldCheck size={14} /> Active Only
          </button>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Main Event Timeline */}
        <div className="lg:col-span-2 space-y-4">
          <SectionHeaderPill icon={<BellRing size={16} />} title="Event Timeline" className="mb-2" />
          
          {loading && !data ? (
            <CardSkeleton className="h-[400px]" />
          ) : !data?.alerts.length ? (
            <div className="panel min-h-[400px] flex flex-col items-center justify-center p-8 text-center border-dashed border-2">
              <div className="w-16 h-16 bg-emerald-50 dark:bg-emerald-500/10 rounded-full flex items-center justify-center mb-4 text-emerald-500">
                <ShieldCheck size={32} />
              </div>
              <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-2">System Clear</h3>
              <p className="text-slate-500 text-sm max-w-sm">No events match your current filters. Everything is operating normally.</p>
            </div>
          ) : (
            <div className="space-y-4">
              <AnimatePresence>
                {data.alerts.map((alert, index) => (
                  <motion.div
                    key={alert.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ delay: index * 0.05 }}
                    className={classNames(
                      "panel p-5 relative overflow-hidden transition-all hover:shadow-md",
                      getSeverityStyles(String(alert.severity), Boolean(alert.is_active))
                    )}
                  >
                    {/* Active Ping Indicator */}
                    {alert.is_active && alert.severity === 'critical' && (
                      <div className="absolute top-5 right-5 w-3 h-3">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-3 w-3 bg-rose-500"></span>
                      </div>
                    )}

                    <div className="flex gap-4">
                      <div className="mt-1">
                        {getSeverityIcon(String(alert.severity))}
                      </div>
                      <div className="flex-1">
                        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-2 mb-1">
                          <h3 className={classNames(
                            "text-base font-bold",
                            !alert.is_active ? "text-slate-600 dark:text-slate-400" : "text-slate-900 dark:text-white"
                          )}>
                            {alert.title}
                          </h3>
                          <span className="text-xs font-medium text-slate-500 uppercase tracking-widest whitespace-nowrap">
                            {relativeTime(alert.last_seen_at ?? alert.triggered_at)}
                          </span>
                        </div>
                        
                        <p className={classNames(
                          "text-sm mb-4 leading-relaxed",
                          !alert.is_active ? "text-slate-500" : "text-slate-700 dark:text-slate-300"
                        )}>
                          {alert.message}
                        </p>

                        <div className="flex flex-wrap items-center gap-2 text-xs mb-4">
                          <Chip severity={alert.is_active ? "warning" : "good"}>
                            {alert.is_active ? "Active" : "Resolved"}
                          </Chip>
                          <span className="px-2 py-1 bg-white/50 dark:bg-black/20 rounded-md font-medium text-slate-600 dark:text-slate-400">
                            {alert.category.replace(/_/g, " ")}
                          </span>
                          {alert.metric_value !== null && (
                            <span className="px-2 py-1 bg-white/50 dark:bg-black/20 rounded-md font-medium text-slate-600 dark:text-slate-400 font-mono">
                              Val: {Number(alert.metric_value).toFixed(2)}
                            </span>
                          )}
                        </div>

                        {alert.is_active && (
                          <div className="flex items-center gap-3 pt-4 border-t border-slate-200/50 dark:border-white/10 mt-4">
                            {!alert.acknowledged_at && (
                              <button
                                onClick={() => void act(alert, "acknowledge")}
                                className="flex items-center gap-1.5 px-4 py-2 bg-white dark:bg-surface-800 rounded-lg text-sm font-semibold text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-surface-700 transition-colors shadow-sm"
                              >
                                <Check size={16} className="text-cyan-500" /> Acknowledge
                              </button>
                            )}
                            <button
                              onClick={() => void act(alert, "resolve")}
                              className="flex items-center gap-1.5 px-4 py-2 bg-slate-900 dark:bg-white rounded-lg text-sm font-semibold text-white dark:text-slate-900 hover:bg-slate-800 dark:hover:bg-slate-200 transition-colors shadow-sm"
                            >
                              <ShieldCheck size={16} /> Mark Resolved
                            </button>
                            
                            {alert.recommended_action && (
                              <span className="ml-auto text-xs font-medium text-slate-500 italic hidden sm:block">
                                Tip: {alert.recommended_action}
                              </span>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          )}
        </div>

        {/* Sidebar: System Rules */}
        <div className="space-y-4">
          <SectionHeaderPill icon={<ShieldAlert size={16} />} title="Active Monitored Rules" className="mb-2" />
          <div className="panel p-5 bg-slate-50/50 dark:bg-surface-900/30">
            <ul className="space-y-4">
              {(meta?.alert_rules ?? []).map((rule) => (
                <li key={rule.id} className="border-b border-slate-200/50 dark:border-white/5 last:border-0 pb-4 last:pb-0">
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <span className="text-sm font-bold text-slate-800 dark:text-slate-200">{rule.title}</span>
                    <span className={classNames(
                      "w-2 h-2 rounded-full",
                      rule.severity === 'critical' ? 'bg-rose-500' : rule.severity === 'warning' ? 'bg-amber-500' : 'bg-sky-500'
                    )} />
                  </div>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mb-2 leading-relaxed">{rule.description}</p>
                  <code className="text-[10px] font-mono text-cyan-600 dark:text-cyan-400 bg-cyan-50 dark:bg-cyan-500/10 px-2 py-1 rounded block truncate">
                    {rule.condition}
                  </code>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
