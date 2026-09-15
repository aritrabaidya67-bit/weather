/**
 * AI Chat Panel: Re-styled to fit the premium design aesthetic.
 * Focuses on smooth transitions, premium inputs, and elegant bubbles.
 */

import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, BrainCircuit, Eraser, Send, Sparkles, User, Database } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, streamChat, ApiError } from "../../services/api";
import type { ChatMessage, OllamaStatus } from "../../types";
import { classNames, relativeTime } from "../../utils/format";
import { Chip, Spinner } from "../common/Ui";

const SESSION_KEY = "eip-chat-session";

export function ChatPanel({ deviceId, compact = false }: { deviceId?: string | null; compact?: boolean }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [status, setStatus] = useState<OllamaStatus | null>(null);
  const sessionRef = useRef<string>("");
  const scrollRef = useRef<HTMLDivElement | null>(null);

  if (!sessionRef.current) {
    const stored = window.localStorage.getItem(SESSION_KEY);
    sessionRef.current = stored ?? `web-${Math.random().toString(36).slice(2, 10)}`;
    window.localStorage.setItem(SESSION_KEY, sessionRef.current);
  }

  useEffect(() => {
    void api.chatStatus().then(setStatus).catch(() => setStatus(null));
    void api.chatSuggestions(deviceId ?? undefined).then((data) => setSuggestions(data.questions)).catch(() => undefined);
    void api.chatHistory(sessionRef.current)
      .then((data) => {
        const restored: ChatMessage[] = data.messages.map((raw) => ({
          role: (raw.role as "user" | "assistant") ?? "assistant",
          content: String(raw.content ?? ""),
          createdAt: String(raw.created_at ?? new Date().toISOString()),
          model: (raw.model as string | null) ?? null,
          warning: (raw.error as string | null) ?? null,
        }));
        if (restored.length) setMessages(restored.slice(-12));
      }).catch(() => undefined);
  }, [deviceId]);

  useEffect(() => {
    const node = scrollRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [messages, streamingText]);

  const history = useMemo(() => messages.slice(-8).map((m) => ({ role: m.role, content: m.content })), [messages]);

  const send = useCallback(async (question: string) => {
    const trimmed = question.trim();
    if (!trimmed || busy) return;
    setError(null);
    setBusy(true);
    setInput("");
    
    setMessages((current) => [...current, { role: "user", content: trimmed, createdAt: new Date().toISOString() }]);
    setStreamingText("");

    let accumulated = "";
    try {
      await streamChat(
        { message: trimmed, session_id: sessionRef.current, device_id: deviceId ?? undefined, history },
        {
          onToken: (token) => { accumulated += token; setStreamingText(accumulated); },
          onError: (msg) => setError(msg),
        },
      );
      setMessages((current) => [
        ...current,
        { role: "assistant", content: accumulated || "(no answer returned)", createdAt: new Date().toISOString(), model: status?.model ?? null, streaming: false },
      ]);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail : "The AI analyst could not be reached.");
    } finally {
      setStreamingText("");
      setBusy(false);
    }
  }, [busy, deviceId, history, status?.model]);

  const clear = useCallback(async () => {
    setMessages([]);
    setError(null);
    try { await api.clearChatHistory(sessionRef.current); } catch {}
  }, []);

  return (
    <div className={classNames("flex flex-col relative", compact ? "h-[620px]" : "h-[calc(100dvh-230px)] min-h-[520px]")}>
      
      {/* Chat Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 p-4 border-b border-slate-200/50 dark:border-white/5 bg-slate-50/50 dark:bg-surface-900/50 rounded-t-2xl">
        <div className="flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-xl bg-cyan-500/10 text-cyan-600 dark:bg-cyan-500/20 dark:text-cyan-400 shadow-inner">
            <BrainCircuit size={20} />
          </div>
          <div>
            <h2 className="text-base font-bold text-slate-800 dark:text-white flex items-center gap-2">
              Environmental Analyst
              {status?.available ? <Chip severity="good">Online</Chip> : <Chip severity="watch">Fallback</Chip>}
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400 font-medium">
              {status?.available ? `Powered by Ollama (${status.model})` : "Using built-in rule-based analysis"}
            </p>
          </div>
        </div>
        <button
          onClick={clear}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-slate-500 hover:bg-white hover:text-slate-900 hover:shadow-sm dark:hover:bg-surface-800 dark:hover:text-white transition-all"
        >
          <Eraser size={14} /> Clear Chat
        </button>
      </div>

      {/* Messages Area */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-6 scroll-smooth">
        {messages.length === 0 && !streamingText && (
          <div className="h-full flex items-center justify-center">
            <div className="max-w-md text-center">
              <div className="w-16 h-16 bg-gradient-to-br from-cyan-400 to-blue-600 rounded-full flex items-center justify-center mx-auto mb-6 shadow-lg shadow-cyan-500/20">
                <Sparkles size={32} className="text-white" />
              </div>
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-2">How can I help?</h3>
              <p className="text-sm text-slate-500 dark:text-slate-400 leading-relaxed">
                I can analyze the current environmental state, explain risk factors, or summarize recent trends based strictly on the data collected by your sensors.
              </p>
            </div>
          </div>
        )}

        <AnimatePresence initial={false}>
          {messages.map((message, index) => (
            <MessageBubble key={`${message.createdAt}-${index}`} message={message} />
          ))}
        </AnimatePresence>

        {streamingText && (
          <MessageBubble
            message={{ role: "assistant", content: streamingText, createdAt: new Date().toISOString(), streaming: true, model: status?.model ?? null }}
          />
        )}

        {busy && !streamingText && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex items-center gap-3 text-xs font-medium text-slate-400 ml-12">
            <Spinner /> Processing telemetry data...
          </motion.div>
        )}

        {error && (
          <div className="flex items-center gap-2 p-3 rounded-xl bg-rose-50 text-rose-600 dark:bg-rose-500/10 dark:text-rose-400 text-sm font-medium">
            <AlertTriangle size={16} /> {error}
          </div>
        )}
      </div>

      {/* Input Area */}
      <div className="p-4 bg-white dark:bg-surface-800 border-t border-slate-200/50 dark:border-white/5 rounded-b-2xl">
        {suggestions.length > 0 && messages.length === 0 && (
          <div className="flex flex-wrap gap-2 mb-4">
            {suggestions.map(q => (
              <button
                key={q}
                onClick={() => send(q)}
                disabled={busy}
                className="px-3 py-1.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600 hover:bg-cyan-50 hover:text-cyan-700 dark:bg-surface-900 dark:text-slate-400 dark:hover:bg-cyan-500/10 dark:hover:text-cyan-300 transition-colors"
              >
                {q}
              </button>
            ))}
          </div>
        )}

        <form onSubmit={e => { e.preventDefault(); send(input); }} className="relative flex items-end gap-2">
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); } }}
            rows={1}
            placeholder="Ask about the environment..."
            className="w-full bg-slate-50 dark:bg-surface-900 border border-slate-200/60 dark:border-white/10 rounded-2xl px-4 py-3.5 text-sm text-slate-900 dark:text-white outline-none focus:ring-2 focus:ring-cyan-500/50 focus:border-transparent transition-all resize-none min-h-[50px] max-h-[150px]"
          />
          <button
            type="submit"
            disabled={busy || !input.trim()}
            className="absolute right-2 bottom-2 h-9 w-9 flex items-center justify-center rounded-xl bg-cyan-500 text-white hover:bg-cyan-600 disabled:opacity-50 disabled:hover:bg-cyan-500 transition-colors shadow-md shadow-cyan-500/20"
          >
            {busy ? <Spinner /> : <Send size={16} className="ml-0.5" />}
          </button>
        </form>
      </div>
    </div>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className={classNames("flex gap-3", isUser ? "flex-row-reverse" : "flex-row")}
    >
      <div className={classNames(
        "flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center shadow-sm mt-1",
        isUser ? "bg-slate-800 text-white dark:bg-slate-200 dark:text-slate-900" : "bg-gradient-to-br from-cyan-400 to-blue-600 text-white"
      )}>
        {isUser ? <User size={14} strokeWidth={2.5} /> : <BrainCircuit size={16} strokeWidth={2.5} />}
      </div>
      
      <div className="flex flex-col max-w-[85%]">
        <div className={classNames(
          "px-4 py-3 text-sm leading-relaxed",
          isUser 
            ? "bg-slate-800 text-white rounded-2xl rounded-tr-sm dark:bg-slate-200 dark:text-slate-900" 
            : "bg-slate-100 text-slate-800 rounded-2xl rounded-tl-sm dark:bg-surface-900 dark:text-slate-200 shadow-sm border border-slate-200/50 dark:border-white/5"
        )}>
          <p className="whitespace-pre-wrap">{message.content}</p>
          {message.streaming && <span className="ml-1 inline-block w-1.5 h-4 bg-cyan-500 animate-pulse align-middle" />}
        </div>
        
        <div className={classNames(
          "flex items-center gap-2 mt-1.5 text-[10px] font-medium uppercase tracking-widest text-slate-400",
          isUser ? "justify-end" : "justify-start ml-1"
        )}>
          <span>{relativeTime(message.createdAt)}</span>
          {!isUser && message.model && <span>• {message.model}</span>}
        </div>

        {message.citations?.length ? (
          <div className="mt-2 ml-1">
            <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest text-cyan-600 dark:text-cyan-400 mb-1">
              <Database size={10} /> Data Sources
            </div>
            <ul className="space-y-1">
              {message.citations.slice(0, 4).map(cit => (
                <li key={`${cit.label}-${cit.value}`} className="text-xs px-2 py-1 bg-slate-50 dark:bg-surface-900/50 rounded border border-slate-100 dark:border-white/5 inline-block mr-2 mb-1">
                  <span className="font-semibold text-slate-600 dark:text-slate-300">{cit.label}:</span> <span className="text-slate-500 dark:text-slate-400">{cit.value}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </motion.div>
  );
}
