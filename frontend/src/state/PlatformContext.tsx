/**
 * Platform state.
 *
 * One provider owns everything shared across pages: platform metadata, system
 * status, the dashboard overview, device status, active alerts and the latest
 * forecast. It merges in realtime events so the UI updates without refetching
 * whole pages, and it exposes an explicit connection state plus the reason, so
 * every page can render honest "offline / stale / simulated" states.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { ApiError, api } from "../services/api";
import { RealtimeClient, type ConnectionState } from "../services/realtime";
import type {
  Alert,
  Anomaly,
  DeviceStatus,
  MetaResponse,
  Overview,
  PredictionResponse,
  Reading,
  SystemStatus,
} from "../types";

interface PlatformState {
  meta: MetaResponse | null;
  status: SystemStatus | null;
  overview: Overview | null;
  device: DeviceStatus | null;
  predictions: PredictionResponse | null;
  alerts: Alert[];
  anomalies: Anomaly[];
  latestReading: Partial<Reading> | null;
  connection: ConnectionState;
  connectionDetail: string;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  backendReachable: boolean;
  deviceId: string | null;
  lastUpdated: string | null;
  theme: "dark" | "light";
  toggleTheme: () => void;
  refresh: (options?: { silent?: boolean }) => Promise<void>;
  setDeviceId: (deviceId: string) => void;
}

const PlatformContext = createContext<PlatformState | null>(null);

const POLL_INTERVAL_MS = 15_000; // safety net when the realtime bus is quiet
const LIVE_THROTTLE_MS = 1_000; // never re-render faster than this on live data

export function PlatformProvider({ children }: { children: ReactNode }) {
  const [meta, setMeta] = useState<MetaResponse | null>(null);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [device, setDevice] = useState<DeviceStatus | null>(null);
  const [predictions, setPredictions] = useState<PredictionResponse | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const [connectionDetail, setConnectionDetail] = useState("Connecting to the backend...");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [backendReachable, setBackendReachable] = useState(true);
  const [deviceId, setDeviceId] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [theme, setTheme] = useState<"dark" | "light">(
    document.documentElement.classList.contains("dark") ? "dark" : "light",
  );

  const clientRef = useRef<RealtimeClient | null>(null);
  const inFlight = useRef(false);
  const lastLiveAt = useRef(0);
  const pendingLive = useRef<number | null>(null);
  const deviceIdRef = useRef<string | null>(null);

  useEffect(() => {
    deviceIdRef.current = deviceId;
  }, [deviceId]);

  const toggleTheme = useCallback(() => {
    setTheme((current) => {
      const next = current === "dark" ? "light" : "dark";
      document.documentElement.classList.toggle("dark", next === "dark");
      window.localStorage.setItem("eip-theme", next);
      return next;
    });
  }, []);

  const loadAll = useCallback(async (options: { silent?: boolean } = {}) => {
    if (inFlight.current) return;
    inFlight.current = true;
    if (!options.silent) setRefreshing(true);
    try {
      const [metaResponse, statusResponse, overviewResponse, deviceResponse, alertsResponse, predictionResponse] =
        await Promise.all([
          api.meta().catch(() => null),
          api.status(),
          api.overview(deviceIdRef.current ?? undefined),
          api.device(deviceIdRef.current ?? undefined),
          api.alerts({ device_id: deviceIdRef.current ?? undefined, limit: 40 }),
          api.predictions(deviceIdRef.current ?? undefined).catch(() => null),
        ]);
      if (metaResponse) setMeta(metaResponse);
      setStatus(statusResponse);
      setBackendReachable(true);
      setError(null);
      if (overviewResponse.has_data) {
        setOverview(overviewResponse);
        setAlerts(alertsResponse.alerts);
        setDevice(deviceResponse);
      } else {
        // No data yet is a valid, expected state - not an error.
        setOverview(overviewResponse);
        setAlerts(alertsResponse.alerts);
        setDevice(deviceResponse);
      }
      if (predictionResponse) setPredictions(predictionResponse);
      setLastUpdated(new Date().toISOString());
    } catch (caught) {
      const apiError = caught instanceof ApiError ? caught : new ApiError(0, "Unexpected client error.");
      setBackendReachable(!apiError.isOffline);
      setError(apiError.detail);
      if (apiError.isOffline) {
        setConnection("offline");
        setConnectionDetail("Backend unreachable. Start FastAPI and reload.");
      }
    } finally {
      inFlight.current = false;
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  // Initial load.
  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  // Reload when the selected device changes (only meaningful in multi-device setups).
  useEffect(() => {
    if (deviceId) void loadAll({ silent: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deviceId]);

  // Polling safety net: the realtime bus carries the updates, this catches drift.
  useEffect(() => {
    const timer = window.setInterval(() => {
      void loadAll({ silent: true });
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [loadAll]);

  // Realtime subscription merged into the overview state.
  useEffect(() => {
    const client = new RealtimeClient();
    clientRef.current = client;
    const offState = client.onState((state, detail) => {
      setConnection(state);
      setConnectionDetail(detail);
    });
    const applyLive = () => {
      pendingLive.current = null;
      // Refresh the derived intelligence (risk, anomalies, observations, cards).
      void loadAll({ silent: true });
    };
    const offEvent = client.onEvent((event) => {
      const now = Date.now();
      if (event.topic === "reading") {
        setOverview((current) =>
          current
            ? {
                ...current,
                has_data: true,
                stale: false,
                data_source: (event.data.source as Overview["data_source"]) ?? current.data_source,
                latest: {
                  ...current.latest,
                  ...(event.data.metrics as Record<string, number | null>),
                  risk_score: (event.data.risk_score as number) ?? current.latest.risk_score,
                  risk_level: (event.data.risk_level as number) ?? current.latest.risk_level,
                  risk_label: (event.data.risk_label as string) ?? current.latest.risk_label,
                  timestamp: event.data.timestamp as string,
                  received_at: event.data.received_at as string,
                  anomalies: (event.data.anomalies as Anomaly[]) ?? [],
                },
                anomalies: (event.data.anomalies as Anomaly[]) ?? current.anomalies,
              }
            : current,
        );
        setStatus((current) =>
          current
            ? {
                ...current,
                device_online: true,
                reading_stale: false,
                device_last_seen_at: (event.data.received_at as string) ?? current.device_last_seen_at,
                device_seconds_since_payload: 0,
                data_source: (event.data.source as SystemStatus["data_source"]) ?? current.data_source,
              }
            : current,
        );
      } else if (event.topic === "risk") {
        setOverview((current) =>
          current
            ? {
                ...current,
                risk: {
                  ...current.risk,
                  ...(event.data as Partial<Overview["risk"]>),
                  contributions: (event.data.contributions as Overview["risk"]["contributions"]) ?? current.risk.contributions,
                },
              }
            : current,
        );
      } else if (event.topic === "alert") {
        const created = (event.data.alerts as Alert[] | undefined) ?? [];
        if (created.length) setAlerts((current) => [...created, ...current].slice(0, 60));
      } else if (event.topic === "device") {
        setStatus((current) =>
          current ? { ...current, device_online: Boolean(event.data.online), arduino: String(event.data.status ?? "") } : current,
        );
      }
      // Throttle the heavier refresh so a fast simulator cannot thrash the API.
      if (now - lastLiveAt.current > LIVE_THROTTLE_MS) {
        lastLiveAt.current = now;
        applyLive();
      } else if (pendingLive.current === null) {
        pendingLive.current = window.setTimeout(() => {
          lastLiveAt.current = Date.now();
          applyLive();
        }, LIVE_THROTTLE_MS);
      }
    });
    client.start();
    return () => {
      offEvent();
      offState();
      client.stop();
      clientRef.current = null;
      if (pendingLive.current) window.clearTimeout(pendingLive.current);
    };
  }, [loadAll]);

  const anomalies = useMemo(() => overview?.anomalies ?? [], [overview]);

  const value = useMemo<PlatformState>(
    () => ({
      meta,
      status,
      overview,
      device,
      predictions,
      alerts,
      anomalies,
      latestReading: overview?.latest ?? null,
      connection,
      connectionDetail,
      loading,
      refreshing,
      error,
      backendReachable,
      deviceId,
      lastUpdated,
      theme,
      toggleTheme,
      refresh: loadAll,
      setDeviceId,
    }),
    [
      meta,
      status,
      overview,
      device,
      predictions,
      alerts,
      anomalies,
      connection,
      connectionDetail,
      loading,
      refreshing,
      error,
      backendReachable,
      deviceId,
      lastUpdated,
      theme,
      toggleTheme,
      loadAll,
    ],
  );

  return <PlatformContext.Provider value={value}>{children}</PlatformContext.Provider>;
}

export function usePlatform(): PlatformState {
  const context = useContext(PlatformContext);
  if (!context) throw new Error("usePlatform must be used inside <PlatformProvider>.");
  return context;
}

/** Convenience hook for pages that only need the meta registry. */
export function useMeta(): MetaResponse | null {
  return usePlatform().meta;
}
