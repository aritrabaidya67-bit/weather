/**
 * Application shell.
 *
 * Deliberately quiet: a brand mark, an icon-led rail, one live indicator, and
 * the theme/refresh controls. Status detail lives in the page content, not in a
 * row of pills competing with it.
 */

import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  AlertTriangle,
  BrainCircuit,
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
  X,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { usePlatform } from "../../state/PlatformContext";
import { classNames, freshnessLabel } from "../../utils/format";
import { Spinner } from "../common/Ui";

const NAV_ITEMS = [
  { to: "/", label: "Overview", icon: LayoutDashboard },
  { to: "/sensors", label: "Sensors", icon: Activity },
  { to: "/analytics", label: "Analytics", icon: LineChart },
  { to: "/risk", label: "Risk", icon: ShieldAlert },
  { to: "/predictions", label: "Forecast", icon: TrendingUp },
  { to: "/alerts", label: "Alerts", icon: ListChecks },
  { to: "/device", label: "Hardware", icon: Cpu },
  { to: "/chat", label: "Assistant", icon: BrainCircuit },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function AppShell({ children }: { children: ReactNode }) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const location = useLocation();
  const { status, overview, connection, refreshing, refresh, theme, toggleTheme } = usePlatform();

  const fresh = freshnessLabel(overview?.latest?.received_at ?? null);
  const deviceOnline = Boolean(status?.device_online);
  const alerts = status?.active_alerts ?? overview?.active_alert_count ?? 0;

  return (
    <div className="min-h-dvh bg-slate-100/60 dark:bg-slate-950">
      <div className="mx-auto flex w-full max-w-[1560px]">
        {/* Desktop rail */}
        <aside className="sticky top-0 hidden h-dvh w-[4.5rem] shrink-0 flex-col items-center gap-1 border-r border-slate-200/70 bg-white/70 py-4 backdrop-blur xl:flex dark:border-slate-800/70 dark:bg-slate-900/40">
          <BrandMark />
          <nav className="mt-4 flex flex-1 flex-col items-center gap-1">
            {NAV_ITEMS.map((item) => (
              <RailLink key={item.to} {...item} />
            ))}
          </nav>
          <ConnectionDot connection={connection} label={`${fresh.label}`} />
        </aside>

        <AnimatePresence>
          {drawerOpen ? (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-40 bg-slate-950/50 xl:hidden"
              onClick={() => setDrawerOpen(false)}
            >
              <motion.aside
                initial={{ x: -280 }}
                animate={{ x: 0 }}
                exit={{ x: -280 }}
                transition={{ type: "spring", stiffness: 340, damping: 34 }}
                className="h-full w-64 border-r border-slate-200 bg-white px-3 py-4 dark:border-slate-800 dark:bg-slate-900"
                onClick={(event) => event.stopPropagation()}
              >
                <div className="mb-4 flex items-center justify-between px-1">
                  <span className="flex items-center gap-2 text-sm font-semibold">Environmental IQ</span>
                  <button
                    type="button"
                    aria-label="Close navigation"
                    className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
                    onClick={() => setDrawerOpen(false)}
                  >
                    <X size={16} />
                  </button>
                </div>
                <nav className="space-y-0.5">
                  {NAV_ITEMS.map((item) => (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      end={item.to === "/"}
                      onClick={() => setDrawerOpen(false)}
                      className={({ isActive }) =>
                        classNames(
                          "rail-item",
                          isActive
                            ? "bg-slate-900 text-white dark:bg-cyan-500/15 dark:text-cyan-200"
                            : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800/70",
                        )
                      }
                    >
                      <item.icon size={16} />
                      {item.label}
                    </NavLink>
                  ))}
                </nav>
              </motion.aside>
            </motion.div>
          ) : null}
        </AnimatePresence>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-30 border-b border-slate-200/70 bg-white/75 backdrop-blur-xl dark:border-slate-800/70 dark:bg-slate-950/75">
            <div className="flex items-center gap-3 px-4 py-2.5">
              <button
                type="button"
                aria-label="Open navigation"
                className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 xl:hidden dark:hover:bg-slate-800"
                onClick={() => setDrawerOpen(true)}
              >
                <Menu size={18} />
              </button>

              <div className="mr-auto min-w-0">
                <h1 className="truncate text-sm font-semibold tracking-tight text-slate-900 dark:text-slate-100">
                  {navTitle(location.pathname)}
                </h1>
                <p className="flex items-center gap-1.5 truncate text-[11px] text-slate-500 dark:text-slate-400">
                  <span
                    className={classNames(
                      "inline-block h-1.5 w-1.5 rounded-full",
                      deviceOnline ? "bg-emerald-500" : "bg-slate-400",
                    )}
                  />
                  {deviceOnline ? `live · ${fresh.label}` : overview?.has_data ? `device offline · last ${fresh.label}` : "waiting for device"}
                </p>
              </div>

              <div className="flex items-center gap-1.5">
                <span
                  className={classNames(
                    "inline-flex items-center gap-1.5 rounded-full border px-1.5 py-1 text-[11px] font-medium sm:px-2.5",
                    connection === "live"
                      ? "border-emerald-500/40 bg-emerald-500/5 text-emerald-700 dark:text-emerald-300"
                      : connection === "connecting"
                        ? "border-sky-500/40 bg-sky-500/5 text-sky-700 dark:text-sky-300"
                        : "border-amber-500/40 bg-amber-500/5 text-amber-700 dark:text-amber-300",
                  )}
                  title={connection === "live" ? "WebSocket stream connected" : "Falling back to polling"}
                >
                  <span className="relative flex h-1.5 w-1.5">
                    {connection === "live" ? (
                      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-70" />
                    ) : null}
                    <span
                      className={classNames(
                        "relative inline-flex h-1.5 w-1.5 rounded-full",
                        connection === "live" ? "bg-emerald-500" : "bg-amber-500",
                      )}
                    />
                  </span>
                  <span className="hidden sm:inline">
                    {connection === "live" ? "LIVE" : connection === "connecting" ? "CONNECTING" : "POLLING"}
                  </span>
                </span>

                {alerts > 0 ? (
                  <NavLink
                    to="/alerts"
                    className="inline-flex items-center gap-1.5 rounded-full border border-rose-500/40 bg-rose-500/5 px-2.5 py-1 text-[11px] font-semibold text-rose-600 dark:text-rose-300"
                  >
                    <AlertTriangle size={12} />
                    {alerts}
                  </NavLink>
                ) : null}

                <button
                  type="button"
                  onClick={() => void refresh()}
                  className="rounded-lg border border-slate-200 p-1.5 text-slate-500 transition hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
                  aria-label="Refresh data"
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
                  "flex items-center gap-2 px-4 py-1.5 text-[11px]",
                  connection === "offline"
                    ? "bg-rose-500/10 text-rose-700 dark:text-rose-300"
                    : "bg-amber-500/10 text-amber-700 dark:text-amber-300",
                )}
              >
                <AlertTriangle size={12} aria-hidden />
                {connection === "offline"
                  ? "Backend unreachable — showing the last data this page received."
                  : "Latest reading is stale — the node may be offline or between transmissions."}
              </div>
            )}
          </header>

          <main className="min-w-0 flex-1 px-4 py-4 pb-24 xl:pb-6">{children}</main>
        </div>
      </div>

      <MobileNav />
    </div>
  );
}

function BrandMark() {
  return (
    <NavLink
      to="/"
      className="grid h-10 w-10 place-items-center rounded-2xl bg-gradient-to-br from-cyan-500 to-sky-600 text-white shadow-sm"
      aria-label="Environmental IQ home"
    >
      <Activity size={18} />
    </NavLink>
  );
}

function RailLink({ to, label, icon: Icon }: { to: string; label: string; icon: typeof Activity }) {
  return (
    <NavLink
      to={to}
      end={to === "/"}
      title={label}
      aria-label={label}
      className={({ isActive }) =>
        classNames(
          "group relative grid h-10 w-10 place-items-center rounded-xl transition-colors",
          isActive
            ? "bg-slate-900 text-white dark:bg-cyan-500/15 dark:text-cyan-200"
            : "text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:text-slate-400 dark:hover:bg-slate-800/70 dark:hover:text-slate-100",
        )
      }
    >
      <Icon size={17} />
      <span className="pointer-events-none absolute left-12 z-20 hidden whitespace-nowrap rounded-lg bg-slate-900 px-2 py-1 text-[11px] font-medium text-white shadow-lg group-hover:block dark:bg-slate-800">
        {label}
      </span>
    </NavLink>
  );
}

function ConnectionDot({ connection, label }: { connection: string; label: string }) {
  return (
    <span
      className="flex flex-col items-center gap-1 text-[10px] text-slate-400"
      title={`${connection} · ${label}`}
    >
      <span className="relative flex h-2 w-2">
        {connection === "live" ? (
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-70" />
        ) : null}
        <span
          className={classNames(
            "relative inline-flex h-2 w-2 rounded-full",
            connection === "live" ? "bg-emerald-500" : "bg-amber-500",
          )}
        />
      </span>
      {connection === "live" ? "live" : "degraded"}
    </span>
  );
}

function MobileNav() {
  const items = NAV_ITEMS.slice(0, 5);
  return (
    <nav className="fixed bottom-0 left-0 right-0 z-30 border-t border-slate-200 bg-white/95 px-2 py-1.5 backdrop-blur xl:hidden dark:border-slate-800 dark:bg-slate-950/95">
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
  if (pathname === "/") return "Overview";
  if (pathname.startsWith("/sensors/")) {
    const key = pathname.split("/").pop() ?? "";
    return key.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
  }
  const match = NAV_ITEMS.find((item) => item.to !== "/" && pathname.startsWith(item.to));
  return match ? match.label : "Environmental Intelligence Platform";
}
