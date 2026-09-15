/** Settings & platform information: configuration, environment variables and data truthfulness. */

import { Info, Server, Settings as SettingsIcon, ShieldCheck, Workflow } from "lucide-react";
import { useEffect, useState } from "react";
import { Card, Chip, DataBadge, InlineNote, SectionHeader, StatusDot } from "../components/common/Ui";
import { API_BASE_URL, API_PREFIX, api } from "../services/api";
import { usePlatform } from "../state/PlatformContext";
import type { WorkerStatus } from "../types";
import { relativeTime } from "../utils/format";

export default function SettingsPage() {
  const { meta, status, theme, toggleTheme, overview } = usePlatform();
  const [workers, setWorkers] = useState<WorkerStatus | null>(null);
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    void api.workers().then(setWorkers).catch(() => undefined);
    void api.health().then(setHealth).catch(() => setHealth(null));
  }, []);

  const bool = (value: unknown) => (value ? "true" : "false");

  return (
    <div className="space-y-5">
      <SectionHeader
        title="Settings & platform info"
        subtitle="Runtime configuration, feature flags and the rules this platform follows about data truthfulness."
        icon={<SettingsIcon size={16} />}
      />

      <div className="grid items-start gap-4 lg:grid-cols-2">
        <Card>
          <SectionHeader title="Appearance" className="mb-3" />
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={toggleTheme}
              className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
            >
              Switch to {theme === "dark" ? "light" : "dark"} theme
            </button>
            <span className="text-xs text-slate-500 dark:text-slate-400">
              Current: {theme}. The preference is stored in the browser only.
            </span>
          </div>
        </Card>

        <Card>
          <SectionHeader title="Backend connection" subtitle="Frontend -> FastAPI" icon={<Server size={16} />} className="mb-3" />
          <dl className="space-y-1.5 text-xs">
            <Row label="API base URL" value={API_BASE_URL || `${window.location.origin} (dev proxy)`} />
            <Row label="API prefix" value={API_PREFIX} />
            <Row label="Backend status" value={String(health?.status ?? "unknown")} />
            <Row label="Environment" value={meta?.environment ?? "unknown"} />
            <Row label="Server time" value={relativeTime(String(health?.server_time ?? meta?.server_time))} />
            <Row label="Uptime" value={health ? `${Number(health.uptime_seconds ?? 0).toFixed(0)} s` : "—"} />
            <Row label="Realtime subscribers" value={String(status?.realtime_subscribers ?? 0)} />
          </dl>
          <InlineNote severity="info" className="mt-3">
            Set <code>VITE_API_BASE_URL</code> to point the frontend at a backend on another host. No API key or
            secret is ever embedded in the frontend bundle.
          </InlineNote>
        </Card>

        <Card>
          <SectionHeader title="Feature flags" subtitle="Reported by the backend" icon={<Workflow size={16} />} className="mb-3" />
          <div className="flex flex-wrap gap-2">
            {Object.entries(meta?.features ?? {}).map(([key, value]) => (
              <Chip key={key} severity={value === true || (typeof value === "number" && value > 0) ? "good" : "unknown"}>
                {key.replace(/_/g, " ")}: {typeof value === "boolean" ? bool(value) : String(value)}
              </Chip>
            ))}
          </div>
          <div className="mt-3 space-y-2 text-xs">
            <Row label="Selected device" value={status?.data_source ?? "unknown"} />
            <Row label="Ollama model" value={status?.ollama?.model ?? "unavailable"} />
            <Row label="Alert rules loaded" value={String(workers?.rules_loaded ?? meta?.alert_rules.length ?? 0)} />
            <Row label="Background workers" value={workers?.background.jobs.join(", ") ?? "—"} />
          </div>
        </Card>

        <Card>
          <SectionHeader title="Environment variables" subtitle="Backend and Arduino configuration surface" className="mb-3" />
          <pre className="overflow-x-auto rounded-xl bg-slate-900 px-3 py-3 text-[11px] leading-relaxed text-slate-100 dark:bg-slate-950">
{`# backend/.env
API_KEY=replace_with_secure_key
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
DATABASE_URL=sqlite:///./data/environmental.db
CORS_ORIGINS=http://localhost:5173
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=            # empty = auto-detect from installed models
OLLAMA_DISABLE_THINKING=false
RISK_CONFIG_FILE=        # optional JSON to replace the risk model

# frontend/.env
VITE_API_BASE_URL=       # empty = same-origin (dev proxy)
VITE_PROXY_TARGET=http://127.0.0.1:8000`}
          </pre>
          <InlineNote severity="watch" className="mt-3">
            Never commit real credentials. The Arduino firmware keeps its Wi-Fi password and API key in a
            configuration header that is excluded from version control.
          </InlineNote>
        </Card>
      </div>

      <Card>
        <SectionHeader
          title="Data truthfulness"
          subtitle="How this platform distinguishes measured, derived and predicted information"
          icon={<ShieldCheck size={16} />}
          className="mb-3"
        />
        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-2 text-xs text-slate-600 dark:text-slate-300">
            <div className="flex items-center gap-2">
              <DataBadge source="arduino" />
              <span>Values measured by the physical Arduino node and stored with source=arduino.</span>
            </div>
            <div className="flex items-center gap-2">
              <DataBadge predicted />
              <span>Statistical estimates with method, confidence and horizon - never stated as facts.</span>
            </div>
          </div>
          <ul className="space-y-1.5 text-xs text-slate-600 dark:text-slate-300">
            <li>• Missing sensor values stay missing; the API reports them instead of interpolating silently.</li>
            <li>• Stale readings are flagged in the header, on the dashboard and to the chatbot.</li>
            <li>• Forecasts disclose method, sample count, R², confidence and whether the horizon is an extrapolation.</li>
            <li>• Air quality is reported as a relative index, not ppm, until the MQ-135 is calibrated.</li>
            <li>• Firmware/backend calibration disagreements are surfaced as warnings.</li>
            <li>• Observations are only produced when the supporting statistics exist.</li>
          </ul>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3 text-[11px] text-slate-500 dark:text-slate-400">
          <span className="inline-flex items-center gap-1.5">
            <StatusDot severity={status?.backend === "online" ? "good" : "critical"} />
            backend {status?.backend ?? "unknown"}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <StatusDot severity={status?.database === "online" ? "good" : "critical"} />
            database {status?.database ?? "unknown"}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <StatusDot severity={status?.device_online ? "good" : "watch"} />
            device {status?.arduino ?? "unknown"}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <StatusDot severity={status?.ollama?.available ? "good" : "unknown"} />
            AI {status?.ollama?.available ? "available" : "unavailable"}
          </span>
        </div>
      </Card>

      <Card>
        <SectionHeader title="Data source in use" icon={<Info size={16} />} className="mb-3" />
        <div className="flex flex-wrap items-center gap-3 text-xs text-slate-600 dark:text-slate-300">
          {overview?.data_source === "arduino" ? (
            <DataBadge source="arduino" />
          ) : (
            <DataBadge source="unknown" />
          )}
          <span>
            {overview?.has_data
              ? `Last reading received ${relativeTime(overview.latest.received_at)} from ${overview.device.device_id}.`
              : "No readings have been stored yet."}
          </span>
        </div>
      </Card>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="tabular max-w-[60%] truncate font-medium text-slate-700 dark:text-slate-200" title={value}>
        {value}
      </dd>
    </div>
  );
}
