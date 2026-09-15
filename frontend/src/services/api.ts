/**
 * Typed API client.
 *
 * The browser only ever talks to the FastAPI backend; no secret is embedded here
 * (device authentication lives on the Arduino side). By default the
 * client uses same-origin `/api/v1` URLs, which the Vite dev server proxies to
 * the backend, so there is no CORS configuration to get wrong locally. Set
 * VITE_API_BASE_URL to point at another host when needed.
 */

import type {
  Alert,
  AlertList,
  AlertRule,
  DeviceStatus,
  HistoryResponse,
  MetaResponse,
  OllamaStatus,
  Overview,
  PredictionAccuracy,
  PredictionResponse,
  RiskAssessment,
  RiskModel,
  RiskState,
  SensorHealth,
  SummaryResponse,
  SystemStatus,
  WorkerStatus,
} from "../types";

export const API_BASE_URL: string = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "";
export const API_PREFIX = `${API_BASE_URL}/api/v1`;

export class ApiError extends Error {
  status: number;
  detail: string;
  fieldErrors: { field: string; reason: string }[];

  constructor(status: number, detail: string, fieldErrors: { field: string; reason: string }[] = []) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.fieldErrors = fieldErrors;
  }

  get isOffline(): boolean {
    return this.status === 0;
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }
}

const DEFAULT_TIMEOUT_MS = 20_000;

async function request<T>(path: string, init: RequestInit = {}, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${API_PREFIX}${path}`, {
      ...init,
      headers: { Accept: "application/json", ...(init.headers ?? {}) },
      signal: controller.signal,
    });
    const text = await response.text();
    const payload = text ? safeJson(text) : null;
    if (!response.ok) {
      const detail =
        (payload && (payload.detail || payload.error || payload.message)) ||
        `Request failed with status ${response.status}`;
      const fieldErrors = (payload?.field_errors as { field: string; reason: string }[]) ?? [];
      throw new ApiError(response.status, String(detail), fieldErrors);
    }
    return payload as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError(408, "The backend took too long to respond. It may still be processing.");
    }
    throw new ApiError(
      0,
      "Cannot reach the backend API. Check that uvicorn is running and that the API base URL is correct.",
    );
  } finally {
    window.clearTimeout(timer);
  }
}

function safeJson(text: string): any {
  try {
    return JSON.parse(text);
  } catch {
    return { detail: text.slice(0, 300) };
  }
}

function query(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") return;
    search.set(key, String(value));
  });
  const rendered = search.toString();
  return rendered ? `?${rendered}` : "";
}

export const api = {
  meta: () => request<MetaResponse>("/meta"),
  health: () => request<Record<string, unknown>>("/health", {}, 8_000),
  status: () => request<SystemStatus>("/status", {}, 10_000),
  workers: () => request<WorkerStatus>("/system/workers", {}, 10_000),

  overview: (deviceId?: string, hours = 6) =>
    request<Overview>(`/analytics/overview${query({ device_id: deviceId, hours })}`),

  history: (params: { device_id?: string; hours?: number; bucket?: string; metrics?: string; limit?: number }) =>
    request<HistoryResponse>(`/sensors/history${query(params)}`),

  aggregates: (params: { device_id?: string; hours?: number; bucket?: string }) =>
    request<{ device_id: string; points: Record<string, number | string | null>[] }>(
      `/sensors/aggregate${query(params)}`,
    ),

  summary: (period: "day" | "week", deviceId?: string) =>
    request<SummaryResponse>(`/analytics/summary/${period}${query({ device_id: deviceId })}`),

  trends: (deviceId?: string, hours = 6) =>
    request<{ metrics: Record<string, Record<string, unknown>>; trend_context: Record<string, number | null> }>(
      `/analytics/trends${query({ device_id: deviceId, hours })}`,
    ),

  observations: (deviceId?: string, hours = 6) =>
    request<{ observations: { id: string; kind: string; importance: string; text: string; evidence: Record<string, unknown> }[]; notes: string[] }>(
      `/analytics/observations${query({ device_id: deviceId, hours })}`,
    ),

  compare: (deviceId?: string, hours = 6) =>
    request<{ metrics: Record<string, { label: string; unit: string; current_mean: number | null; previous_mean: number | null; delta: number | null; message: string; sufficient_comparison: boolean }> }>(
      `/analytics/compare${query({ device_id: deviceId, hours })}`,
    ),

  classification: (deviceId?: string) =>
    request<{ classification: { label: string }; heat_index_c: number | null; dew_point_c: number | null; has_data: boolean }>(
      `/analytics/classification${query({ device_id: deviceId })}`,
    ),

  anomalies: (deviceId?: string, hours = 6) =>
    request<{
      count: number;
      severity_counts: Record<string, number>;
      anomalies: import("../types").Anomaly[];
      baseline_ready: boolean;
      notes: string[];
    }>(`/sensors/anomalies${query({ device_id: deviceId, hours })}`),

  baseline: (deviceId?: string) =>
    request<{
      metrics: Record<string, { mean: number | null; median: number | null; sigma: number | null; samples: number }>;
      readiness: Record<string, number>;
      window_points: number;
      min_samples: number;
    }>(`/sensors/baseline${query({ device_id: deviceId })}`),

  riskCurrent: (deviceId?: string) => request<RiskAssessment>(`/risk/current${query({ device_id: deviceId })}`),
  riskModel: () => request<RiskModel>("/risk/model"),
  riskAnalysis: (deviceId?: string, hours = 6) =>
    request<{
      assessment: RiskAssessment;
      trend: { timestamp: string; score: number; level: number }[];
      trend_direction: string;
      trend_change: number | null;
      anomalies: import("../types").Anomaly[];
      alerts: Alert[];
      notes: string[];
    }>(`/risk/analysis${query({ device_id: deviceId, hours })}`),

  predictions: (deviceId?: string, horizons?: string) =>
    request<PredictionResponse>(`/predictions${query({ device_id: deviceId, horizons })}`),
  predictionAccuracy: (deviceId?: string) =>
    request<PredictionAccuracy>(`/predictions/accuracy${query({ device_id: deviceId })}`),
  predictionHistory: (deviceId?: string, limit = 30) =>
    request<{ count: number; records: Record<string, unknown>[] }>(
      `/predictions/history${query({ device_id: deviceId, limit })}`,
    ),

  alerts: (params: { device_id?: string; active_only?: boolean; severity?: string; limit?: number } = {}) =>
    request<AlertList>(`/alerts${query(params)}`),
  alertRules: () => request<AlertRule[]>("/alerts/rules"),
  acknowledgeAlert: (id: number) => request<{ success: boolean; alert: Alert }>(`/alerts/${id}/acknowledge`, { method: "POST" }),
  resolveAlert: (id: number) => request<{ success: boolean; alert: Alert }>(`/alerts/${id}/resolve`, { method: "POST" }),

  device: (deviceId?: string) => request<DeviceStatus>(`/device${query({ device_id: deviceId })}`),
  deviceList: () =>
    request<{ count: number; devices: DeviceStatus[]; primary_device_id: string; offline_message: string }>("/device/list"),
  deviceById: (deviceId: string) => request<DeviceStatus>(`/device/${deviceId}`),
  deviceRiskState: (deviceId: string) => request<RiskState>(`/device/${deviceId}/risk-state`),
  sensorHealth: (deviceId?: string) =>
    request<{ overall_health_score: number; sensors: SensorHealth[] }>(`/sensors/health${query({ device_id: deviceId })}`),
  sensorCatalog: () =>
    request<{ sensors: import("../types").SensorSpec[]; channels: import("../types").ChannelSpec[] }>("/sensors/catalog"),

  chatStatus: () => request<OllamaStatus>("/chat/status", {}, 8_000),
  chatSuggestions: (deviceId?: string) =>
    request<{ questions: string[] }>(`/chat/suggestions${query({ device_id: deviceId })}`),
  chatHistory: (sessionId: string) =>
    request<{ count: number; messages: Record<string, unknown>[] }>(`/chat/history/${sessionId}`),
  clearChatHistory: (sessionId: string) =>
    request<{ success: boolean }>(`/chat/history/${sessionId}`, { method: "DELETE" }),
};

export async function askChat(payload: {
  message: string;
  session_id?: string;
  device_id?: string;
  history?: { role: "user" | "assistant"; content: string }[];
}): Promise<import("../types").ChatResponse> {
  return request<import("../types").ChatResponse>("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }, 180_000);
}

/**
 * Streams an answer token by token from `POST /chat/stream`.
 * Falls back to the non-streaming endpoint if the browser lacks streams support.
 */
export async function streamChat(
  payload: {
    message: string;
    session_id?: string;
    device_id?: string;
    history?: { role: "user" | "assistant"; content: string }[];
  },
  handlers: {
    onMeta?: (detail: string) => void;
    onToken: (token: string) => void;
    onDone?: (info: { model?: string | null; detail?: string }) => void;
    onError?: (message: string) => void;
  },
): Promise<void> {
  const controller = new AbortController();
  let response: Response;
  try {
    response = await fetch(`${API_PREFIX}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/x-ndjson" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
  } catch {
    handlers.onError?.("Cannot reach the backend API.");
    return;
  }
  if (!response.ok || !response.body) {
    handlers.onError?.(`Chat stream failed with status ${response.status}.`);
    return;
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        let chunk: { type: string; content?: string; detail?: string; model?: string | null };
        try {
          chunk = JSON.parse(trimmed);
        } catch {
          continue;
        }
        if (chunk.type === "meta") handlers.onMeta?.(chunk.detail ?? "");
        else if (chunk.type === "token") handlers.onToken(chunk.content ?? "");
        else if (chunk.type === "error") handlers.onError?.(chunk.detail ?? "The model stream failed.");
        else if (chunk.type === "done") handlers.onDone?.({ model: chunk.model ?? null, detail: chunk.detail });
      }
    }
  } catch {
    handlers.onError?.("The response stream was interrupted.");
  } finally {
    reader.releaseLock();
  }
}

/** WebSocket URL for the realtime bus (proxied in dev, absolute in production).
 *
 * When REQUIRE_AUTH_FOR_READS is enabled on the backend, the browser WebSocket
 * API cannot set headers, so the realtime key travels as a query parameter and
 * is validated server-side like any other credential. It is supplied by the
 * operator through VITE_REALTIME_API_KEY (build-time, never a user secret
 * embedded per-session).
 */
export function realtimeUrl(topics: string[], lastEventId = 0): string {
  const explicit = import.meta.env.VITE_WS_URL as string | undefined;
  const base = explicit
    ? explicit.replace(/\/$/, "")
    : API_BASE_URL
      ? API_BASE_URL.replace(/^http/, "ws")
      : `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`;
  const apiKey = (import.meta.env.VITE_REALTIME_API_KEY as string | undefined) ?? "";
  return `${base}/api/v1/realtime/ws${query({ topics: topics.join(","), last_event_id: lastEventId, api_key: apiKey || undefined })}`;
}

export function sseUrl(topics: string[], lastEventId = 0): string {
  const apiKey = (import.meta.env.VITE_REALTIME_API_KEY as string | undefined) ?? "";
  return `${API_PREFIX}/realtime/events${query({ topics: topics.join(","), last_event_id: lastEventId, api_key: apiKey || undefined })}`;
}
