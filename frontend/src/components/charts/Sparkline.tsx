/** Tiny trend line used inside metric cards (pure SVG - no chart lib overhead). */

import { useMemo } from "react";
import type { SeriesPoint } from "../../types";

export function Sparkline({
  points,
  color = "#38bdf8",
  height = 40,
  className,
  showArea = true,
}: {
  points: SeriesPoint[];
  color?: string;
  height?: number;
  className?: string;
  showArea?: boolean;
}) {
  const geometry = useMemo(() => {
    const values = points
      .map((point) => point.value)
      .filter((value): value is number => value !== null && value !== undefined && !Number.isNaN(value));
    if (values.length < 2) return null;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || Math.abs(max) || 1;
    const width = 100;
    const step = width / (values.length - 1);
    const coords = values.map((value, index) => {
      const x = index * step;
      // keep a little headroom so flat lines still look like lines
      const y = height - ((value - min) / span) * (height - 6) - 3;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    });
    const path = `M${coords.join(" L")}`;
    const area = `${path} L${width},${height} L0,${height} Z`;
    return { path, area, gradientId: `spark-${color.replace("#", "")}-${values.length}` };
  }, [points, color, height]);

  if (!geometry) {
    return (
      <div
        className={className}
        style={{ height }}
        aria-label="Not enough data to draw a trend"
      >
        <div className="h-full w-full rounded-md border border-dashed border-slate-300/70 dark:border-slate-700/70" />
      </div>
    );
  }

  return (
    <svg
      viewBox={`0 0 100 ${height}`}
      preserveAspectRatio="none"
      className={className}
      style={{ height, width: "100%" }}
      role="img"
      aria-label="Recent trend"
    >
      <defs>
        <linearGradient id={geometry.gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.35" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      {showArea ? <path d={geometry.area} fill={`url(#${geometry.gradientId})`} /> : null}
      <path
        d={geometry.path}
        fill="none"
        stroke={color}
        strokeWidth="1.6"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
