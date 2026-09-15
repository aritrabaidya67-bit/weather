/**
 * Application shell.
 *
 * Designed to be extremely quiet and premium. A brand mark, an icon-led rail,
 * a subtle live indicator, and controls. The content should be the hero.
 */

import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  AlertTriangle,
  BrainCircuit,
  ChevronUp,
  Cpu,
  LayoutDashboard,
  LineChart,
  ListChecks,
  Moon,
  RefreshCw,
  Settings,
  ShieldAlert,
  Sun,
  TrendingUp,
} from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";
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
  { to: "/device", label: "Device", icon: Cpu },
  { to: "/chat", label: "Assistant", icon: BrainCircuit },
];

//: How many destinations the compact bottom bar shows before the rest move into
//: the overflow sheet. Keep this in sync with the row's width budget.
const MOBILE_PRIMARY_COUNT = 5;

const MOBILE_PRIMARY_ITEMS = NAV_ITEMS.slice(0, MOBILE_PRIMARY_COUNT);

/**
 * Destinations that the compact bar cannot fit.
 *
 * These used to be silently dropped below the `xl` breakpoint (the desktop rail
 * is `hidden ... xl:flex`), which left /alerts, /device and /chat - the AI
 * assistant included - with no navigation entry at all on a narrow window. They
 * are reachable now through the "More" sheet.
 */
const MOBILE_OVERFLOW_ITEMS = [
  ...NAV_ITEMS.slice(MOBILE_PRIMARY_COUNT),
  { to: "/settings", label: "Settings", icon: Settings },
];

export function AppShell({ children }: { children: ReactNode }) {
  const location = useLocation();
  const { status, overview, connection, refreshing, refresh, theme, toggleTheme } = usePlatform();

  const fresh = freshnessLabel(overview?.latest?.received_at ?? null);
  const deviceOnline = Boolean(status?.device_online);
  const alerts = status?.active_alerts ?? overview?.active_alert_count ?? 0;

  return (
    <div className="min-h-dvh bg-slate-50 dark:bg-surface-950 transition-colors duration-500">
      <div className="mx-auto flex w-full max-w-[1600px] h-dvh overflow-hidden">
        
        {/* Desktop Sidebar Rail */}
        <aside className="hidden h-full w-[5rem] shrink-0 flex-col items-center gap-2 border-r border-slate-200/50 bg-white/40 py-6 backdrop-blur-xl xl:flex dark:border-white/5 dark:bg-surface-900/40 relative z-40">
          <BrandMark />
          
          <nav className="mt-8 flex flex-1 flex-col items-center gap-3">
            {NAV_ITEMS.map((item) => (
              <RailLink key={item.to} {...item} />
            ))}
          </nav>
          
          <div className="flex flex-col items-center gap-3 mt-auto">
            <RailLink to="/settings" label="Settings" icon={Settings} />
            <div className="h-px w-8 bg-slate-200 dark:bg-white/10 my-1" />
            <ConnectionDot connection={connection} />
          </div>
        </aside>

        {/* Main Content Area */}
        <div className="flex min-w-0 flex-1 flex-col h-full relative overflow-y-auto overflow-x-hidden">
          
          {/* Top Header */}
          <header className="sticky top-0 z-30 flex items-center justify-between px-6 py-4 xl:px-10 xl:py-6">
            <div className="flex items-center gap-4">
              <div className="min-w-0">
                <h1 className="text-xl font-medium tracking-tight text-slate-900 dark:text-slate-100">
                  {navTitle(location.pathname)}
                </h1>
              </div>
              
              {/* Subtle Live Status */}
              <div className="hidden sm:flex items-center gap-2 px-3 py-1 rounded-full bg-white/60 border border-slate-200/60 backdrop-blur-md dark:bg-surface-900/50 dark:border-white/5">
                <span className="relative flex h-1.5 w-1.5">
                  {connection === "live" && <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-70" />}
                  <span className={classNames("relative inline-flex h-1.5 w-1.5 rounded-full", connection === "live" ? "bg-emerald-500" : "bg-amber-500")} />
                </span>
                <span className="text-[10px] font-medium tracking-wide uppercase text-slate-500 dark:text-slate-400">
                  {connection === "live" ? "Live" : connection === "connecting" ? "Connecting" : "Polling"}
                </span>
                <div className="w-px h-3 bg-slate-200 dark:bg-white/10 mx-1" />
                <span className="text-[10px] text-slate-400">{deviceOnline ? fresh.label : "Offline"}</span>
              </div>
            </div>

            <div className="flex items-center gap-2">
              {alerts > 0 && (
                <NavLink to="/alerts" className="inline-flex items-center gap-1.5 rounded-full border border-rose-500/20 bg-rose-500/10 px-3 py-1.5 text-xs font-medium text-rose-600 dark:text-rose-400 transition-colors hover:bg-rose-500/20">
                  <AlertTriangle size={14} />
                  {alerts}
                </NavLink>
              )}
              
              <button onClick={() => void refresh()} className="grid h-9 w-9 place-items-center rounded-full text-slate-400 hover:bg-slate-200/50 hover:text-slate-700 transition-colors dark:hover:bg-white/10 dark:hover:text-slate-200">
                {refreshing ? <Spinner /> : <RefreshCw size={16} />}
              </button>
              
              <button onClick={toggleTheme} className="grid h-9 w-9 place-items-center rounded-full text-slate-400 hover:bg-slate-200/50 hover:text-slate-700 transition-colors dark:hover:bg-white/10 dark:hover:text-slate-200">
                {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
              </button>
            </div>
          </header>

          {/* Page Content */}
          <main className="flex-1 px-4 sm:px-6 xl:px-10 pb-28 xl:pb-12 max-w-[1200px] w-full mx-auto">
            {children}
          </main>
        </div>
      </div>

      {/* Mobile Bottom Navigation */}
      <MobileNav />
    </div>
  );
}

function BrandMark() {
  return (
    <NavLink to="/" className="group relative grid h-12 w-12 place-items-center rounded-[1.25rem] bg-slate-900 text-white shadow-lg dark:bg-white dark:text-slate-900 overflow-hidden transition-transform hover:scale-105 active:scale-95">
      <div className="absolute inset-0 bg-gradient-to-tr from-cyan-500/40 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
      <Activity size={22} className="relative z-10" />
    </NavLink>
  );
}

function RailLink({ to, label, icon: Icon }: { to: string; label: string; icon: typeof Activity }) {
  return (
    <NavLink
      to={to}
      end={to === "/"}
      title={label}
      className={({ isActive }) =>
        classNames(
          "group relative flex h-12 w-12 items-center justify-center rounded-2xl transition-all duration-300",
          isActive
            ? "bg-slate-900 text-white shadow-md dark:bg-white/10 dark:text-cyan-300 dark:shadow-none"
            : "text-slate-400 hover:bg-slate-200/50 hover:text-slate-900 dark:hover:bg-white/5 dark:hover:text-slate-100"
        )
      }
    >
      <Icon size={20} strokeWidth={2} />
      <span className="pointer-events-none absolute left-14 z-50 hidden origin-left scale-95 whitespace-nowrap rounded-lg bg-slate-900/90 backdrop-blur px-3 py-1.5 text-xs font-medium text-white opacity-0 shadow-xl transition-all group-hover:block group-hover:scale-100 group-hover:opacity-100 dark:bg-surface-800/90 dark:border dark:border-white/10">
        {label}
      </span>
    </NavLink>
  );
}

function ConnectionDot({ connection }: { connection: string }) {
  return (
    <div className="grid h-10 w-10 place-items-center" title={`Connection: ${connection}`}>
      <span className="relative flex h-2.5 w-2.5">
        {connection === "live" && <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-70" />}
        <span className={classNames("relative inline-flex h-2.5 w-2.5 rounded-full shadow-[0_0_8px_rgba(0,0,0,0.2)]", connection === "live" ? "bg-emerald-500 shadow-emerald-500/50" : "bg-amber-500 shadow-amber-500/50")} />
      </span>
    </div>
  );
}

function MobileNav() {
  const items = MOBILE_PRIMARY_ITEMS;
  const { pathname } = useLocation();
  const [moreOpen, setMoreOpen] = useState(false);

  const overflowActive = MOBILE_OVERFLOW_ITEMS.some(
    (item) => item.to !== "/" && pathname.startsWith(item.to)
  );

  // Close the sheet whenever the route changes, so a tap on a destination does
  // not leave the panel floating over the page it just navigated to.
  useEffect(() => {
    setMoreOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!moreOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMoreOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [moreOpen]);

  return (
    <>
      <AnimatePresence>
        {moreOpen && (
          <motion.div
            key="mobile-nav-scrim"
            className="fixed inset-0 z-40 bg-slate-900/30 backdrop-blur-sm xl:hidden"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setMoreOpen(false)}
            aria-hidden="true"
          />
        )}
      </AnimatePresence>

      <nav
        className="fixed bottom-6 left-6 right-6 z-50 xl:hidden"
        aria-label="Primary"
      >
        <div className="mx-auto max-w-md rounded-2xl border border-slate-200/60 bg-white/80 p-2 shadow-2xl backdrop-blur-xl dark:border-white/10 dark:bg-surface-900/80">
          <AnimatePresence initial={false}>
            {moreOpen && (
              <motion.ul
                key="mobile-nav-overflow"
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.18, ease: "easeOut" }}
                className="overflow-hidden"
              >
                {MOBILE_OVERFLOW_ITEMS.map((item) => (
                  <li key={item.to}>
                    <NavLink
                      to={item.to}
                      end={item.to === "/"}
                      className={({ isActive }) =>
                        classNames(
                          "mb-1 flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors",
                          isActive
                            ? "bg-cyan-500/10 text-cyan-600 dark:text-cyan-300"
                            : "text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-white/5"
                        )
                      }
                    >
                      {({ isActive }) => (
                        <>
                          <item.icon size={18} strokeWidth={isActive ? 2.5 : 2} />
                          <span>{item.label}</span>
                        </>
                      )}
                    </NavLink>
                  </li>
                ))}
              </motion.ul>
            )}
          </AnimatePresence>

        <ul className="flex items-center justify-between">
          {items.map((item) => (
            <li key={item.to} className="flex-1">
              <NavLink
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  classNames(
                    "flex flex-col items-center gap-1 rounded-xl py-2 transition-all",
                    isActive 
                      ? "text-cyan-600 dark:text-cyan-300" 
                      : "text-slate-400 hover:bg-slate-100 dark:hover:bg-white/5"
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <motion.div animate={isActive ? { y: -2 } : { y: 0 }} transition={{ type: "spring", stiffness: 400, damping: 25 }}>
                      <item.icon size={20} strokeWidth={isActive ? 2.5 : 2} />
                    </motion.div>
                    {isActive && (
                      <motion.div layoutId="nav-pill" className="h-1 w-1 rounded-full bg-cyan-600 dark:bg-cyan-400" />
                    )}
                  </>
                )}
              </NavLink>
            </li>
          ))}
          <li className="flex-1">
            <button
              type="button"
              onClick={() => setMoreOpen((open) => !open)}
              aria-expanded={moreOpen}
              aria-haspopup="menu"
              aria-label="More destinations"
              className={classNames(
                "flex w-full flex-col items-center gap-1 rounded-xl py-2 transition-all",
                moreOpen || overflowActive
                  ? "text-cyan-600 dark:text-cyan-300"
                  : "text-slate-400 hover:bg-slate-100 dark:hover:bg-white/5"
              )}
            >
              <motion.div
                animate={moreOpen ? { rotate: 180 } : { rotate: 0 }}
                transition={{ type: "spring", stiffness: 400, damping: 25 }}
              >
                <ChevronUp size={20} strokeWidth={moreOpen || overflowActive ? 2.5 : 2} />
              </motion.div>
              {(moreOpen || overflowActive) && (
                <motion.div
                  layoutId="nav-pill"
                  className="h-1 w-1 rounded-full bg-cyan-600 dark:bg-cyan-400"
                />
              )}
            </button>
          </li>
        </ul>
      </div>
    </nav>
    </>
  );
}

function navTitle(pathname: string): string {
  if (pathname === "/") return "Overview";
  if (pathname.startsWith("/sensors/")) {
    const key = pathname.split("/").pop() ?? "";
    return key.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
  }
  const match = NAV_ITEMS.find((item) => item.to !== "/" && pathname.startsWith(item.to));
  if (match) return match.label;
  if (pathname === "/settings") return "Settings";
  return "Platform";
}
