/**
 * AI Chat Page.
 * A premium full-page layout for interacting with the AI analyst.
 */

import { BrainCircuit, Cpu, ShieldCheck, Database, AlertTriangle } from "lucide-react";
import { useEffect, useState } from "react";

import { ChatPanel } from "../components/chat/ChatPanel";
import { Chip, DataBadge, SectionHeaderPill, StatusDot } from "../components/common/Ui";
import { api } from "../services/api";
import { usePlatform } from "../state/PlatformContext";
import type { OllamaStatus } from "../types";
import { relativeTime } from "../utils/format";

export default function ChatPage() {
  const { overview, deviceId } = usePlatform();
  const [ollama, setOllama] = useState<OllamaStatus | null>(null);

  useEffect(() => {
    void api.chatStatus().then(setOllama).catch(() => setOllama(null));
  }, []);

  return (
    <div className="space-y-6 animate-float-in h-full flex flex-col">
      
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 panel p-5">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-2">
            <BrainCircuit size={20} className="text-cyan-500" />
            AI Analyst
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Data-grounded environmental analysis.
          </p>
        </div>
        <DataBadge source={overview?.data_source} />
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)] flex-1 min-h-0">
        
        {/* Main Chat Interface */}
        <div className="panel flex flex-col min-h-[600px] xl:min-h-0 shadow-lg border-slate-200/80 dark:border-white/10">
          <ChatPanel deviceId={deviceId} />
        </div>

        {/* Sidebar Context */}
        <div className="space-y-6 overflow-y-auto pr-1 pb-6">
          
          <section className="panel p-6">
            <SectionHeaderPill icon={<Cpu size={16} />} title="Model Engine" className="mb-4" />
            
            <div className="bg-slate-50 dark:bg-surface-900/40 rounded-xl p-4 border border-slate-200/50 dark:border-white/5 mb-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-bold text-slate-800 dark:text-slate-200">
                  {ollama?.available ? ollama.model : 'Rule-Based System'}
                </span>
                <StatusDot severity={ollama?.available ? "good" : "watch"} pulse={ollama?.available} />
              </div>
              <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
                {ollama?.available 
                  ? `Running locally via Ollama (${ollama.host}).` 
                  : "Ollama not detected. Falling back to the deterministic rule-based analyst."}
              </p>
            </div>

            {ollama?.models_available?.length ? (
              <div>
                <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-2">Available Models</p>
                <div className="flex flex-wrap gap-1.5">
                  {ollama.models_available.map((model) => (
                    <Chip key={model} severity={model === ollama.model ? "good" : "unknown"}>{model}</Chip>
                  ))}
                </div>
              </div>
            ) : null}
          </section>

          <section className="panel p-6">
            <SectionHeaderPill icon={<Database size={16} />} title="Data Grounding" className="mb-4" />
            
            <p className="text-xs font-medium text-slate-600 dark:text-slate-300 leading-relaxed mb-4">
              The analyst is provided a realtime snapshot of the environment for every query. It can see:
            </p>
            
            <ul className="space-y-2 text-xs text-slate-500 dark:text-slate-400">
              <li className="flex items-center gap-2"><span className="w-1 h-1 rounded-full bg-cyan-500"></span> Live sensor readings & bands</li>
              <li className="flex items-center gap-2"><span className="w-1 h-1 rounded-full bg-cyan-500"></span> Risk scores & drivers</li>
              <li className="flex items-center gap-2"><span className="w-1 h-1 rounded-full bg-cyan-500"></span> Recent anomalies</li>
              <li className="flex items-center gap-2"><span className="w-1 h-1 rounded-full bg-cyan-500"></span> Statistical forecasts</li>
            </ul>

            <div className="mt-6 pt-4 border-t border-slate-200/50 dark:border-white/5 text-[11px] text-slate-400 flex flex-col gap-2">
              <span className="flex items-start gap-1.5 text-amber-600 dark:text-amber-400 font-medium">
                <AlertTriangle size={12} className="shrink-0 mt-0.5" /> 
                The model is explicitly instructed never to hallucinate sensor values.
              </span>
            </div>
          </section>

          <section className="panel p-6">
            <SectionHeaderPill icon={<ShieldCheck size={16} />} title="Current Context Snapshot" className="mb-4" />
            {overview?.has_data ? (
              <div className="grid grid-cols-2 gap-4">
                <ContextBlock label="Risk Level" value={`L${overview.risk.level}`} />
                <ContextBlock label="Active Alerts" value={String(overview.active_alert_count)} />
                <ContextBlock label="Anomalies" value={String(overview.anomalies.length)} />
                <ContextBlock label="Stale Data" value={overview.stale ? "Yes" : "No"} />
                <div className="col-span-2">
                  <ContextBlock label="Last Update" value={relativeTime(overview.latest.received_at)} />
                </div>
              </div>
            ) : (
              <div className="p-4 rounded-xl bg-amber-50 text-amber-600 dark:bg-amber-500/10 dark:text-amber-400 text-xs font-medium border border-amber-200 dark:border-amber-500/20">
                Waiting for device telemetry to build context.
              </div>
            )}
          </section>

        </div>
      </div>
    </div>
  );
}

function ContextBlock({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-slate-50 dark:bg-surface-900/50 border border-slate-100 dark:border-white/5 rounded-lg p-3 text-center">
      <div className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-1">{label}</div>
      <div className="font-bold text-slate-800 dark:text-slate-200">{value}</div>
    </div>
  );
}
