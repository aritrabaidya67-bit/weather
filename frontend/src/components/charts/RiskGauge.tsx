/** Radial risk gauge plus the risk-score history area chart. */

import { motion } from "framer-motion";
import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { axisTime, riskColor } from "../../utils/format";

export function RiskGauge({
  score,
  level,
  label,
  size = 180,
  confidence,
}: {
  score: number;
  level: number;
  label: string;
  size?: number;
  confidence?: number;
}) {
  const radius = size / 2 - 14;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.max(0, Math.min(100, score));
  const progress = (clamped / 100) * circumference * 0.75; // 3/4 sweep
  const color = riskColor(level);

  return (
    <div className="relative grid place-items-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-[135deg]">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          className="text-slate-200 dark:text-slate-800"
          strokeWidth={10}
          strokeDasharray={`${circumference * 0.75} ${circumference}`}
          strokeLinecap="round"
        />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={10}
          strokeLinecap="round"
          strokeDasharray={`${progress} ${circumference}`}
          initial={{ strokeDasharray: `0 ${circumference}` }}
          animate={{ strokeDasharray: `${progress} ${circumference}` }}
          transition={{ duration: 0.9, ease: "easeOut" }}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center">
        <div>
          <div className="tabular text-4xl font-semibold tracking-tight" style={{ color }}>
            {clamped.toFixed(0)}
          </div>
          <div className="text-[11px] font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
            {label} · L{level}
          </div>
          {confidence !== undefined ? (
            <div className="mt-1 text-[11px] text-slate-400">
              {Math.round(confidence * 100)}% data confidence
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export function RiskTrendChart({
  data,
  height = 200,
  rangeHours = 6,
}: {
  data: { timestamp: string; score: number; level: number }[];
  height?: number;
  rangeHours?: number;
}) {
  const rows = data
    .map((point) => ({ timestamp: new Date(point.timestamp).getTime(), value: point.score, level: point.level }))
    .filter((row) => !Number.isNaN(row.timestamp));

  if (rows.length < 2) {
    return (
      <div className="grid h-[120px] place-items-center rounded-xl border border-dashed border-slate-300 text-xs text-slate-500 dark:border-slate-700 dark:text-slate-400">
        Risk history appears once a few readings have been stored.
      </div>
    );
  }

  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: -20 }}>
          <defs>
            <linearGradient id="riskGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#f97316" stopOpacity={0.4} />
              <stop offset="100%" stopColor="#f97316" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.18)" vertical={false} />
          <XAxis
            dataKey="timestamp"
            type="number"
            domain={["dataMin", "dataMax"]}
            tickFormatter={(value: number) => axisTime(value, rangeHours)}
            tick={{ fontSize: 11, fill: "rgb(148 163 184)" }}
            axisLine={false}
            tickLine={false}
            minTickGap={30}
          />
          <YAxis domain={[0, 100]} tick={{ fontSize: 11, fill: "rgb(148 163 184)" }} axisLine={false} tickLine={false} width={44} />
          {[20, 40, 60, 80].map((threshold) => (
            <ReferenceLine key={threshold} y={threshold} stroke="rgba(148,163,184,0.25)" strokeDasharray="4 4" />
          ))}
          <Tooltip
            content={({ active, payload, label }) => {
              if (!active || !payload?.length) return null;
              const row = payload[0].payload as { value: number; level: number };
              return (
                <div className="rounded-xl border border-slate-200 bg-white/95 px-3 py-2 text-xs shadow-lg dark:border-slate-700 dark:bg-slate-900/95">
                  <div className="font-medium text-slate-500 dark:text-slate-400">
                    {new Date(Number(label)).toLocaleString()}
                  </div>
                  <div className="tabular font-semibold" style={{ color: riskColor(row.level) }}>
                    Risk {row.value.toFixed(0)}/100 · level {row.level}
                  </div>
                </div>
              );
            }}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke="#f97316"
            strokeWidth={2}
            fill="url(#riskGradient)"
            dot={false}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
