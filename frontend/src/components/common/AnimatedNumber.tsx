/**
 * Numeric readout that interpolates between values instead of snapping.
 *
 * Live sensor data arrives every few seconds; the eye picks up a jump far
 * better than a value that eases into place. Reduced-motion users get the value
 * immediately.
 */

import { animate, useReducedMotion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { classNames } from "../../utils/format";

export function AnimatedNumber({
  value,
  decimals = 1,
  className,
  duration = 0.55,
}: {
  value: number | null | undefined;
  decimals?: number;
  className?: string;
  duration?: number;
}) {
  const reduceMotion = useReducedMotion();
  const [display, setDisplay] = useState<number | null>(value ?? null);
  const previous = useRef<number | null>(value ?? null);

  useEffect(() => {
    if (value === null || value === undefined || Number.isNaN(value)) {
      previous.current = null;
      setDisplay(null);
      return;
    }
    const from = previous.current ?? value;
    previous.current = value;
    if (reduceMotion || from === value) {
      setDisplay(value);
      return;
    }
    const controls = animate(from, value, {
      duration,
      ease: [0.22, 1, 0.36, 1],
      onUpdate: (latest) => setDisplay(latest),
    });
    return () => controls.stop();
  }, [value, reduceMotion, duration]);

  if (display === null) {
    return <span className={classNames("tabular text-slate-400", className)}>—</span>;
  }
  return <span className={classNames("tabular", className)}>{display.toFixed(decimals)}</span>;
}
