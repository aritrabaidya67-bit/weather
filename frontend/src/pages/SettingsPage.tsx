/**
 * Settings & platform info.
 * Re-styled for premium aesthetics and clarity.
 */

import { Server, Settings as SettingsIcon, ShieldCheck, Workflow } from "lucide-react";
import { useEffect, useState } from "react";
import { Chip, DataBadge, SectionHeaderPill, StatusDot } from "../components/common/Ui";
import { API_BASE_URL, API_PREFIX, api } from "../services/api";
import { usePlatform } from "../state/PlatformContext";
import type { WorkerStatus } from "../types";
import { relativeTime } from "../utils/format";

export default function SettingsPage() {
  const { meta, status, theme, toggleTheme } = usePlatform();
  const [workers, setWorkers] = useState<WorkerStatus | null>(null);
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    void api.workers().then(setWorkers).catch(() => undefined);
    void api.health().then(setHealth).catch(() => setHealth(null));
  }, []);

  const bool = (val: unknown) => (val ? "true" : "false");

  return (
    <div className="space-y-6 animate-float-in">
      
      <div className="panel p-6 sm:p-8 relative overflow-hidden bg-gradient-to-r from-slate-50 to-white dark:from-surface-900 dark:to-surface-800">
        <div className="absolute right-0 top-0 w-48 h-48 bg-slate-200/50 dark:bg-white/5 rounded-full filter blur-3xl translate-x-1/3 -translate-y-1/3" />
        <div className="relative z-10 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-2">
              <SettingsIcon size={24} className="text-slate-400" />
              Platform Settings
            </h1>
            <p className="text-sm text-slate-500 mt-1 max-w-xl">
              Runtime configuration, system health, and data truthfulness policies.
            </p>
          </div>
          <button
            onClick={toggleTheme}
            className="flex items-center gap-2 px-4 py-2 bg-slate-900 text-white dark:bg-white dark:text-slate-900 rounded-full text-sm font-semibold hover:shadow-md transition-all"
          >
            Toggle {theme === "dark" ? "Light" : "Dark"} Mode
          </button>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        
        {/* System Health */}
        <section className="panel p-6">
          <SectionHeaderPill icon={<Server size={16} />} title="System Health & API" className="mb-6" />
          
          <div className="space-y-3 mb-6">
            <Row label="API Base URL" value={API_BASE_URL || `${window.location.origin} (dev proxy)`} />
            <Row label="API Prefix" value={API_PREFIX} />
            <Row label="Environment" value={meta?.environment ?? "unknown"} />
            <Row label="Backend Status" value={String(health?.status ?? "unknown")} />
            <Row label="Server Time" value={relativeTime(String(health?.server_time ?? meta?.server_time))} />
            <Row label="Uptime" value={health ? `${Number(health.uptime_seconds ?? 0).toFixed(0)} s` : "—"} />
          </div>

          <div className="p-4 rounded-xl bg-slate-50/50 dark:bg-surface-900/40 border border-slate-200/50 dark:border-white/5 flex flex-wrap gap-4 text-xs font-medium">
            <span className="flex items-center gap-1.5"><StatusDot severity={status?.backend === "online" ? "good" : "critical"} /> Backend</span>
            <span className="flex items-center gap-1.5"><StatusDot severity={status?.database === "online" ? "good" : "critical"} /> Database</span>
            <span className="flex items-center gap-1.5"><StatusDot severity={status?.device_online ? "good" : "watch"} /> Device</span>
            <span className="flex items-center gap-1.5"><StatusDot severity={status?.ollama?.available ? "good" : "unknown"} /> AI Engine</span>
          </div>
        </section>

        {/* Feature Flags */}
        <section className="panel p-6">
          <SectionHeaderPill icon={<Workflow size={16} />} title="Feature Flags" className="mb-6" />
          
          <div className="flex flex-wrap gap-2 mb-6">
            {Object.entries(meta?.features ?? {}).map(([key, value]) => (
              <Chip key={key} severity={value === true || (typeof value === "number" && value > 0) ? "good" : "unknown"}>
                {key.replace(/_/g, " ")}: {typeof value === "boolean" ? bool(value) : String(value)}
              </Chip>
            ))}
          </div>

          <div className="space-y-3 p-4 rounded-xl bg-slate-50/50 dark:bg-surface-900/40 border border-slate-200/50 dark:border-white/5">
            <Row label="Active Device" value={status?.data_source ?? "unknown"} />
            <Row label="Ollama Model" value={status?.ollama?.model ?? "unavailable"} />
            <Row label="Alert Rules Loaded" value={String(workers?.rules_loaded ?? meta?.alert_rules.length ?? 0)} />
            <Row label="Subscribers" value={String(status?.realtime_subscribers ?? 0)} />
          </div>
        </section>

        {/* Data Truthfulness */}
        <section className="panel p-6 lg:col-span-2">
          <SectionHeaderPill icon={<ShieldCheck size={16} />} title="Data Truthfulness Policy" className="mb-6" />
          
          <div className="grid gap-6 md:grid-cols-2">
            <div className="space-y-4">
              <div className="p-4 rounded-xl bg-sky-50 dark:bg-sky-500/5 border border-sky-100 dark:border-sky-500/10">
                <div className="flex items-center gap-2 mb-2"><DataBadge source="arduino" /></div>
                <p className="text-sm text-slate-700 dark:text-slate-300">Values physically measured by hardware sensors. Never fabricated.</p>
              </div>
              <div className="p-4 rounded-xl bg-purple-50 dark:bg-purple-500/5 border border-purple-100 dark:border-purple-500/10">
                <div className="flex items-center gap-2 mb-2"><DataBadge predicted /></div>
                <p className="text-sm text-slate-700 dark:text-slate-300">Statistical estimates explicitly marked with methodology and confidence intervals.</p>
              </div>
            </div>
            
            <div className="space-y-3">
              <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Strict Guidelines</p>
              <ul className="space-y-2 text-sm text-slate-600 dark:text-slate-400">
                <li className="flex items-start gap-2">
                  <span className="text-cyan-500">•</span> Missing values remain null; we do not silently interpolate.
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-cyan-500">•</span> Stale readings are immediately flagged across all UI components.
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-cyan-500">•</span> Forecasts always disclose sample counts, R², and algorithms used.
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-cyan-500">•</span> Observations require statistical backing before generation.
                </li>
              </ul>
            </div>
          </div>
        </section>

      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-slate-100 dark:border-white/5 pb-2 last:border-0 last:pb-0">
      <span className="text-xs font-bold uppercase tracking-wider text-slate-400">{label}</span>
      <span className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate" title={value}>{value}</span>
    </div>
  );
}
