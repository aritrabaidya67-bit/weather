/** Metric card: current value, interpretation, trend, sparkline and mini stats. */

import { motion } from "framer-motion";
import { ArrowRight, CloudRain, Droplets, Gauge, Sun, Thermometer, Wind } from "lucide-react";
import { Link } from "react-router-dom";
import type { ChannelCard as ChannelCardType } from "../../types";
import {
  SEVERITY_CLASSES,
  classNames,
  formatSigned,
  trendClass,
  trendGlyph,
  unitSymbol,
} from "../../utils/format";
import { Sparkline } from "../charts/Sparkline";
import { Chip, DataBadge, StatusDot } from "../common/Ui";

const ICONS: Record<string, typeof Thermometer> = {
  thermometer: Thermometer,
  droplets: Droplets,
  gauge: Gauge,
  wind: Wind,
  sun: Sun,
  "cloud-rain": CloudRain,
};

export function MetricCard({ card, simulated, index = 0 }: { card: ChannelCardType; simulated: boolean; index?: number }) {
  const Icon = ICONS[card.icon] ?? Gauge;
  const hasValue = card.value !== null && card.value !== undefined;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: Math.min(index * 0.05, 0.3) }}
    >
      <Link
        to={`/sensors/${card.channel}`}
        className="panel group block p-4 transition hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-md dark:hover:border-slate-700"
      >
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2">
            <span
              className="grid h-8 w-8 place-items-center rounded-lg"
              style={{ backgroundColor: `${card.color}1f`, color: card.color }}
            >
              <Icon size={16} />
            </span>
            <div>
              <p className="text-sm font-medium text-slate-700 dark:text-slate-200">{card.label}</p>
              <p className="text-[11px] text-slate-400">{card.sensor}</p>
            </div>
          </div>
          <ArrowRight
            size={14}
            className="mt-1 text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-slate-500 dark:text-slate-600"
          />
        </div>

        <div className="mt-3 flex items-end justify-between gap-2">
          <div>
            {hasValue ? (
              <div className="flex items-baseline gap-1">
                <span className="tabular text-2xl font-semibold tracking-tight text-slate-900 dark:text-slate-50">
                  {card.value!.toFixed(card.decimals)}
                </span>
                <span className="text-xs text-slate-500 dark:text-slate-400">{unitSymbol(card.unit)}</span>
              </div>
            ) : (
              <div className="text-sm font-medium text-slate-400">no reading</div>
            )}
            <div className="mt-1 flex items-center gap-2">
              <span
                className={classNames(
                  "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium capitalize",
                  SEVERITY_CLASSES[card.severity] ?? SEVERITY_CLASSES.unknown,
                )}
              >
                <StatusDot severity={card.severity} />
                {card.status}
              </span>
              {card.change !== null && card.change !== undefined ? (
                <span className={classNames("tabular text-[11px] font-medium", trendClass(card.trend))}>
                  {trendGlyph(card.trend)} {formatSigned(card.change, card.decimals, card.unit)}
                </span>
              ) : null}
            </div>
          </div>
          <div className="w-24">
            <Sparkline points={card.sparkline} color={card.color} height={36} />
          </div>
        </div>

        <div className="mt-3 flex items-center justify-between border-t border-slate-200/70 pt-2 text-[11px] text-slate-400 dark:border-slate-800/70">
          <span className="tabular">
            1h: {card.stats.min?.toFixed(card.decimals) ?? "—"}–{card.stats.max?.toFixed(card.decimals) ?? "—"}{" "}
            {unitSymbol(card.unit)}
          </span>
          {simulated ? (
            <DataBadge source="simulation" />
          ) : card.stale ? (
            <Chip severity="warning">stale</Chip>
          ) : null}
        </div>
      </Link>
    </motion.div>
  );
}
