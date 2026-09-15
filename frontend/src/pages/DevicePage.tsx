/** Hardware page: device telemetry, sensor availability and firmware setup hints. */

import { Activity, Cpu, Radio, Server, Wifi } from "lucide-react";
import { useEffect, useState } from "react";
import { SensorHealthTable } from "../components/dashboard/Panels";
import { Card, CardSkeleton, Chip, DataBadge, EmptyState, InlineNote, SectionHeader, StatusDot } from "../components/common/Ui";
import { api, API_PREFIX } from "../services/api";
import { usePlatform } from "../state/PlatformContext";
import type { WorkerStatus } from "../types";
import { relativeTime, secondsAgo } from "../utils/format";

export default function DevicePage() {
  const { device, meta, overview, status, deviceId } = usePlatform();
  const [workers, setWorkers] = useState<WorkerStatus | null>(null);

  const loadWorkers = () => {
    void api.workers().then(setWorkers).catch(() => setWorkers(null));
  };

  useEffect(() => {
    loadWorkers();
    const timer = window.setInterval(loadWorkers, 10_000);
    return () => window.clearInterval(timer);
  }, []);

  const firmwareSnippet = `// arduino/environmental_monitor/config.h (edit these, never commit real secrets)
#define WIFI_SSID        "YOUR_HOTSPOT_SSID"
#define WIFI_PASSWORD    "YOUR_WIFI_PASSWORD"
#define BACKEND_HOST     "192.168.1.50"   // laptop LAN/hotspot IP - NOT localhost
#define BACKEND_PORT     8000
#define API_KEY          "your-device-api-key"
#define DEVICE_ID        "arduino-r4-wifi-01"
#define SEND_INTERVAL_MS 15000`;

  return (
    <div className="space-y-5">
      <SectionHeader
        title="Hardware"
        subtitle="Arduino UNO R4 Wi-Fi node telemetry and sensor availability."
        icon={<Cpu size={16} />}
        action={<DataBadge source={overview?.data_source} />}
      />

      {!device ? (
        <Card>
          <EmptyState
            icon={<Cpu size={20} />}
            title="Waiting for the Arduino UNO R4 Wi-Fi"
            message="Power the node, confirm it joined the correct Wi-Fi network, set BACKEND_HOST to this machine's LAN IP (never localhost) and make sure the firewall allows the backend port."
          />
        </Card>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
          <Card>
            <SectionHeader
              title={device.display_name ?? device.device_id}
              subtitle={`${device.device_id} · ${device.source}`}
              icon={<Radio size={16} />}
              action={
                <Chip severity={device.online ? "good" : "critical"}>
                  <StatusDot severity={device.online ? "good" : "critical"} pulse={device.online} />
                  {device.online ? "online" : device.status.replace("_", " ")}
                </Chip>
              }
              className="mb-3"
            />
            <p className="text-sm text-slate-600 dark:text-slate-300">{device.status_message}</p>

            <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 text-xs sm:grid-cols-3">
              <Field label="Firmware" value={device.firmware_version ?? "not reported"} />
              <Field label="IP address" value={device.ip_address ?? "not reported"} icon={<Wifi size={11} />} />
              <Field
                label="Wi-Fi signal"
                value={device.rssi !== null ? `${device.rssi} dBm · ${device.rssi_quality}` : "not reported"}
                icon={<Wifi size={11} />}
              />
              <Field label="Last payload" value={relativeTime(device.last_payload_at)} />
              <Field label="Time since payload" value={`${secondsAgo(device.seconds_since_last_payload)} ago`} />
              <Field
                label="Transmit interval"
                value={`${device.transmission_interval_seconds ?? device.expected_interval_seconds ?? "—"} s`}
              />
              <Field label="Uptime" value={device.uptime_human ?? "not reported"} />
              <Field label="First seen" value={relativeTime(device.first_seen_at)} />
              <Field label="Readings stored" value={String(device.total_readings)} />
              <Field label="Rejected payloads" value={String(device.rejected_payloads)} />
              <Field label="Missed intervals" value={String(device.missed_intervals)} />
              <Field
                label="Delivery rate"
                value={device.estimated_delivery_rate_pct !== null ? `${device.estimated_delivery_rate_pct}%` : "—"}
              />
            </dl>

            {device.notes.length ? (
              <ul className="mt-3 space-y-1">
                {device.notes.map((note) => (
                  <li key={note} className="text-[11px] text-amber-600 dark:text-amber-400">
                    {note}
                  </li>
                ))}
              </ul>
            ) : null}
          </Card>

          <div className="space-y-4">
            <Card>
              <SectionHeader
                title="Sensor availability"
                subtitle={`${device.sensors_available.length} reporting · ${device.sensors_missing.length} missing`}
                className="mb-3"
              />
              <div className="flex flex-wrap gap-1.5">
                {device.sensors_available.map((sensor) => (
                  <Chip key={sensor} severity="good">
                    {sensor.replace(/_/g, " ")}
                  </Chip>
                ))}
                {device.sensors_missing.map((sensor) => (
                  <Chip key={sensor} severity="critical">
                    {sensor.replace(/_/g, " ")} · missing
                  </Chip>
                ))}
                {!device.sensors_available.length && !device.sensors_missing.length ? (
                  <span className="text-xs text-slate-500 dark:text-slate-400">No sensor metadata reported yet.</span>
                ) : null}
              </div>
              <InlineNote severity="info" className="mt-3">
                A missing sensor is recorded as <em>no value</em> rather than being filled in, so charts show a gap
                instead of a fabricated number.
              </InlineNote>
            </Card>

          </div>
        </div>
      )}

      {overview?.has_data ? (
        <Card>
          <SectionHeader title="Sensor health detail" subtitle="From the analytics service (rate, coverage, stuck detection)" icon={<Activity size={16} />} className="mb-3" />
          <SensorHealthTable sensors={overview.sensor_health} />
        </Card>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <SectionHeader title="Connect the Arduino" subtitle="This is the only configuration the firmware needs" icon={<Server size={16} />} className="mb-3" />
          <pre className="overflow-x-auto rounded-xl bg-slate-900 px-3 py-3 text-[11px] leading-relaxed text-slate-100 dark:bg-slate-950">
{firmwareSnippet}
          </pre>
          <ul className="mt-3 space-y-1 text-xs text-slate-600 dark:text-slate-300">
            <li>• LAN addresses detected by the backend: {(meta?.local_addresses ?? []).join(", ") || "none detected"}</li>
            <li>• Recommended backend URL for the firmware: {meta?.recommended_backend_url ?? "—"}</li>
            <li>• API endpoint the firmware posts to: <code>{API_PREFIX}/sensors/data</code></li>
            <li>• Risk state for the LEDs/buzzer: <code>{API_PREFIX}/device/{deviceId ?? "&lt;device&gt;"}/risk-state</code></li>
            <li>• The Arduino must never use localhost - that would refer to the Arduino itself.</li>
            <li>• Windows Firewall must allow inbound TCP on the backend port for private networks.</li>
          </ul>
        </Card>

        <Card>
          <SectionHeader title="Backend workers" subtitle="Watchdog, prediction snapshots, retention, Ollama probe" className="mb-3" />
          {workers ? (
            <div className="space-y-3 text-xs">
              <div className="flex flex-wrap gap-2">
                <Chip severity={workers.background.enabled ? "good" : "watch"}>
                  background {workers.background.enabled ? "enabled" : "disabled"}
                </Chip>
                <Chip severity="info">realtime subscribers {workers.realtime_subscribers}</Chip>
                <Chip severity="info">{workers.rules_loaded} alert rules</Chip>
              </div>
              <ul className="space-y-1 text-slate-600 dark:text-slate-300">
                {Object.entries(workers.background.last_runs).map(([job, time]) => (
                  <li key={job}>
                    • {job.replace(/_/g, " ")}: {relativeTime(time)}
                  </li>
                ))}
                {!Object.keys(workers.background.last_runs).length ? <li>No background job has run yet.</li> : null}
              </ul>
              <ul className="space-y-1 text-slate-500 dark:text-slate-400">
                {Object.entries(workers.background.counters).map(([key, value]) => (
                  <li key={key}>
                    {key.replace(/_/g, " ")}: <span className="tabular">{value}</span>
                  </li>
                ))}
              </ul>
              <div className="flex items-center gap-2 text-slate-500 dark:text-slate-400">
                <StatusDot severity={status?.ollama?.available ? "good" : "unknown"} />
                Ollama: {status?.ollama?.available ? status.ollama.model : status?.ollama?.detail ?? "unknown"}
              </div>
            </div>
          ) : (
            <CardSkeleton />
          )}
        </Card>
      </div>
    </div>
  );
}

function Field({ label, value, icon }: { label: string; value: string; icon?: React.ReactNode }) {
  return (
    <div>
      <dt className="flex items-center gap-1 text-[10px] uppercase tracking-wide text-slate-400">
        {icon}
        {label}
      </dt>
      <dd className="tabular font-medium text-slate-700 dark:text-slate-200">{value}</dd>
    </div>
  );
}
