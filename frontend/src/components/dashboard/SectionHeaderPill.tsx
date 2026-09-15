/** Minimal panel header: icon + short title + optional muted meta. No prose. */

import type { ReactNode } from "react";
import { classNames } from "../../utils/format";

export function SectionHeaderPill({
  icon,
  title,
  meta,
  action,
  className,
}: {
  icon?: ReactNode;
  title: string;
  meta?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <header className={classNames("flex items-center justify-between gap-2", className)}>
      <h2 className="flex items-center gap-1.5 text-[13px] font-semibold tracking-tight text-slate-700 dark:text-slate-200">
        {icon ? <span className="text-slate-400 dark:text-slate-500">{icon}</span> : null}
        {title}
      </h2>
      <div className="flex items-center gap-2">
        {meta ? <span className="text-[11px] text-slate-400">{meta}</span> : null}
        {action}
      </div>
    </header>
  );
}
