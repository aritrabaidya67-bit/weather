/** Presentation helpers: units, numbers, time and colour mapping. */

import type { Severity } from "../types";

/** Registry unit codes -> display symbols (registry keeps ASCII-safe codes). */
const UNIT_SYMBOLS: Record<string, string> = {
  degC: "°C",
  "%RH": "%RH",
  hPa: "hPa",
  ADC: "ADC",
  "%": "%",
  idx: "idx",
  lux: "lx",
};

export function unitSymbol(unit: string | null | undefined): string {
  if (!unit) return "";
  return UNIT_SYMBOLS[unit] ?? unit;
}

export function formatNumber(
  value: number | null | undefined,
  decimals = 1,
  fallback = "—",
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return fallback;
  return value.toFixed(decimals);
}

export function formatWithUnit(
  value: number | null | undefined,
  unit: string | null | undefined,
  decimals = 1,
): string {
  if (value === null || value === undefined) return "—";
  const symbol = unitSymbol(unit);
  return symbol ? `${value.toFixed(decimals)} ${symbol}` : value.toFixed(decimals);
}

export function formatSigned(value: number | null | undefined, decimals = 1, unit = ""): string {
  if (value === null || value === undefined) return "—";
  const sign = value > 0 ? "+" : "";
  const symbol = unitSymbol(unit);
  return `${sign}${value.toFixed(decimals)}${symbol ? ` ${symbol}` : ""}`;
}

export function formatPercent(value: number | null | undefined, decimals = 0): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(decimals)}%`;
}

export function relativeTime(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "never";
  const timestamp = new Date(iso).getTime();
  if (Number.isNaN(timestamp)) return "unknown";
  const seconds = Math.round((now - timestamp) / 1000);
  if (Math.abs(seconds) < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ${minutes % 60}m ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function secondsAgo(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "never";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${(seconds / 60).toFixed(1)} min`;
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)} h`;
  return `${(seconds / 86400).toFixed(1)} d`;
}

export function clockTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function axisTime(iso: string | number, rangeHours: number): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  if (rangeHours > 48) {
    return date.toLocaleDateString([], { month: "short", day: "numeric" });
  }
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/** Colour classes per severity, used by chips, borders and dots. */
export const SEVERITY_CLASSES: Record<Severity | string, string> = {
  good: "text-emerald-600 bg-emerald-500/10 border-emerald-500/30 dark:text-emerald-300",
  info: "text-sky-600 bg-sky-500/10 border-sky-500/30 dark:text-sky-300",
  watch: "text-amber-600 bg-amber-500/10 border-amber-500/30 dark:text-amber-300",
  warning: "text-orange-600 bg-orange-500/10 border-orange-500/30 dark:text-orange-300",
  critical: "text-rose-600 bg-rose-500/10 border-rose-500/30 dark:text-rose-300",
  unknown: "text-slate-500 bg-slate-500/10 border-slate-500/30 dark:text-slate-300",
};

export const SEVERITY_DOT: Record<string, string> = {
  good: "bg-emerald-500",
  info: "bg-sky-500",
  watch: "bg-amber-500",
  warning: "bg-orange-500",
  critical: "bg-rose-500",
  unknown: "bg-slate-400",
};

export const ALERT_CLASSES: Record<string, string> = {
  info: "border-sky-500/40 bg-sky-500/5",
  warning: "border-amber-500/40 bg-amber-500/5",
  critical: "border-rose-500/50 bg-rose-500/5",
};

export const RISK_LEVEL_COLORS: Record<number, string> = {
  1: "#22c55e",
  2: "#84cc16",
  3: "#eab308",
  4: "#f97316",
  5: "#ef4444",
};

export function riskColor(level: number | null | undefined): string {
  if (!level) return "#64748b";
  return RISK_LEVEL_COLORS[level] ?? "#64748b";
}

export function trendGlyph(trend: string | null | undefined): string {
  switch (trend) {
    case "rising":
      return "↑";
    case "falling":
      return "↓";
    case "stable":
      return "→";
    default:
      return "•";
  }
}

export function trendClass(trend: string | null | undefined): string {
  switch (trend) {
    case "rising":
      return "text-orange-500 dark:text-orange-400";
    case "falling":
      return "text-sky-500 dark:text-sky-400";
    case "stable":
      return "text-slate-500 dark:text-slate-400";
    default:
      return "text-slate-400";
  }
}

/** Compact "how stale is this" badge description. */
export function freshnessLabel(iso: string | null | undefined, staleAfterSeconds = 90): {
  label: string;
  stale: boolean;
} {
  if (!iso) return { label: "no data", stale: true };
  const ageSeconds = (Date.now() - new Date(iso).getTime()) / 1000;
  if (Number.isNaN(ageSeconds)) return { label: "unknown", stale: true };
  return { label: relativeTime(iso), stale: ageSeconds > staleAfterSeconds };
}

export function dataSourceLabel(source: string | null | undefined): string {
  switch (source) {
    case "simulation":
      return "SIMULATED";
    case "arduino":
      return "LIVE HARDWARE";
    case "api":
      return "API";
    case "manual":
      return "MANUAL";
    default:
      return "NO DATA";
  }
}

export function confidenceLabel(confidence: number | null | undefined): string {
  if (confidence === null || confidence === undefined) return "unknown";
  if (confidence >= 0.7) return "high";
  if (confidence >= 0.45) return "medium";
  return "low";
}

export function humanizeMethod(method: string | null | undefined): string {
  if (!method) return "unknown method";
  return method.replace(/_/g, " ");
}

export function decimalPlaces(value: number | null | undefined): number {
  if (value === null || value === undefined) return 0;
  return Math.abs(value) >= 100 ? 0 : Math.abs(value) >= 10 ? 1 : 2;
}

export function firstSentence(text: string): string {
  const match = text.match(/^[^.!?]*[.!?]/);
  return (match ? match[0] : text).trim();
}

export function classNames(...values: (string | false | null | undefined)[]): string {
  return values.filter(Boolean).join(" ");
}
