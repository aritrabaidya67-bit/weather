/** Application shell: sidebar navigation, status header, mobile nav and global banners. */

import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  AlertTriangle,
  BrainCircuit,
  CloudOff,
  Cpu,
  LayoutDashboard,
  LineChart,
  ListChecks,
  Menu,
  Moon,
  RefreshCw,
  Settings,
  ShieldAlert,
  Sun,
  TrendingUp,
  Wifi,
  WifiOff,
  X,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { usePlatform } from "../../state/PlatformContext";
import { classNames, freshnessLabel, relativeTime, riskColor } from "../../utils/format";
import { DataBadge, Spinner, StatusDot, StatusPill } from "../common/Ui";

const NAV_ITEMS = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/sensors", label: "Sensors", icon: Activity },
  { to: "/analytics", label: "Analytics", icon: LineChart },
  { to: "/risk", label: "Risk", icon: ShieldAlert },
  { to: "/predictions", label: "Forecast", icon: TrendingUp },
  { to: "/alerts", label: "Alerts", icon: ListChecks },
  { to: "/device", label: "Hardware", icon: Cpu },
  { to: "/chat", label: "AI Analyst", icon: BrainCircuit },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function AppShell({ children }: { children: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  const {
    status,
    overview,
    connection,
    connectionDetail,
    refreshing,
    refresh,
    theme,
    toggleTheme,
    activeAlerts,
  } = useAppShellState();

  const fresh = freshnessLabel(overview?.latest?.received_at ?? null);
  const risk = overview?.risk;

  const connectionSeverity =
    connection === "live" ? "good" : connection === "degraded" ? "watch" : connection === "connecting" ? "info" : "critical";

  return (
    <div className="min-h-dvh bg-slate-100/70 dark:bg-slate-950">
      <div className="mx-auto flex w-full max-w-[1600px]">
        {/* Desktop sidebar */}
        <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col border-r border-slate-200/80 bg-white/80 px-3 py-5 backdrop-blur lg:flex dark:border-slate-800/80 dark:bg-slate-900/50">
          <SidebarContent />
        </aside>

        {/* Mobile drawer */}
        <AnimatePresence>
          {mobileOpen ? (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-40 bg-slate-950/50 lg:hidden"
              onClick={() => setMobileOpen(false)}
            >
              <motion.aside
                initial={{ x: -280 }}
                animate={{ x: 0 }}
                exit={{ x: -280 }}
                transition={{ type: "spring", stiffness: 320, damping: 32 }}
                className="h-full w-64 border-r border-slate-200 bg-white px-3 py-5 dark:border-slate-800 dark:bg-slate-900"
                onClick={(event) => event.stopPropagation()}
              >
                <div className="mb-3 flex justify-end">
                  <button
                    type="button"
                    aria-label="Close navigation"
                    className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
                    onClick={() => setMobileOpen(false)}
                  >
                    <X size={16} />
                  </button>
                </div>
                <SidebarContent onNavigate={() => setMobileOpen(false)} />
              </motion.aside>
            </motion.div>
          ) : null}
        </AnimatePresence>

        <div className="flex min-w-0 flex-1 flex-col">
          {/* Header */}
          <header className="sticky top-0 z-30 border-b border-slate-200/80 bg-white/85 backdrop-blur dark:border-slate-800/80 dark:bg-slate-950/80">
            <div className="flex flex-wrap items-center gap-2 px-4 py-3">
              <button
                type="button"
                aria-label="Open navigation"
                className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 lg:hidden dark:hover:bg-slate-800"
                onClick={() => setMobileOpen(true)}
              >
                <Menu size={18} />
              </button>

              <div className="mr-auto min-w-0">
                <h1 className="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">
                  {navTitle(location.pathname)}
                </h1>
                <p className="truncate text-[11px] text-slate-500 dark:text-slate-400">
                  {overview?.classification?.label ?? "Waiting for the first reading"}
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-1.5">
                <DataBadge source={overview?.data_source} />
                <StatusPill
                  label={
                    status?.device_online
                      ? "Device online"
                      : overview?.has_data
                        ? "Device offline"
                        : "Waiting for device"
                  }
                  detail={status?.device_online ? `payload ${fresh.label}` : undefined}
                  severity={status?.device_online ? "good" : "critical"}
                  pulse={Boolean(status?.device_online)}
                />
                <StatusPill
                  label={connection === "live" ? "Realtime" : connection === "degraded" ? "Degraded" : connection === "connecting" ? "Connecting" : "Offline"}
                  detail={connection === "degraded" || connection === "offline" ? connectionDetail : undefined}
                  severity={connectionSeverity}
                  pulse={connection === "live"}
                />
                {risk && overview?.has_data ? (
                  <span
                    className="hidden items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium sm:inline-flex"
                    style={{ borderColor: `${riskColor(risk.level)}66`, color: riskColor(risk.level) }}
                    title={`Risk ${risk.score.toFixed(0)}/100`}
                  >
                    <StatusDot severity={risk.level >= 4 ? "critical" : risk.level === 3 ? "watch" : "good"} />
                    {risk.label}
                  </span>
                ) : null}
                {activeAlerts > 0 ? (
                  <NavLink
                    to="/alerts"
                    className="inline-flex items-center gap-1.5 rounded-full border border-rose-500/40 bg-rose-500/10 px-3 py-1 text-xs font-medium text-rose-600 dark:text-rose-300"
                  >
                    <AlertTriangle size={12} />
                    {activeAlerts} active
                  </NavLink>
                ) : null}
                <button
                  type="button"
                  onClick={() => void refresh()}
                  className="rounded-lg border border-slate-200 p-1.5 text-slate-500 transition hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
                  aria-label="Refresh data"
                  title={`Last updated ${relativeTime(overview?.server_time)}`}
                >
                  {refreshing ? <Spinner /> : <RefreshCw size={15} />}
                </button>
                <button
                  type="button"
                  onClick={toggleTheme}
                  className="rounded-lg border border-slate-200 p-1.5 text-slate-500 transition hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
                  aria-label="Toggle theme"
                >
                  {theme === "dark" ? <Sun size={15} /> : <Moon size={15} />}
                </button>
              </div>
            </div>

            {(connection === "offline" || (overview?.stale && overview?.has_data)) && (
              <div
                className={classNames(
                  "flex items-center gap-2 px-4 py-2 text-xs",
                  connection === "offline"
                    ? "bg-rose-500/10 text-rose-700 dark:text-rose-300"
                    : "bg-amber-500/10 text-amber-700 dark:text-amber-300",
                )}
              >
                {connection === "offline" ? <CloudOff size={13} /> : <WifiOff size={13} />}
                {connection === "offline"
                  ? "Backend unreachable - showing the last data this page received."
                  : "The latest reading is stale: the device may be offline or between transmissions."}
              </div>
            )}
          </header>

          <main className="min-w-0 flex-1 px-4 py-5 pb-24 lg:pb-8">{children}</main>
        </div>
      </div>

      <MobileNav />
    </div>
  );
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { meta, status } = usePlatform();
  return (
    <>
      <div className="mb-5 px-2">
        <div className="flex items-center gap-2">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-cyan-500 to-sky-600 text-white shadow-sm">
            <Activity size={18} />
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">
              Environmental IQ
            </p>
            <p className="truncate text-[11px] text-slate-500 dark:text-slate-400">
              Arduino R4 · {meta?.environment ?? "development"}
            </p>
          </div>
        </div>
      </div>
      <nav className="flex-1 space-y-0.5">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            onClick={onNavigate}
            className={({ isActive }) =>
              classNames(
                "flex items-center gap-2.5 rounded-xl px-3 py-2 text-sm transition",
                isActive
                  ? "bg-slate-900 text-white shadow-sm dark:bg-cyan-500/15 dark:text-cyan-200"
                  : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800/70",
              )
            }
          >
            <item.icon size={16} />
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div className="mt-4 space-y-2 px-2 text-[11px] text-slate-500 dark:text-slate-400">
        <div className="flex items-center gap-1.5">
          <Wifi size={12} />
          <span>API {meta?.version ?? "—"} · {meta?.api_version ?? "v1"}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <StatusDot severity={status?.ollama?.available ? "good" : "unknown"} />
          <span>AI: {status?.ollama?.available ? status.ollama.model : "unavailable"}</span>
        </div>
      </div>
    </>
  );
}

function MobileNav() {
  const items = NAV_ITEMS.slice(0, 5);
  return (
    <nav className="fixed bottom-0 left-0 right-0 z-30 border-t border-slate-200 bg-white/95 px-2 py-1.5 backdrop-blur lg:hidden dark:border-slate-800 dark:bg-slate-950/95">
      <ul className="flex items-center justify-between">
        {items.map((item) => (
          <li key={item.to} className="flex-1">
            <NavLink
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                classNames(
                  "flex flex-col items-center gap-0.5 rounded-lg py-1.5 text-[10px] font-medium",
                  isActive ? "text-cyan-600 dark:text-cyan-300" : "text-slate-500 dark:text-slate-400",
                )
              }
            >
              <item.icon size={18} />
              {item.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}

function navTitle(pathname: string): string {
  if (pathname === "/") return "Realtime environmental overview";
  if (pathname.startsWith("/sensors/")) {
    return `Sensor detail · ${pathname.split("/").pop()}`;
  }
  const match = NAV_ITEMS.find((item) => item.to !== "/" && pathname.startsWith(item.to));
  return match ? match.label : "Environmental Intelligence Platform";
}

/** Small selector hook kept separate so the shell stays readable. */
function useAppShellState() {
  const platform = usePlatform();
  return {
    ...platform,
    activeAlerts: platform.status?.active_alerts ?? platform.overview?.active_alert_count ?? 0,
  };
}

