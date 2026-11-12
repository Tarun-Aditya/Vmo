import { ReactNode } from "react";
import { Card, Sev, SeverityChip } from "../ui";

export const Tile = ({ l, v, sub, tone }: { l: string; v: ReactNode; sub?: ReactNode; tone?: "red" | "amber" | "green" }) => (
  <div className={`rounded-lg border bg-white p-3.5 dark:bg-slate-800 ${tone === "red" ? "border-red-300" : tone === "amber" ? "border-orange-300" : tone === "green" ? "border-indigo-300" : "border-line dark:border-slate-700"}`}>
    <div className="text-[11.5px] font-semibold uppercase tracking-wider text-ink-mute dark:text-slate-400">{l}</div>
    <div className="num mt-0.5 text-[26px] font-semibold leading-tight tracking-tight">{v}</div>
    {sub && <div className="text-[12.5px] text-ink-mute dark:text-slate-400">{sub}</div>}
  </div>
);

export const TIER_SEV: Record<string, Sev> = { critical: "critical", high: "high", medium: "medium", low: "low" };
export const TierChip = ({ tier }: { tier: string }) => <SeverityChip sev={TIER_SEV[tier] ?? "low"} label={`${tier} risk`} />;

/** Horizontal meter: filled share of 0-100, optional marker. */
export function Meter({ value, max = 100, marker, tone = "indigo", label }: { value: number; max?: number; marker?: number; tone?: "indigo" | "red" | "amber" | "green"; label?: string }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  const color = { indigo: "bg-indigo-500", red: "bg-red-500", amber: "bg-amber-500", green: "bg-emerald-500" }[tone];
  return (
    <div className="relative h-2.5 w-full rounded bg-slate-200 dark:bg-slate-700" role="meter" aria-valuenow={Math.round(value)} aria-valuemax={max} aria-label={label}>
      <div className={`h-full rounded ${color}`} style={{ width: `${pct}%` }} />
      {marker !== undefined && <div className="absolute -top-0.5 h-3.5 w-0.5 bg-slate-900 dark:bg-white" style={{ left: `${Math.max(0, Math.min(100, (marker / max) * 100))}%` }} title="expected by now" />}
    </div>
  );
}

export const scoreTone = (n: number): "green" | "amber" | "red" => (n >= 50 ? "red" : n >= 30 ? "amber" : "green");
export const Pill = ({ children, cls = "bg-slate-200 text-slate-800 dark:bg-slate-700 dark:text-slate-100" }: { children: ReactNode; cls?: string }) => (
  <span className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${cls}`}>{children}</span>
);
