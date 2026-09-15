/**
 * Hardware Telemetry & Setup
 * Modern visual representation of device health and configuration.
 */

import { Cpu, Radio, Server, Wifi, Activity } from "lucide-react";
import { SensorHealthTable } from "../components/dashboard/Panels";
import { Chip, DataBadge, EmptyState, SectionHeaderPill, StatusDot } from "../components/common/Ui";
import { API_PREFIX } from "../services/api";
import { usePlatform } from "../state/PlatformContext";
import { relativeTime, secondsAgo } from "../utils/format";

export default function DevicePage() {
  const { device, meta, overview, deviceId } = usePlatform();

  const firmwareSnippet = `// arduino/environmental_monitor/config.h
#define WIFI_SSID        "YOUR_HOTSPOT_SSID"
#define WIFI_PASSWORD    "YOUR_WIFI_PASSWORD"
#define BACKEND_HOST     "192.168.1.50"   // LAN IP, NOT localhost
#define BACKEND_PORT     8000
#define API_KEY          "your-device-api-key"
#define DEVICE_ID        "arduino-r4-wifi-01"
#define SEND_INTERVAL_MS 15000`;

  return (
    <div className="space-y-6 animate-float-in">
      
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 panel p-5">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-2">
            <Cpu size={20} className="text-cyan-500" />
            Hardware & Telemetry
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Arduino UNO R4 node status and configuration.
          </p>
        </div>
        <DataBadge source={overview?.data_source} />
      </div>

      {!device ? (
        <div className="panel flex flex-col items-center justify-center p-12 text-center min-h-[50vh]">
          <div className="rounded-full bg-slate-100 p-4 dark:bg-surface-800 mb-6 text-slate-400">
            <Cpu size={32} />
          </div>
          <EmptyState
            title="Waiting for Arduino Connection"
            message="Ensure the node is powered, on Wi-Fi, and BACKEND_HOST is set to this machine's LAN IP. Check your firewall."
          />
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
          
          {/* Main Device Status */}
          <div className="space-y-6">
            <section className="panel p-6 sm:p-8 relative overflow-hidden">
              <div className="absolute right-0 top-0 w-64 h-64 bg-cyan-500/5 rounded-full filter blur-3xl translate-x-1/2 -translate-y-1/2" />
              
              <div className="flex items-start justify-between mb-8 relative z-10">
                <div>
                  <SectionHeaderPill icon={<Radio size={16} />} title="Device Status" className="mb-2" />
                  <h2 className="text-2xl font-bold text-slate-900 dark:text-white">{device.display_name ?? device.device_id}</h2>
                  <p className="text-xs font-mono text-slate-500 mt-1">{device.device_id}</p>
                </div>
                <Chip severity={device.online ? "good" : "critical"}>
                  <StatusDot severity={device.online ? "good" : "critical"} pulse={device.online} />
                  {device.online ? "ONLINE" : device.status.replace("_", " ").toUpperCase()}
                </Chip>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 relative z-10">
                <MetricBlock label="IP Address" value={device.ip_address ?? "—"} icon={<Wifi size={14} />} />
                <MetricBlock label="Signal (RSSI)" value={device.rssi ? `${device.rssi} dBm` : "—"} />
                <MetricBlock label="Uptime" value={device.uptime_human ?? "—"} />
                <MetricBlock label="Interval" value={`${device.transmission_interval_seconds ?? "—"}s`} />
                <MetricBlock label="Readings" value={String(device.total_readings)} />
                <MetricBlock label="Delivery Rate" value={device.estimated_delivery_rate_pct ? `${device.estimated_delivery_rate_pct}%` : "—"} />
              </div>
              
              <div className="mt-6 pt-4 border-t border-slate-200/50 dark:border-white/5 flex flex-wrap gap-4 text-[11px] text-slate-500">
                <span>Last seen: {relativeTime(device.last_payload_at)} ({secondsAgo(device.seconds_since_last_payload)}s ago)</span>
                <span>Firmware: {device.firmware_version ?? "unknown"}</span>
              </div>
            </section>

            {overview?.has_data && (
              <section className="panel p-6">
                <SectionHeaderPill icon={<Activity size={16} />} title="Sensor Health Detail" className="mb-4" />
                <SensorHealthTable sensors={overview.sensor_health} />
              </section>
            )}
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            <section className="panel p-6">
              <SectionHeaderPill icon={<Activity size={16} />} title="Sensor Availability" className="mb-6" />
              <div className="space-y-4">
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-2">Online Sensors ({device.sensors_available.length})</p>
                  <div className="flex flex-wrap gap-2">
                    {device.sensors_available.map(s => (
                      <Chip key={s} severity="info">{s.replace(/_/g, " ")}</Chip>
                    ))}
                    {!device.sensors_available.length && <span className="text-xs text-slate-400">None</span>}
                  </div>
                </div>
                {device.sensors_missing.length > 0 && (
                  <div>
                    <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-2">Missing/Offline ({device.sensors_missing.length})</p>
                    <div className="flex flex-wrap gap-2">
                      {device.sensors_missing.map(s => (
                        <Chip key={s} severity="critical">{s.replace(/_/g, " ")}</Chip>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </section>

            <section className="panel p-6">
              <SectionHeaderPill icon={<Server size={16} />} title="Firmware Setup" className="mb-4" />
              <div className="bg-slate-900 rounded-xl overflow-hidden shadow-inner mb-4">
                <div className="bg-slate-800/50 px-4 py-2 border-b border-white/10">
                  <span className="text-[10px] font-mono text-slate-400">config.h</span>
                </div>
                <pre className="p-4 text-[11px] font-mono leading-relaxed text-slate-300 overflow-x-auto">
                  {firmwareSnippet}
                </pre>
              </div>
              <ul className="space-y-2 text-[11px] text-slate-500 dark:text-slate-400">
                <li><strong className="text-slate-700 dark:text-slate-300">LAN IP:</strong> {(meta?.local_addresses ?? []).join(", ") || "none detected"}</li>
                <li><strong className="text-slate-700 dark:text-slate-300">API Endpoint:</strong> <code>{API_PREFIX}/sensors/data</code></li>
                <li><strong className="text-slate-700 dark:text-slate-300">Risk Endpoint:</strong> <code>{API_PREFIX}/device/{deviceId ?? "&lt;device&gt;"}/risk-state</code></li>
              </ul>
            </section>
          </div>

        </div>
      )}
    </div>
  );
}

function MetricBlock({ label, value, icon }: { label: string; value: string; icon?: React.ReactNode }) {
  return (
    <div className="bg-slate-50/50 dark:bg-surface-900/40 border border-slate-200/50 dark:border-white/5 rounded-xl p-3">
      <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-1">
        {icon} {label}
      </div>
      <div className="font-bold text-slate-800 dark:text-slate-200 tabular">{value}</div>
    </div>
  );
}
