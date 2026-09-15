/**
 * Overview — The Hero Dashboard.
 * 
 * Re-architected for maximum understanding and minimal cognitive load.
 * "Understand the state before reading the data."
 */

import { motion } from "framer-motion";
import { Cpu } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { NextUp } from "../components/dashboard/NextUp";
import { AttentionStrip } from "../components/dashboard/AttentionStrip";
import { SensorTile } from "../components/dashboard/SensorTile";
import { StatusOrb, statusWordFor } from "../components/dashboard/StatusOrb";
import { TREND_RANGES, TrendPanel, type TrendMetricKey } from "../components/dashboard/TrendPanel";
import { CardSkeleton, Skeleton } from "../components/common/Ui";
import { api, ApiError } from "../services/api";
import { usePlatform } from "../state/PlatformContext";
import type { HistoryResponse, PredictionResponse } from "../types";

const HERO_METRICS = ["temperature", "humidity", "air_quality", "pressure"] as const;

export default function Dashboard() {
  const { overview, loading, error, refresh } = usePlatform();
  const [rangeLabel, setRangeLabel] = useState("6h");
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
      <div className="space-y-6">
        <Skeleton className="h-72 w-full rounded-[2rem]" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <CardSkeleton key={index} className="h-40" />
          ))}
        </div>
      </div>
    );
  }

  if (error && !overview?.has_data) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <div className="rounded-full bg-rose-500/10 p-4 mb-4 text-rose-500">
          <Cpu size={32} />
        </div>
        <h2 className="text-xl font-semibold text-slate-900 dark:text-white">Can't reach the monitoring service.</h2>
        <p className="mt-2 text-slate-500 max-w-sm">{error}</p>
        <button onClick={() => void refresh()} className="mt-6 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-800 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-200">
          Retry
        </button>
      </div>
    );
  }

  if (!overview?.has_data) {
    return <WaitingForDevice />;
  }

  const risk = overview.risk;
  const word = statusWordFor(risk.level);
  const heroCards = HERO_METRICS.map((key) => overview.channels.find((card) => card.channel === key)).filter(
    (card): card is NonNullable<typeof card> => Boolean(card)
  );

  return (
    <div className="space-y-6 sm:space-y-8 animate-float-in">
      
      {/* Priority 1: The Alert Strip (Only if there are alerts) */}
      <AttentionStrip alerts={overview.alerts} anomalies={overview.anomalies} />

      {/* Priority 2: Overall Status & Key Sensors */}
      <section className="grid gap-6 xl:grid-cols-[400px_minmax(0,1fr)]">
        
        {/* The Hero State */}
        <div className="panel-hero flex flex-col justify-center min-h-[380px]">
          <StatusOrb
            level={risk.level}
            score={risk.score}
            levelLabel={risk.label}
            word={word}
            confidence={risk.confidence}
            stale={overview.stale}
          />
        </div>

        {/* The Live Sensor Modules */}
        <div className="grid gap-4 sm:grid-cols-2">
          {heroCards.map((card, index) => (
            <SensorTile key={card.channel} card={card} index={index} />
          ))}
        </div>
      </section>

      {/* Priority 3: Visual Prediction (What happens next) */}
      <section>
        <NextUp prediction={prediction} />
      </section>

      {/* Priority 4: The Core Trend (One chart, beautifully rendered) */}
      <section className="h-[420px]">
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
      </section>

    </div>
  );
}

function WaitingForDevice() {
  return (
    <div className="panel-hero min-h-[60vh] flex flex-col items-center justify-center text-center p-8">
      <motion.div 
        className="relative grid h-24 w-24 place-items-center mb-8"
        animate={{ scale: [1, 1.05, 1] }}
        transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
      >
        <span className="absolute inset-0 rounded-full border-2 border-dashed border-slate-300 dark:border-slate-700 animate-[spin_20s_linear_infinite]" />
        <div className="absolute inset-4 rounded-full bg-slate-100 dark:bg-surface-800 grid place-items-center shadow-inner">
          <Cpu size={28} className="text-slate-400 dark:text-slate-500" />
        </div>
      </motion.div>
      
      <h2 className="text-2xl font-semibold tracking-tight text-slate-900 dark:text-white">Waiting for your device</h2>
      <p className="mt-3 text-slate-500 dark:text-slate-400 max-w-sm">
        Connect the Arduino to start monitoring. The dashboard will automatically update when data arrives.
      </p>
      
      <div className="mt-8 flex gap-3">
        <Link to="/device" className="rounded-full bg-slate-900 px-6 py-2.5 text-sm font-medium text-white transition hover:bg-slate-800 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-200">
          Hardware Setup
        </Link>
      </div>
    </div>
  );
}
