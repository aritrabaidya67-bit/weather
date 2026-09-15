/**
 * AI analyst panel.
 *
 * Grounding is always visible: every answer states whether the model or the
 * built-in rule-based analyst produced it, and citations point back at the
 * platform's own data snapshot. Streaming tokens arrive over NDJSON.
 */

import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, BrainCircuit, Cpu, Eraser, Send, Sparkles, User } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, streamChat, ApiError } from "../../services/api";
import type { ChatCitation, ChatMessage, OllamaStatus } from "../../types";
import { classNames, relativeTime } from "../../utils/format";
import { Chip, DataBadge, EmptyState, Spinner } from "../common/Ui";

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
    void api
      .chatHistory(sessionRef.current)
      .then((data) => {
        const restored: ChatMessage[] = data.messages.map((raw) => ({
          role: (raw.role as "user" | "assistant") ?? "assistant",
          content: String(raw.content ?? ""),
          createdAt: String(raw.created_at ?? new Date().toISOString()),
          model: (raw.model as string | null) ?? null,
          warning: (raw.error as string | null) ?? null,
        }));
        if (restored.length) setMessages(restored.slice(-12));
      })
      .catch(() => undefined);
  }, [deviceId]);

  useEffect(() => {
    const node = scrollRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [messages, streamingText]);

  const history = useMemo(
    () => messages.slice(-8).map((message) => ({ role: message.role, content: message.content })),
    [messages],
  );

  const send = useCallback(
    async (question: string) => {
      const trimmed = question.trim();
      if (!trimmed || busy) return;
      setError(null);
      setBusy(true);
      setInput("");
      const userMessage: ChatMessage = {
        role: "user",
        content: trimmed,
        createdAt: new Date().toISOString(),
      };
      setMessages((current) => [...current, userMessage]);
      setStreamingText("");

      let accumulated = "";
      try {
        await streamChat(
          {
            message: trimmed,
            session_id: sessionRef.current,
            device_id: deviceId ?? undefined,
            history,
          },
          {
            onToken: (token) => {
              accumulated += token;
              setStreamingText(accumulated);
            },
            onError: (message) => setError(message),
          },
        );
        setMessages((current) => [
          ...current,
          {
            role: "assistant",
            content: accumulated || "(no answer returned)",
            createdAt: new Date().toISOString(),
            model: status?.model ?? null,
            streaming: false,
          },
        ]);
      } catch (caught) {
        const message =
          caught instanceof ApiError
            ? caught.detail
            : "The AI analyst could not be reached. The sensor dashboard keeps working.";
        setError(message);
      } finally {
        setStreamingText("");
        setBusy(false);
      }
    },
    [busy, deviceId, history, status?.model],
  );

  const clear = useCallback(async () => {
    setMessages([]);
    setError(null);
    try {
      await api.clearChatHistory(sessionRef.current);
    } catch {
      /* clearing locally is enough */
    }
  }, []);

  return (
    <div className={classNames("flex flex-col", compact ? "h-[620px]" : "h-[calc(100dvh-230px)] min-h-[520px]")}>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200/80 pb-3 dark:border-slate-800/80">
        <div className="flex items-center gap-2">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-cyan-500/15 text-cyan-600 dark:text-cyan-300">
            <BrainCircuit size={16} />
          </span>
          <div>
            <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">Environmental analyst</p>
            <p className="text-[11px] text-slate-500 dark:text-slate-400">
              {status?.available
                ? `Local model: ${status.model} via Ollama (${status.host})`
                : status?.installed
                  ? "Ollama detected but not reachable - answers come from the built-in analyst"
                  : "No local model detected - answers come from the built-in analyst"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {status?.available ? <Chip severity="good">model ready</Chip> : <Chip severity="watch">rule-based fallback</Chip>}
          <button
            type="button"
            onClick={() => void clear()}
            className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2 py-1 text-[11px] text-slate-500 transition hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
          >
            <Eraser size={12} />
            Clear
          </button>
        </div>
      </div>

      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto py-4 pr-1">
        {messages.length === 0 && !streamingText ? (
          <EmptyState
            icon={<Sparkles size={18} />}
            title="Ask about the current environment"
            message="The assistant only sees data this platform actually measured: current readings, baselines, anomalies, risk factors and forecasts. It will tell you when something is unavailable."
          />
        ) : null}

        <AnimatePresence initial={false}>
          {messages.map((message, index) => (
            <MessageBubble key={`${message.createdAt}-${index}`} message={message} />
          ))}
        </AnimatePresence>

        {streamingText ? (
          <MessageBubble
            message={{
              role: "assistant",
              content: streamingText,
              createdAt: new Date().toISOString(),
              streaming: true,
              model: status?.model ?? null,
            }}
          />
        ) : null}

        {busy && !streamingText ? (
          <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
            <Spinner />
            Building the data snapshot and querying the model...
          </div>
        ) : null}

        {error ? (
          <div className="flex items-start gap-2 rounded-xl border border-amber-500/40 bg-amber-500/5 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
            <AlertTriangle size={14} className="mt-0.5" />
            <span>{error}</span>
          </div>
        ) : null}
      </div>

      {suggestions.length ? (
        <div className="flex flex-wrap gap-1.5 border-t border-slate-200/80 pt-3 dark:border-slate-800/80">
          {suggestions.map((question) => (
            <button
              key={question}
              type="button"
              disabled={busy}
              onClick={() => void send(question)}
              className="rounded-full border border-slate-200 px-3 py-1 text-[11px] text-slate-600 transition hover:border-cyan-500/50 hover:text-cyan-700 disabled:opacity-50 dark:border-slate-700 dark:text-slate-300 dark:hover:text-cyan-300"
            >
              {question}
            </button>
          ))}
        </div>
      ) : null}

      <form
        className="mt-3 flex items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          void send(input);
        }}
      >
        <textarea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void send(input);
            }
          }}
          rows={2}
          placeholder="e.g. Why is the risk score high, and is it improving?"
          className="min-h-[46px] flex-1 resize-none rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none transition focus:border-cyan-500/60 focus:ring-2 focus:ring-cyan-500/20 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        />
        <button
          type="submit"
          disabled={busy || !input.trim()}
          className="inline-flex h-[46px] items-center gap-1.5 rounded-xl bg-cyan-600 px-4 text-sm font-medium text-white transition hover:bg-cyan-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy ? <Spinner /> : <Send size={15} />}
          Ask
        </button>
      </form>
    </div>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className={classNames("flex gap-2.5", isUser ? "flex-row-reverse" : "flex-row")}
    >
      <span
        className={classNames(
          "mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-lg",
          isUser ? "bg-slate-900 text-white dark:bg-slate-700" : "bg-cyan-500/15 text-cyan-600 dark:text-cyan-300",
        )}
      >
        {isUser ? <User size={14} /> : <Cpu size={14} />}
      </span>
      <div
        className={classNames(
          "max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed",
          isUser
            ? "bg-slate-900 text-white dark:bg-slate-800"
            : "border border-slate-200 bg-white text-slate-700 dark:border-slate-800 dark:bg-slate-900/70 dark:text-slate-200",
        )}
      >
        <p className="whitespace-pre-wrap">{message.content}</p>
        {message.streaming ? (
          <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse bg-cyan-500 align-middle" />
        ) : null}
        <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[10px] text-slate-400">
          <span>{relativeTime(message.createdAt)}</span>
          {!isUser && message.model ? <span>model: {message.model}</span> : null}
          {!isUser && message.warning ? <DataBadge source="analysis" /> : null}
          {message.latencyMs ? <span>{message.latencyMs} ms</span> : null}
        </div>
        {message.citations?.length ? (
          <ul className="mt-2 space-y-0.5 border-t border-slate-200/70 pt-1.5 dark:border-slate-800/70">
            {message.citations.slice(0, 6).map((citation: ChatCitation) => (
              <li key={`${citation.label}-${citation.value}`} className="text-[10px] text-slate-500 dark:text-slate-400">
                <span className="font-medium text-slate-600 dark:text-slate-300">{citation.label}:</span>{" "}
                {citation.value} <span className="opacity-70">· {citation.source}</span>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </motion.div>
  );
}
