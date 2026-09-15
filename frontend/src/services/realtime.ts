/**
 * Realtime client.
 *
 * Primary transport is the WebSocket; if it cannot be established (or keeps
 * failing) the client transparently falls back to Server-Sent Events. Both
 * transports replay recent events using the last seen event id, so reconnects
 * never leave the dashboard showing stale values without saying so.
 */

import type { RealtimeEvent } from "../types";
import { realtimeUrl, sseUrl } from "./api";

export type ConnectionState = "connecting" | "live" | "degraded" | "offline";

type Listener = (event: RealtimeEvent) => void;
type StateListener = (state: ConnectionState, detail: string) => void;

const MAX_BACKOFF_MS = 20_000;
const BASE_BACKOFF_MS = 1_000;
const STALE_AFTER_MS = 45_000;

export class RealtimeClient {
  private topics: string[];
  private listeners = new Set<Listener>();
  private stateListeners = new Set<StateListener>();
  private socket: WebSocket | null = null;
  private source: EventSource | null = null;
  private reconnectTimer: number | null = null;
  private watchdog: number | null = null;
  private attempts = 0;
  private lastEventId = 0;
  private lastMessageAt = 0;
  private stopped = false;
  private state: ConnectionState = "connecting";
  private detail = "Connecting to the realtime bus...";

  constructor(topics: string[] = ["reading", "risk", "alert", "anomaly", "device", "prediction", "system"]) {
    this.topics = topics;
  }

  onEvent(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  onState(listener: StateListener): () => void {
    this.stateListeners.add(listener);
    listener(this.state, this.detail);
    return () => this.stateListeners.delete(listener);
  }

  get currentState(): ConnectionState {
    return this.state;
  }

  start(): void {
    this.stopped = false;
    this.connectWebSocket();
    this.startWatchdog();
  }

  stop(): void {
    this.stopped = true;
    this.clearTimers();
    this.socket?.close();
    this.source?.close();
    this.socket = null;
    this.source = null;
    this.setState("offline", "Realtime connection stopped.");
  }

  private setState(state: ConnectionState, detail: string): void {
    if (this.state === state && this.detail === detail) return;
    this.state = state;
    this.detail = detail;
    this.stateListeners.forEach((listener) => listener(state, detail));
  }

  private clearTimers(): void {
    if (this.reconnectTimer) window.clearTimeout(this.reconnectTimer);
    if (this.watchdog) window.clearInterval(this.watchdog);
    this.reconnectTimer = null;
    this.watchdog = null;
  }

  private startWatchdog(): void {
    if (this.watchdog) window.clearInterval(this.watchdog);
    this.watchdog = window.setInterval(() => {
      if (this.stopped) return;
      const age = Date.now() - this.lastMessageAt;
      if (this.lastMessageAt && age > STALE_AFTER_MS && this.state === "live") {
        this.setState(
          "degraded",
          `No realtime message for ${Math.round(age / 1000)}s. The dashboard may be showing stale values.`,
        );
      }
    }, 10_000);
  }

  private connectWebSocket(): void {
    if (this.stopped) return;
    let socket: WebSocket;
    try {
      socket = new WebSocket(realtimeUrl(this.topics, this.lastEventId));
    } catch {
      this.connectSse();
      return;
    }
    this.socket = socket;
    this.setState("connecting", "Opening realtime connection...");

    socket.onopen = () => {
      this.attempts = 0;
      this.lastMessageAt = Date.now();
      this.setState("live", "Realtime WebSocket connected.");
    };

    socket.onmessage = (message) => {
      try {
        const parsed = JSON.parse(message.data as string) as RealtimeEvent;
        this.accept(parsed);
      } catch {
        /* ignore malformed frames */
      }
    };

    socket.onerror = () => {
      this.setState("degraded", "Realtime socket error; retrying.");
    };

    socket.onclose = () => {
      this.socket = null;
      if (this.stopped) return;
      this.attempts += 1;
      if (this.attempts >= 3 && !this.source) {
        this.connectSse();
        return;
      }
      this.scheduleReconnect(() => this.connectWebSocket());
    };
  }

  private connectSse(): void {
    if (this.stopped || this.source) return;
    this.setState("degraded", "WebSocket unavailable - using Server-Sent Events instead.");
    const source = new EventSource(sseUrl(this.topics, this.lastEventId));
    this.source = source;

    this.topics.forEach((topic) => {
      source.addEventListener(topic, (raw) => {
        try {
          const data = JSON.parse((raw as MessageEvent).data);
          this.accept({ id: Number((raw as MessageEvent).lastEventId || 0), topic: topic as RealtimeEvent["topic"], timestamp: new Date().toISOString(), data });
        } catch {
          /* ignore */
        }
      });
    });

    source.onopen = () => {
      this.attempts = 0;
      this.lastMessageAt = Date.now();
      this.setState("live", "Realtime SSE stream connected.");
    };

    source.onerror = () => {
      source.close();
      this.source = null;
      if (this.stopped) return;
      this.attempts += 1;
      this.setState("degraded", "SSE stream interrupted; retrying WebSocket.");
      this.scheduleReconnect(() => this.connectWebSocket());
    };
  }

  private scheduleReconnect(connect: () => void): void {
    if (this.stopped) return;
    const delay = Math.min(MAX_BACKOFF_MS, BASE_BACKOFF_MS * 2 ** Math.min(this.attempts, 5));
    const jitter = delay * 0.2 * Math.random();
    this.setState("degraded", `Reconnecting in ${Math.round((delay + jitter) / 1000)}s...`);
    this.reconnectTimer = window.setTimeout(connect, delay + jitter);
  }

  private accept(event: RealtimeEvent): void {
    if (!event) return;
    this.lastMessageAt = Date.now();
    if (event.id && event.id > this.lastEventId) this.lastEventId = event.id;
    if (this.state !== "live") this.setState("live", "Realtime connection healthy.");
    this.listeners.forEach((listener) => listener(event));
  }
}
