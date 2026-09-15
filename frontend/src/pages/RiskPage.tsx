/** Risk analysis: score, contributors, trend, anomalies, alerts and the model explanation. */

import { AlertTriangle, Gauge, ListChecks, ShieldAlert, Sliders } from "lucide-react";
import { useEffect, useState } from "react";
import { RiskGauge, RiskTrendChart } from "../components/charts/RiskGauge";
import { AlertFeed, AnomalyList, RiskBreakdown } from "../components/dashboard/Panels";
import { Card, CardSkeleton, Chip, DataBadge, EmptyState, InlineNote, SectionHeader } from "../components/common/Ui";
import { api } from "../services/api";
import { usePlatform } from "../state/PlatformContext";
import type { RiskModel } from "../types";
import { classNames, riskColor } from "../utils/format";

const LEVEL_BLUZ = ["silent", "silent", "occasional beep", "repeated warning pattern", "critical alarm pattern"];

export default function RiskPage() {
  const { overview, meta } = usePlatform();
  const [model, setModel] = useState<RiskModel | null>(null);
  const [trend, setTrend] = useState<{ timestamp: string; score: number; level: number }[]>([]);
  const [trendDirection, setTrendDirection] = useState<string>("unknown");
  const [trendChange, setTrendChange] = useState<number | null>(null);

  useEffect(() => {
    void api.riskModel().then(setModel).catch(() => setModel(null));
    void api
      .riskAnalysis(undefined, 6)
      .then((response) => {
        setTrend(response.trend);
        setTrendDirection(response.trend_direction);
        setTrendChange(response.trend_change);
      })
      .catch(() => undefined);
  }, [overview?.latest?.received_at]);

  if (!overview?.has_data) {
    return (
      <Card>
        <EmptyState
          icon={<ShieldAlert size={20} />}
          title="No risk assessment yet"
          message="Risk is calculated from real readings. Once the Arduino or simulator sends data, this page explains exactly which factors drive the score."
        />
      </Card>
    );
  }

  const risk = overview.risk;

  return (
    <div className="space-y-5">
      <SectionHeader
        title="Risk analysis"
        subtitle="An auditable score: every factor's contribution is shown, and the model is fully configurable."
        icon={<ShieldAlert size={16} />}
        action={overview.data_source === "simulation" ? <DataBadge source="simulation" /> : <DataBadge source={overview.data_source} />}
      />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)]">
        <Card className="flex flex-col items-center justify-center gap-4">
          <RiskGauge score={risk.score} level={risk.level} label={risk.label} confidence={risk.confidence} size={220} />
          <div className="text-center">
            <p className="text-sm font-medium text-slate-800 dark:text-slate-100">{risk.description}</p>
            <div className="mt-2 flex flex-wrap items-center justify-center gap-2">
              <Chip severity={risk.level >= 4 ? "critical" : risk.level === 3 ? "watch" : "good"}>
                level {risk.level} · {risk.code.replace("_", " ")}
              </Chip>
              <Chip severity={trendDirection === "rising" ? "warning" : trendDirection === "falling" ? "good" : "info"}>
                trend {trendDirection}
                {trendChange !== null ? ` (${trendChange > 0 ? "+" : ""}${trendChange.toFixed(1)})` : ""}
              </Chip>
            </div>
            <p className="mt-3 text-[11px] text-slate-500 dark:text-slate-400">
              Physical indicators: LED {Math.round(risk.level)} of 5 · buzzer {LEVEL_BLUZ[Math.min(4, Math.round(risk.level) - 1)]}
            </p>
          </div>
        </Card>

        <Card>
          <SectionHeader title="Risk trend" subtitle="Stored score history (last 6 hours of readings)" icon={<Gauge size={16} />} className="mb-3" />
          <RiskTrendChart data={trend} rangeHours={6} height={220} />
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <Card>
          <SectionHeader title="Why this score" subtitle="Additive factor contributions" icon={<ListChecks size={16} />} className="mb-3" />
          <RiskBreakdown risk={risk} />
        </Card>
        <div className="space-y-4">
          <Card>
            <SectionHeader title="Anomalies feeding the score" className="mb-3" />
            <AnomalyList anomalies={overview.anomalies} />
          </Card>
          <Card>
            <SectionHeader title="Active alerts" className="mb-3" />
            <AlertFeed alerts={overview.alerts} />
          </Card>
        </div>
      </div>

      <Card>
        <SectionHeader
          title="Risk model"
          subtitle="Weights, bands and cross-sensor rules - replaceable through RISK_CONFIG_FILE"
          icon={<Sliders size={16} />}
          className="mb-3"
        />
        {model ? (
          <div className="space-y-5">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              {model.levels.map((level) => (
                <div
                  key={level.level}
                  className={classNames(
                    "rounded-2xl border p-3",
                    risk.level === level.level ? "border-cyan-500/50 bg-cyan-500/5" : "border-slate-200/80 dark:border-slate-800/80",
                  )}
                >
                  <div className="flex items-center gap-2">
                    <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: level.color }} />
                    <span className="text-xs font-semibold text-slate-700 dark:text-slate-200">
                      L{level.level} {level.label}
                    </span>
                  </div>
                  <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                    {level.min_score}–{level.max_score} · LED {level.led_index}
                  </p>
                  <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">{level.description}</p>
                  <p className="mt-1 text-[10px] uppercase tracking-wide text-slate-400">
                    buzzer: {level.buzzer_pattern.replace(/_/g, " ")}
                  </p>
                </div>
              ))}
            </div>

            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Factor weights</p>
              <div className="space-y-2">
                {model.factors.map((factor) => {
                  const contribution = risk.contributions.find((item) => item.key === factor.key);
                  return (
                    <div key={factor.key} className="space-y-1">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-medium text-slate-700 dark:text-slate-200">
                          {factor.label}
                          {factor.note ? (
                            <span className="ml-2 font-normal text-slate-400">{factor.note}</span>
                          ) : null}
                        </span>
                        <span className="tabular text-slate-500 dark:text-slate-400">
                          weight {factor.weight} · now +{(contribution?.points ?? 0).toFixed(1)}
                        </span>
                      </div>
                      <div className="h-2 overflow-hidden rounded-full bg-slate-200/70 dark:bg-slate-800">
                        <div
                          className="h-full rounded-full transition-all"
                          style={{
                            width: `${Math.min(100, ((contribution?.points ?? 0) / factor.weight) * 100)}%`,
                            backgroundColor: riskColor(risk.level),
                          }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
                Cross-sensor combination rules
              </p>
              <ul className="space-y-1.5">
                {model.combination_rules.map((rule) => (
                  <li key={rule.id} className="rounded-xl bg-slate-50/70 px-3 py-2 text-xs text-slate-600 dark:bg-slate-900/40 dark:text-slate-300">
                    <span className="font-medium text-slate-700 dark:text-slate-200">{rule.label}</span> (+{rule.points} points)
                    <span className="ml-1 text-slate-500 dark:text-slate-400">— {rule.reason}</span>
                  </li>
                ))}
              </ul>
            </div>

            <InlineNote severity="info">
              {model.notes.join(" ")}
            </InlineNote>
          </div>
        ) : (
          <CardSkeleton />
        )}
      </Card>

      <Card>
        <SectionHeader title="Alert rules behind these alerts" icon={<AlertTriangle size={16} />} className="mb-3" />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead>
              <tr className="text-[11px] uppercase tracking-wide text-slate-400">
                <th className="pb-2 font-medium">Rule</th>
                <th className="pb-2 font-medium">Severity</th>
                <th className="pb-2 font-medium">Condition</th>
                <th className="pb-2 font-medium">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200/70 dark:divide-slate-800/70">
              {(meta?.alert_rules ?? []).map((rule) => (
                <tr key={rule.id}>
                  <td className="py-2 pr-3 font-medium text-slate-700 dark:text-slate-200">{rule.title}</td>
                  <td className="py-2 pr-3">
                    <Chip severity={rule.severity === "critical" ? "critical" : rule.severity === "warning" ? "warning" : "info"}>
                      {rule.severity}
                    </Chip>
                  </td>
                  <td className="py-2 pr-3 text-[11px] text-slate-500 dark:text-slate-400">{rule.condition}</td>
                  <td className="py-2 text-[11px] text-slate-500 dark:text-slate-400">{rule.default_action}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
