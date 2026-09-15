/** Shared UI primitives: cards, badges, states, indicators. */

import { motion } from "framer-motion";
import type { ReactNode } from "react";
import { AlertTriangle, Database, Info, Loader2, Radio, TrendingUp } from "lucide-react";
import { SEVERITY_CLASSES, SEVERITY_DOT, classNames, dataSourceLabel } from "../../utils/format";

export function Card({
  children,
  className,
  as = "div",
}: {
  children: ReactNode;
  className?: string;
  as?: "div" | "section" | "article";
}) {
  const Component = as;
  return (
    <Component className={classNames("panel p-5", className)}>
      {children}
    </Component>
  );
}

export function SectionHeader({
  title,
  subtitle,
  icon,
  action,
  className,
}: {
  title: string;
  subtitle?: string;
  icon?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={classNames("mb-4 flex items-start justify-between gap-4", className)}>
      <div className="flex items-start gap-3">
        {icon ? (
          <span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-slate-900/5 text-slate-600 dark:bg-white/5 dark:text-slate-300">
            {icon}
          </span>
        ) : null}
        <div>
          <h2 className="text-base font-semibold tracking-tight text-slate-900 dark:text-slate-100">{title}</h2>
          {subtitle ? (
            <p className="mt-0.5 max-w-2xl text-sm text-slate-500 dark:text-slate-400">{subtitle}</p>
          ) : null}
        </div>
      </div>
      {action}
    </div>
  );
}

export function Chip({
  children,
  severity = "unknown",
  className,
}: {
  children: ReactNode;
  severity?: string;
  className?: string;
  /**
   * Marker so TypeScript keeps this signature in the public surface; chips are
   * used with and without extra classes across pages.
   */
}) {
  return (
    <span
      className={classNames(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize",
        SEVERITY_CLASSES[severity] ?? SEVERITY_CLASSES.unknown,
        className,
      )}
    >
      {children}
    </span>
  );
}

export function StatusDot({ severity, pulse = false }: { severity: string; pulse?: boolean }) {
  return (
    <span className="relative inline-flex h-2.5 w-2.5">
      {pulse ? (
        <span
          className={classNames(
            "absolute inline-flex h-full w-full animate-ping rounded-full opacity-60",
            SEVERITY_DOT[severity] ?? SEVERITY_DOT.unknown,
          )}
        />
      ) : null}
      <span
        className={classNames(
          "relative inline-flex h-2.5 w-2.5 rounded-full",
          SEVERITY_DOT[severity] ?? SEVERITY_DOT.unknown,
        )}
      />
    </span>
  );
}

export function StatusPill({
  label,
  detail,
  severity,
  pulse,
  className,
}: {
  label: string;
  detail?: string;
  severity: string;
  pulse?: boolean;
  className?: string;
}) {
  return (
    <div
      className={classNames(
        "inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium",
        SEVERITY_CLASSES[severity] ?? SEVERITY_CLASSES.unknown,
        className,
      )}
      title={detail}
    >
      <StatusDot severity={severity} pulse={pulse} />
      <span>{label}</span>
      {detail ? <span className="hidden text-[11px] font-normal opacity-80 sm:inline">{detail}</span> : null}
    </div>
  );
}

/** Data-provenance badge: the UI never presents predicted values as measured facts. */
export function DataBadge({
  source,
  predicted = false,
  className,
}: {
  source?: string | null;
  predicted?: boolean;
  className?: string;
}) {
  const label = predicted ? "PREDICTED" : dataSourceLabel(source);
  const Icon = predicted ? TrendingUp : source === "arduino" ? Radio : Database;
  const severity = predicted ? "info" : source === "arduino" ? "good" : "unknown";
  return (
    <span
      className={classNames(
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[10px] font-semibold tracking-wider",
        SEVERITY_CLASSES[severity],
        className,
      )}
      title={
        predicted
          ? "Statistical estimate - not a measured value."
          : "Values received from the edge device."
      }
    >
      <Icon size={11} />
      {label}
    </span>
  );
}

export function ConfidenceBar({
  confidence,
  label,
  className,
}: {
  confidence: number | null | undefined;
  label?: string;
  className?: string;
}) {
  const value = Math.max(0, Math.min(1, confidence ?? 0));
  const severity = value >= 0.7 ? "good" : value >= 0.45 ? "watch" : "warning";
  return (
    <div className={classNames("space-y-1", className)}>
      <div className="flex items-center justify-between text-[11px] text-slate-500 dark:text-slate-400">
        <span>{label ?? "Confidence"}</span>
        <span className="tabular font-medium text-slate-700 dark:text-slate-200">
          {Math.round(value * 100)}%
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-200/70 dark:bg-slate-800">
        <motion.div
          className={classNames("h-full rounded-full", SEVERITY_DOT[severity])}
          initial={{ width: 0 }}
          animate={{ width: `${value * 100}%` }}
          transition={{ duration: 0.6, ease: "easeOut" }}
        />
      </div>
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  message,
  action,
}: {
  icon?: ReactNode;
  title: string;
  message: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-slate-300 px-6 py-10 text-center dark:border-slate-700">
      <span className="grid h-11 w-11 place-items-center rounded-full bg-slate-900/5 text-slate-500 dark:bg-white/5 dark:text-slate-300">
        {icon ?? <Info size={20} />}
      </span>
      <div>
        <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">{title}</p>
        <p className="mx-auto mt-1 max-w-md text-sm text-slate-500 dark:text-slate-400">{message}</p>
      </div>
      {action}
    </div>
  );
}

export function ErrorState({
  title = "Something went wrong",
  message,
  onRetry,
}: {
  title?: string;
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-rose-500/40 bg-rose-500/5 p-5">
      <div className="flex items-center gap-2 text-sm font-semibold text-rose-700 dark:text-rose-300">
        <AlertTriangle size={16} />
        {title}
      </div>
      <p className="text-sm text-slate-600 dark:text-slate-300">{message}</p>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="self-start rounded-lg border border-rose-500/40 px-3 py-1.5 text-xs font-medium text-rose-700 transition hover:bg-rose-500/10 dark:text-rose-300"
        >
          Try again
        </button>
      ) : null}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={classNames("skeleton", className)} />;
}

export function CardSkeleton() {
  return (
    <div className="panel space-y-3 p-5">
      <Skeleton className="h-4 w-24" />
      <Skeleton className="h-8 w-32" />
      <Skeleton className="h-10 w-full" />
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={classNames("animate-spin", className)} size={16} />;
}

export function InlineNote({
  children,
  severity = "info",
  className,
}: {
  children: ReactNode;
  severity?: string;
  className?: string;
}) {
  return (
    <div
      className={classNames(
        "flex items-start gap-2 rounded-xl border px-3 py-2 text-xs",
        SEVERITY_CLASSES[severity] ?? SEVERITY_CLASSES.info,
        className,
      )}
    >
      <Info size={14} className="mt-0.5 shrink-0" />
      <span>{children}</span>
    </div>
  );
}

export function ProgressBar({
  value,
  max = 100,
  color,
  className,
}: {
  value: number;
  max?: number;
  color?: string;
  className?: string;
}) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className={classNames("h-1.5 w-full overflow-hidden rounded-full bg-slate-200/70 dark:bg-slate-800", className)}>
      <motion.div
        className="h-full rounded-full"
        style={{ backgroundColor: color ?? "currentColor" }}
        initial={{ width: 0 }}
        animate={{ width: `${pct}%` }}
        transition={{ duration: 0.5, ease: "easeOut" }}
      />
    </div>
  );
}
