/**
 * Premium Sensor Tile.
 * Sparse: icon, value, name, trend, sparkline.
 * Adds soft glows, lifting hover interactions, and beautiful spacing.
 */

import { motion } from "framer-motion";
import { Link } from "react-router-dom";
import type { ChannelCard as ChannelCardType } from "../../types";
import { unitSymbol } from "../../utils/format";
import { AnimatedNumber } from "../common/AnimatedNumber";
import { TrendPill } from "../common/TrendPill";
import { Sparkline } from "../charts/Sparkline";
import { channelIcon } from "./channelIcons";

export function SensorTile({ card, index = 0 }: { card: ChannelCardType; index?: number }) {
  const Icon = channelIcon(card.icon ?? card.channel);
  const missing = card.value === null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: Math.min(index * 0.05, 0.3), ease: [0.16, 1, 0.3, 1] }}
    >
      <Link
        to={`/sensors/${card.channel}`}
        className="tile tile-hover group block h-full flex flex-col justify-between"
        aria-label={`${card.label}: ${missing ? "no reading" : `${card.value} ${card.unit}`}`}
        style={{
          boxShadow: `inset 0 1px 0 rgba(255,255,255,0.4), 0 4px 16px -4px ${card.color}15`,
        }}
      >
        <div className="glass-overlay rounded-2xl" />

        <div className="relative z-10">
          <div className="flex items-center justify-between mb-3">
            <div 
              className="flex items-center justify-center w-8 h-8 rounded-full" 
              style={{ backgroundColor: `${card.color}15`, color: card.color }}
            >
              <Icon size={16} strokeWidth={2.5} aria-hidden />
            </div>
            
            {!missing && (
              <span className="text-[10px] font-bold tracking-widest uppercase" style={{ color: card.color }}>
                {card.status}
              </span>
            )}
          </div>

          <div className="flex items-baseline gap-1 mt-1">
            <AnimatedNumber
              value={card.value}
              decimals={card.decimals ?? 1}
              className="text-3xl font-semibold tracking-tight text-slate-900 dark:text-white"
            />
            <span className="text-sm font-medium text-slate-400">{missing ? "" : unitSymbol(card.unit)}</span>
          </div>

          <div className="mt-1 flex items-center justify-between">
            <span className="text-sm font-medium text-slate-500 dark:text-slate-400">{card.label}</span>
            <TrendPill
              compact
              direction={card.trend}
              change={card.change}
              unit={card.unit}
              decimals={card.decimals ?? 1}
            />
          </div>
        </div>

        <div className="relative z-10 mt-4 h-10 w-full opacity-80 group-hover:opacity-100 transition-opacity">
          {missing || card.sparkline.length < 2 ? (
            <div className="grid h-full place-items-center rounded-lg border border-dashed border-slate-200 bg-slate-50/50 text-[10px] text-slate-400 dark:border-white/5 dark:bg-white/5">
              collecting…
            </div>
          ) : (
            <Sparkline points={card.sparkline} color={card.color} height={40} />
          )}
        </div>
      </Link>
    </motion.div>
  );
}
