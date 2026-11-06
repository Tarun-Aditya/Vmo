import { ReactNode } from "react";
import { Card, Sev, SeverityChip } from "../ui";

export const Tile = ({ l, v, sub, tone }: { l: string; v: ReactNode; sub?: ReactNode; tone?: "red" | "amber" | "green" }) => (
  <Card className={tone === "red" ? "border-l-4 border-l-red-500" : tone === "amber" ? "border-l-4 border-l-amber-500" : tone === "green" ? "border-l-4 border-l-emerald-500" : ""}>
    <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">{l}</div>
    <div className="mt-1 text-2xl font-semibold tabular-nums">{v}</div>
    {sub && <div className="mt-0.5 text-xs text-slate-500">{sub}</div>}
  </Card>
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
