/** AI chat page: conversational analysis plus the exact data snapshot context. */

import { BrainCircuit, Cpu, Info, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ChatPanel } from "../components/chat/ChatPanel";
import { Card, Chip, DataBadge, InlineNote, SectionHeader, StatusDot } from "../components/common/Ui";
import { api } from "../services/api";
import { usePlatform } from "../state/PlatformContext";
import type { OllamaStatus } from "../types";
import { relativeTime } from "../utils/format";

export default function ChatPage() {
  const { overview, meta, status, deviceId } = usePlatform();
  const [ollama, setOllama] = useState<OllamaStatus | null>(null);

  useEffect(() => {
    void api.chatStatus().then(setOllama).catch(() => setOllama(null));
  }, []);

  const simulated = overview?.data_source === "simulation" || Boolean(meta?.simulation_mode);

  return (
    <div className="space-y-5">
      <SectionHeader
        title="AI analyst"
        subtitle="Ask questions about the current and historical environment. Answers are grounded in this platform's own data."
        icon={<BrainCircuit size={16} />}
        action={simulated ? <DataBadge source="simulation" /> : <DataBadge source={overview?.data_source} />}
      />

      <div className="grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Card>
          <ChatPanel deviceId={deviceId} />
        </Card>

        <div className="space-y-4">
          <Card>
            <SectionHeader title="Model status" subtitle="Reuses your existing Ollama installation" className="mb-3" />
            <div className="space-y-2 text-xs">
              <div className="flex items-center gap-2">
                <StatusDot severity={ollama?.available ? "good" : ollama?.running ? "watch" : "unknown"} pulse={ollama?.available} />
                <span className="font-medium text-slate-700 dark:text-slate-200">
                  {ollama?.available ? `${ollama.model} ready` : ollama?.installed ? "Ollama installed, not serving a chat model" : "Ollama not detected"}
                </span>
              </div>
              <p className="text-slate-500 dark:text-slate-400">
                Host: {ollama?.host ?? "unknown"} · running: {String(ollama?.running ?? false)}
              </p>
              {ollama?.models_available?.length ? (
                <div className="flex flex-wrap gap-1">
                  {ollama.models_available.map((model) => (
                    <Chip key={model} severity={model === ollama.model ? "good" : "unknown"}>
                      {model}
                    </Chip>
                  ))}
                </div>
              ) : null}
              {ollama?.detail ? <InlineNote severity={ollama.available ? "good" : "watch"}>{ollama.detail}</InlineNote> : null}
              <InlineNote severity="info">
                Configure with OLLAMA_HOST / OLLAMA_MODEL in backend/.env. The browser never talks to Ollama directly,
                and no model is ever downloaded or replaced by this project.
              </InlineNote>
            </div>
          </Card>

          <Card>
            <SectionHeader
              title="What the assistant can see"
              subtitle="The snapshot is rebuilt for every question"
              icon={<ShieldCheck size={16} />}
              className="mb-3"
            />
            <ul className="space-y-1.5 text-xs text-slate-600 dark:text-slate-300">
              <li>• Current reading for every channel, with units and interpretation</li>
              <li>• Risk score, level, per-factor contributions and recommended actions</li>
              <li>• Anomalies detected against rolling baselines</li>
              <li>• Forecast values, methods, confidence and horizon</li>
              <li>• 6-hour statistics, trends and correlations</li>
              <li>• Sensor health and device connectivity status</li>
            </ul>
            <InlineNote severity="watch" className="mt-3">
              The model is instructed never to invent a sensor value and to say when data is missing, stale or
              simulated. If it cannot answer from the snapshot it must say so.
            </InlineNote>
            <div className="mt-3 flex flex-wrap gap-2 text-[11px]">
              <Link to="/risk" className="text-cyan-600 hover:underline dark:text-cyan-400">
                risk analysis →
              </Link>
              <Link to="/predictions" className="text-cyan-600 hover:underline dark:text-cyan-400">
                forecast →
              </Link>
              <Link to="/device" className="text-cyan-600 hover:underline dark:text-cyan-400">
                hardware →
              </Link>
            </div>
          </Card>

          <Card>
            <SectionHeader title="Context snapshot" subtitle="Exactly what may be referenced in an answer" icon={<Cpu size={16} />} className="mb-3" />
            {overview?.has_data ? (
              <dl className="grid grid-cols-2 gap-3 text-xs">
                <Context label="Data source" value={simulated ? "simulated" : overview.data_source} />
                <Context label="Last reading" value={relativeTime(overview.latest.received_at)} />
                <Context label="Risk" value={`${overview.risk.score.toFixed(0)} / L${overview.risk.level}`} />
                <Context label="Anomalies" value={String(overview.anomalies.length)} />
                <Context label="Active alerts" value={String(overview.active_alert_count)} />
                <Context label="Readings in window" value={String(overview.reading_count)} />
                <Context label="Model" value={status?.ollama?.model ?? "rule-based analyst"} />
                <Context label="Stale" value={overview.stale ? "yes" : "no"} />
              </dl>
            ) : (
              <InlineNote severity="watch">
                No readings stored yet, so the assistant can only explain the platform state - not the environment.
              </InlineNote>
            )}
            <p className="mt-3 flex items-start gap-1.5 text-[11px] text-slate-400">
              <Info size={11} className="mt-0.5" />
              Simulations, forecasts and measurements are labelled differently throughout the dashboard so you can
              always tell what is measured, what is estimated and what is synthetic.
            </p>
          </Card>
        </div>
      </div>
    </div>
  );
}

function Context({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className="font-medium text-slate-700 dark:text-slate-200">{value}</dd>
    </div>
  );
}
