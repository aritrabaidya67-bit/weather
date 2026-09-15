/**
 * Sensor tile — deliberately sparse: icon, value, name, trend, sparkline.
 *
 * Everything explanatory (statistics, anomalies, baseline, interpretation)
 * lives on the sensor detail page that this tile links to.
 */

import { motion } from "framer-motion";
import { ChevronRight } from "lucide-react";
import { Link } from "react-router-dom";
import type { ChannelCard as ChannelCardType } from "../../types";
import { classNames, unitSymbol } from "../../utils/format";
import { AnimatedNumber } from "../common/AnimatedNumber";
import { TrendPill } from "../common/TrendPill";
import { Sparkline } from "../charts/Sparkline";
import { channelIcon } from "./channelIcons";

export function SensorTile({ card, index = 0 }: { card: ChannelCardType; index?: number }) {
  const Icon = channelIcon(card.icon ?? card.channel);
  const missing = card.value === null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32, delay: Math.min(index * 0.04, 0.24), ease: [0.22, 1, 0.36, 1] }}
    >
      <Link
        to={`/sensors/${card.channel}`}
        className={classNames("tile tile-hover group block", !card.severity || card.severity === "unknown" ? "" : "")}
        aria-label={`${card.label}: ${missing ? "no reading" : `${card.value} ${card.unit}`}`}
      >
        <div className="flex items-center justify-between gap-2">
          <span className="flex items-center gap-1.5 text-[11px] font-medium text-slate-500 dark:text-slate-400">
            <Icon size={13} style={{ color: card.color }} aria-hidden />
            {missing ? "no reading" : card.status}
          </span>
          <ChevronRight
            size={13}
            className="text-slate-300 transition-transform group-hover:translate-x-0.5 dark:text-slate-600"
            aria-hidden
          />
        </div>

        <div className="mt-2 flex items-baseline gap-1">
          <AnimatedNumber
            value={card.value}
            decimals={card.decimals ?? 1}
            className="text-2xl font-semibold leading-none text-slate-900 dark:text-white"
          />
          <span className="text-xs font-medium text-slate-400">{missing ? "" : unitSymbol(card.unit)}</span>
        </div>

        <div className="mt-1 flex items-center justify-between gap-2">
          <span className="truncate text-xs text-slate-500 dark:text-slate-400">{card.label}</span>
          <TrendPill
            compact
            direction={card.trend}
            change={card.change}
            unit={card.unit}
            decimals={card.decimals ?? 1}
          />
        </div>

        <div className="mt-2 h-8 opacity-90">
          {missing || card.sparkline.length < 2 ? (
            <div className="grid h-full place-items-center rounded-md border border-dashed border-slate-200 text-[10px] text-slate-400 dark:border-slate-800">
              collecting…
            </div>
          ) : (
            <Sparkline points={card.sparkline} color={card.color} height={32} />
          )}
        </div>
      </Link>
    </motion.div>
  );
}
