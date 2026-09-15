/**
 * Overview — a command centre, not a report.
 *
 * Priority order on screen: overall status → risk → live values → trend →
 * forecast → anything that needs a human. Explanations, statistics, sensor
 * health and raw channels live on the pages this one links to.
 */

import { motion } from "framer-motion";
import { Cpu, Radio } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { NextUp } from "../components/dashboard/NextUp";
import { AttentionStrip } from "../components/dashboard/AttentionStrip";
import { SensorTile } from "../components/dashboard/SensorTile";
import { StatusOrb, statusWordFor } from "../components/dashboard/StatusOrb";
import { TREND_RANGES, TrendPanel, type TrendMetricKey } from "../components/dashboard/TrendPanel";
import { AnimatedNumber } from "../components/common/AnimatedNumber";
import { Card, CardSkeleton, ErrorState, Skeleton } from "../components/common/Ui";
import { api, ApiError } from "../services/api";
import { usePlatform } from "../state/PlatformContext";
import type { HistoryResponse, PredictionResponse } from "../types";
import { classNames, formatSigned, freshnessLabel, riskColor, unitSymbol } from "../utils/format";

/** The three numbers that answer "is it comfortable right now?". */
const HERO_METRICS = ["temperature", "humidity", "air_quality"] as const;

export default function Dashboard() {
  const { overview, loading, error, refresh } = usePlatform();
  const [rangeLabel, setRangeLabel] = useState("6 h");
  const [metric, setMetric] = useState<TrendMetricKey>("temperature_c");
  const [history, setHistory] = useState<HistoryResponse | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [prediction, setPrediction] = useState<PredictionResponse | null>(null);

  const range = TREND_RANGES.find((item) => item.label === rangeLabel) ?? TREND_RANGES[2];
  const latestAt = overview?.latest?.received_at ?? null;

  useEffect(() => {
    let cancelled = false;
    setHistoryError(null);
    void api
      .history({ hours: range.hours, bucket: range.bucket, limit: 300 })
      .then((response) => {
        if (!cancelled) setHistory(response);
      })
      .catch((caught) => {
        if (!cancelled) setHistoryError(caught instanceof ApiError ? caught.detail : "History unavailable.");
      });
    return () => {
      cancelled = true;
    };
  }, [range.hours, range.bucket, latestAt]);

  useEffect(() => {
    let cancelled = false;
    void api
      .predictions(undefined, "30")
      .then((response) => {
        if (!cancelled) setPrediction(response);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [latestAt]);

  if (loading && !overview) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-64 w-full rounded-2xl" />
        <div className="grid gap-3 sm:grid-cols-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <CardSkeleton key={index} />
          ))}
        </div>
      </div>
    );
  }

  if (error && !overview?.has_data) {
    return <ErrorState title="Backend not reachable" message={error} onRetry={() => void refresh()} />;
  }

  if (!overview?.has_data) {
    return <WaitingForDevice message={overview?.device?.status_message} />;
  }

  const risk = overview.risk;
  const word = statusWordFor(risk.level);
  const fresh = freshnessLabel(latestAt);
  const heroCards = HERO_METRICS.map((key) => overview.channels.find((card) => card.channel === key)).filter(
    (card): card is NonNullable<typeof card> => Boolean(card),
  );

  return (
    <div className="space-y-4">
      {/* Hero: status first, everything else supports it. */}
      <section className="panel-hero">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-slate-300/60 to-transparent dark:via-slate-700/60" />
        <div className="grid items-center gap-6 p-5 lg:grid-cols-[auto_minmax(0,1fr)_minmax(0,18rem)] lg:p-7">
          <motion.div
            initial={{ opacity: 0, scale: 0.94 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
            className="mx-auto"
          >
            <StatusOrb
              level={risk.level}
              score={risk.score}
              levelLabel={risk.label}
              word={word}
              confidence={risk.confidence}
              stale={overview.stale}
            />
          </motion.div>

          <div className="min-w-0">
            <p className="text-[13px] text-slate-500 dark:text-slate-400">{overview.classification.label}</p>
            {risk.reasons.length ? (
              <p className="mt-1 max-w-xl text-sm text-slate-700 dark:text-slate-200">
                {risk.reasons.slice(0, 2).join(" · ")}
              </p>
            ) : (
              <p className="mt-1 text-sm text-slate-700 dark:text-slate-200">
                Everything is inside the normal range.
              </p>
            )}

            <div className="mt-5 grid grid-cols-3 gap-4">
              {heroCards.map((card, index) => (
                <motion.div
                  key={card.channel}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3, delay: 0.08 + index * 0.06 }}
                >
                  <Link to={`/sensors/${card.channel}`} className="group block">
                    <div className="flex items-baseline gap-0.5">
                      <AnimatedNumber
                        value={card.value}
                        decimals={card.decimals ?? 1}
                        className="text-2xl font-semibold text-slate-900 sm:text-3xl dark:text-white"
                      />
                      <span className="text-xs text-slate-400">{unitSymbol(card.unit)}</span>
                    </div>
                    <p className="mt-0.5 text-[11px] uppercase tracking-wide text-slate-400">{card.label}</p>
                    <p className="mt-0.5 text-xs font-medium text-slate-500 group-hover:text-cyan-600 dark:text-slate-400 dark:group-hover:text-cyan-300">
                      {card.change !== null
                        ? `${formatSigned(card.change, card.decimals ?? 1)}${unitSymbol(card.unit)} · ${card.status}`
                        : card.status}
                    </p>
                  </Link>
                </motion.div>
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-3 lg:items-end">
            <Link
              to="/risk"
              className="group inline-flex flex-col gap-1 rounded-2xl border border-slate-200/80 px-4 py-3 text-left transition-colors hover:border-slate-300 dark:border-slate-800 dark:hover:border-slate-700"
              style={{ borderColor: `${riskColor(risk.level)}55` }}
            >
              <span className="text-[11px] uppercase tracking-wider text-slate-400">Risk breakdown</span>
              <span className="flex items-center gap-2 text-sm font-medium text-slate-700 dark:text-slate-200">
                {risk.contributions
                  .filter((item) => item.points >= 1)
                  .slice(0, 2)
                  .map((item) => `${item.label} +${item.points.toFixed(0)}`)
                  .join(" · ") || "no factor above the baseline"}
              </span>
              <span className="text-[11px] text-cyan-600 group-hover:underline dark:text-cyan-300">why this score →</span>
            </Link>
            <p className="flex items-center gap-1.5 text-[11px] text-slate-400">
              <Radio size={11} className={classNames(overview.stale ? "" : "text-emerald-500")} aria-hidden />
              {fresh.label} · reading {fresh.stale ? "stale" : "current"}
            </p>
          </div>
        </div>
      </section>

      {/* Trend + forecast */}
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.65fr)_minmax(0,1fr)]">
        <TrendPanel
          history={history}
          metric={metric}
          onMetricChange={setMetric}
          rangeLabel={rangeLabel}
          onRangeChange={setRangeLabel}
          ranges={TREND_RANGES}
          loading={!history && !historyError}
          error={historyError}
        />
        <NextUp prediction={prediction} />
      </div>

      {/* Live values */}
      <section>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6">
          {overview.channels.map((card, index) => (
            <SensorTile key={card.channel} card={card} index={index} />
          ))}
        </div>
      </section>

      {/* Attention */}
      <AttentionStrip alerts={overview.alerts} anomalies={overview.anomalies} />

      <p className="flex flex-wrap items-center gap-x-3 gap-y-1 px-1 text-[11px] text-slate-400">
        <span>{overview.reading_count} readings in {rangeLabel}</span>
        <span>sensor health {overview.risk.context.health_score?.toFixed(0) ?? "—"}%</span>
        <span>coverage {Math.round((risk.data_coverage ?? 0) * 100)}%</span>
        <Link to="/sensors" className="hover:underline">
          all sensors →
        </Link>
        <Link to="/analytics" className="hover:underline">
          analytics →
        </Link>
      </p>
    </div>
  );
}

function WaitingForDevice({ message }: { message?: string }) {
  return (
    <Card className="overflow-hidden">
      <div className="flex flex-col items-center gap-4 py-8 text-center">
        <div className="relative grid h-20 w-20 place-items-center">
          <span className="absolute inset-0 animate-[breathe_5.5s_ease-in-out_infinite] rounded-full bg-slate-500/10" />
          <span className="absolute inset-3 rounded-full border border-dashed border-slate-300 dark:border-slate-700" />
          <Cpu size={22} className="relative text-slate-400" aria-hidden />
        </div>
        <div>
          <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">Waiting for the Arduino</p>
          <p className="mx-auto mt-1 max-w-sm text-xs text-slate-500 dark:text-slate-400">
            {message ?? "Power the node, point it at this machine's LAN IP and the dashboard fills in by itself."}
          </p>
        </div>
        <div className="flex flex-wrap items-center justify-center gap-2 text-xs">
          <Link
            to="/device"
            className="rounded-lg border border-slate-200 px-3 py-1.5 font-medium transition hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
          >
            Hardware setup
          </Link>
          <a
            href="/docs"
            className="rounded-lg border border-slate-200 px-3 py-1.5 font-medium transition hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
          >
            API docs
          </a>
        </div>
      </div>
    </Card>
  );
}
