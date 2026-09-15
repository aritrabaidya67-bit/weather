/** Alert centre: active and historical alerts with acknowledge/resolve and the rule catalogue. */

import { BellRing, Check, ListChecks, RefreshCw, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Card, CardSkeleton, Chip, DataBadge, EmptyState, ErrorState, SectionHeader } from "../components/common/Ui";
import { api, ApiError } from "../services/api";
import { usePlatform } from "../state/PlatformContext";
import type { Alert, AlertList } from "../types";
import { ALERT_CLASSES, classNames, relativeTime } from "../utils/format";

export default function AlertsPage() {
  const { meta, refresh } = usePlatform();
  const [filter, setFilter] = useState<{ activeOnly: boolean; severity: string | null }>({ activeOnly: false, severity: null });
  const [data, setData] = useState<AlertList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    void api
      .alerts({ active_only: filter.activeOnly, severity: filter.severity ?? undefined, limit: 100 })
      .then(setData)
      .catch((caught) => setError(caught instanceof ApiError ? caught.detail : "Could not load alerts."))
      .finally(() => setLoading(false));
  }, [filter]);

  useEffect(() => {
    load();
  }, [load]);

  const act = async (alert: Alert, action: "acknowledge" | "resolve") => {
    if (alert.id === null) return;
    try {
      if (action === "acknowledge") await api.acknowledgeAlert(alert.id);
      else await api.resolveAlert(alert.id);
      load();
      await refresh({ silent: true });
    } catch {
      /* surfaced by the reload */
    }
  };

  const simulated = Boolean(meta?.simulation_mode);

  return (
    <div className="space-y-5">
      <SectionHeader
        title="Alert centre"
        subtitle="Rule-based alerts with de-duplication, automatic resolution and recommended actions."
        icon={<BellRing size={16} />}
        action={
          <div className="flex flex-wrap items-center gap-2">
            {simulated ? <DataBadge source="simulation" /> : null}
            <button
              type="button"
              onClick={load}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 py-1 text-[11px] text-slate-600 transition hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
            >
              <RefreshCw size={12} />
              Refresh
            </button>
          </div>
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => setFilter((current) => ({ ...current, activeOnly: !current.activeOnly }))}
          className={classNames(
            "rounded-full border px-3 py-1 text-xs font-medium transition",
            filter.activeOnly
              ? "border-transparent bg-slate-900 text-white dark:bg-cyan-500/20 dark:text-cyan-200"
              : "border-slate-200 text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300",
          )}
        >
          <ShieldCheck size={12} className="mr-1 inline" />
          active only
        </button>
        {[null, "info", "warning", "critical"].map((severity) => (
          <button
            key={severity ?? "all"}
            type="button"
            onClick={() => setFilter((current) => ({ ...current, severity }))}
            className={classNames(
              "rounded-full border px-3 py-1 text-xs font-medium capitalize transition",
              filter.severity === severity
                ? "border-transparent bg-slate-900 text-white dark:bg-cyan-500/20 dark:text-cyan-200"
                : "border-slate-200 text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300",
            )}
          >
            {severity ?? "all severities"}
          </button>
        ))}
      </div>

      {error ? <ErrorState message={error} onRetry={load} /> : null}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <Card>
          <SectionHeader
            title={data ? `${data.alerts.length} alerts` : "Alerts"}
            subtitle={data ? `${data.active_count} active · ${data.total_count} total stored` : undefined}
            className="mb-3"
          />
          {loading && !data ? (
            <CardSkeleton />
          ) : !data?.alerts.length ? (
            <EmptyState
              icon={<BellRing size={18} />}
              title="No alerts"
              message="No alert matches the current filter. Alerts appear when risk, air quality, temperature, humidity, pressure, rain, anomalies or sensor health cross their configured thresholds."
            />
          ) : (
            <ul className="space-y-2">
              {data.alerts.map((alert) => (
                <li
                  key={alert.id}
                  className={classNames(
                    "rounded-xl border px-3 py-2.5",
                    alert.is_active ? ALERT_CLASSES[String(alert.severity)] ?? ALERT_CLASSES.info : "border-slate-200/70 bg-slate-50/50 opacity-80 dark:border-slate-800/70 dark:bg-slate-900/30",
                  )}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-slate-800 dark:text-slate-100">{alert.title}</span>
                      <Chip severity={alert.severity === "critical" ? "critical" : alert.severity === "warning" ? "warning" : "info"}>
                        {alert.severity}
                      </Chip>
                      {!alert.is_active ? <Chip severity="good">resolved</Chip> : null}
                      {alert.acknowledged_at ? <Chip severity="info">acknowledged</Chip> : null}
                    </div>
                    <span className="text-[11px] text-slate-400">
                      {relativeTime(alert.last_seen_at ?? alert.triggered_at)}
                      {alert.occurrence_count > 1 ? ` · ×${alert.occurrence_count}` : ""}
                    </span>
                  </div>
                  <p className="mt-1.5 text-xs text-slate-600 dark:text-slate-300">{alert.message}</p>
                  <div className="mt-1.5 flex flex-wrap items-center gap-3 text-[11px] text-slate-500 dark:text-slate-400">
                    <span>category: {alert.category.replace(/_/g, " ")}</span>
                    {alert.sensor ? <span>sensor: {alert.sensor.replace(/_/g, " ")}</span> : null}
                    {alert.metric_value !== null ? <span className="tabular">value: {Number(alert.metric_value).toFixed(2)}</span> : null}
                    {alert.risk_level ? <span>risk level {alert.risk_level}</span> : null}
                  </div>
                  {alert.recommended_action ? (
                    <p className="mt-1.5 text-[11px] text-slate-500 dark:text-slate-400">→ {alert.recommended_action}</p>
                  ) : null}
                  {alert.is_active ? (
                    <div className="mt-2 flex gap-2">
                      {!alert.acknowledged_at ? (
                        <button
                          type="button"
                          onClick={() => void act(alert, "acknowledge")}
                          className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2 py-1 text-[11px] text-slate-600 transition hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
                        >
                          <Check size={11} />
                          acknowledge
                        </button>
                      ) : null}
                      <button
                        type="button"
                        onClick={() => void act(alert, "resolve")}
                        className="rounded-lg border border-slate-200 px-2 py-1 text-[11px] text-slate-600 transition hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
                      >
                        resolve
                      </button>
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card>
          <SectionHeader
            title="Alert rules"
            subtitle="Loaded from the backend - the same definitions that actually fire"
            icon={<ListChecks size={16} />}
            className="mb-3"
          />
          <ul className="space-y-2">
            {(meta?.alert_rules ?? []).map((rule) => (
              <li key={rule.id} className="rounded-xl bg-slate-50/70 px-3 py-2 dark:bg-slate-900/40">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold text-slate-700 dark:text-slate-200">{rule.title}</span>
                  <Chip severity={rule.severity === "critical" ? "critical" : rule.severity === "warning" ? "warning" : "info"}>
                    {rule.severity}
                  </Chip>
                </div>
                <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">{rule.description}</p>
                <p className="mt-1 text-[10px] text-slate-400">condition: {rule.condition}</p>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}
