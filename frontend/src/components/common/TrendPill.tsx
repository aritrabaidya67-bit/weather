/**
 * Trend indicator: direction is carried by arrow + sign + colour together, so
 * it stays readable for colour-blind users and in greyscale.
 */

import { ArrowDownRight, ArrowRight, ArrowUpRight } from "lucide-react";
import type { TrendDirection } from "../../types";
import { classNames, formatSigned, unitSymbol } from "../../utils/format";

export function TrendPill({
  direction,
  change,
  unit,
  decimals = 1,
  compact = false,
  className,
}: {
  direction?: TrendDirection | null;
  change?: number | null;
  unit?: string | null;
  decimals?: number;
  compact?: boolean;
  className?: string;
}) {
  const resolved: TrendDirection = change === null || change === undefined ? "unknown" : (direction ?? "unknown");
  const Icon = resolved === "rising" ? ArrowUpRight : resolved === "falling" ? ArrowDownRight : ArrowRight;
  const tone =
    resolved === "rising"
      ? "text-orange-600 dark:text-orange-300"
      : resolved === "falling"
        ? "text-sky-600 dark:text-sky-300"
        : "text-slate-500 dark:text-slate-400";

  return (
    <span
      className={classNames(
        "inline-flex items-center gap-0.5 text-xs font-medium",
        tone,
        className,
      )}
      title={
        change === null || change === undefined
          ? "Not enough history for a trend yet"
          : `${formatSigned(change, decimals, unitSymbol(unit))} over the analysis window`
      }
    >
      <Icon size={compact ? 12 : 14} aria-hidden />
      {change === null || change === undefined ? (
        <span className="text-slate-400">steady</span>
      ) : (
        <span className="tabular">
          {formatSigned(change, decimals)}
          {unitSymbol(unit)}
        </span>
      )}
    </span>
  );
}
