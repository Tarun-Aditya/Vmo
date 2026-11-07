import { ReactNode, useEffect, useRef } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Status, ago, api, inFuture, useSetting } from "./lib";

export type Sev = "low" | "medium" | "high" | "critical";

/** Severity is encoded in form (glyph + label + stripe weight), not colour alone. */
const SEV: Record<Sev, { glyph: string; cls: string; stripe: string }> = {
  critical: { glyph: "▲▲", cls: "bg-red-100 text-red-900 border-red-600 dark:bg-red-950 dark:text-red-200", stripe: "border-l-8 border-red-600" },
  high: { glyph: "▲", cls: "bg-orange-100 text-orange-900 border-orange-500 dark:bg-orange-950 dark:text-orange-200", stripe: "border-l-[6px] border-orange-500" },
  medium: { glyph: "●", cls: "bg-amber-100 text-amber-900 border-amber-500 dark:bg-amber-950 dark:text-amber-200", stripe: "border-l-4 border-amber-500" },
  low: { glyph: "○", cls: "bg-sky-100 text-sky-900 border-sky-500 dark:bg-sky-950 dark:text-sky-200", stripe: "border-l-2 border-sky-500" },
};
export const sevStripe = (s: Sev) => SEV[s].stripe;

export function SeverityChip({ sev, label }: { sev: Sev; label?: string }) {
  const s = SEV[sev];
  return (
    <span className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-xs font-medium ${s.cls}`}>
      <span aria-hidden>{s.glyph}</span>{label ?? sev}
    </span>
  );
}

export function ConfidenceBadge({ v }: { v: number | null }) {
  if (v === null || v === undefined) return null;
  const pct = Math.round(Number(v) * 100);
  const cls = pct >= 90 ? "bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200"
    : pct >= 70 ? "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200"
    : "bg-red-100 text-red-900 dark:bg-red-950 dark:text-red-200";
  const glyph = pct >= 90 ? "✓" : pct >= 70 ? "~" : "?";
  return <span title="Extraction confidence" className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${cls}`}>{glyph} {pct}%</span>;
}

export function Card({ title, right, children, className = "" }: { title?: ReactNode; right?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-lg border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-800 ${className}`}>
      {(title || right) && (
        <div className="mb-3 flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{title}</h2>{right}
        </div>
      )}
      {children}
    </section>
  );
}

export const Th = ({ children, className = "" }: { children?: ReactNode; className?: string }) =>
  <th className={`px-2 py-1.5 text-left text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 ${className}`}>{children}</th>;
export const Td = ({ children, className = "" }: { children?: ReactNode; className?: string }) =>
  <td className={`px-2 py-1.5 align-top ${className}`}>{children}</td>;

export function Loading({ q }: { q: { isLoading: boolean; error: unknown } }) {
  if (q.isLoading) return <p className="text-sm text-slate-500">Loading…</p>;
  if (q.error) return <p className="text-sm text-red-600">Could not load: {String(q.error)}</p>;
  return null;
}

const NAV = [["/", "Dashboard"], ["/contracts", "Contracts"], ["/vendors", "Vendors"], ["/clauses", "Key clauses"], ["/obligations", "Obligations"], ["/spend", "Spend"], ["/risk", "Risk"], ["/ask", "Ask"], ["/redline", "Redline"], ["/templates", "Templates"], ["/new", "New contract"]];

export function Layout() {
  const [dark, setDark] = useSetting("dark", window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false);
  const [demo, setDemo] = useSetting("demo", true);
  document.documentElement.classList.toggle("dark", dark);
  const meta = useQuery({ queryKey: ["meta"], queryFn: () => api<{ llm_available: boolean; llm_label: string; llm_provider: string; today: string }>("/api/meta") });
  const qc = useQueryClient();
  const st = useQuery({ queryKey: ["status"], queryFn: () => api<Status>("/api/status"), refetchInterval: 10000 });
  const al = useQuery({ queryKey: ["alerts-summary"], queryFn: () => api<{ unread: number; open: number; critical: number }>("/api/alerts/summary"), refetchInterval: 30000 });
  const lastRun = useRef<number | null>(null);
  useEffect(() => {
    // A pipeline run finished: refresh every screen, so all modules show the same new data.
    const id = st.data?.last_run?.id ?? null;
    if (lastRun.current !== null && id !== lastRun.current) qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "status" });
    lastRun.current = id;
  }, [st.data?.last_run?.id, qc]);
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/95 backdrop-blur dark:border-slate-700 dark:bg-slate-900/95">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2">
          <span className="text-lg font-bold tracking-tight">Contract<span className="text-indigo-600">IQ</span></span>
          <nav className="flex flex-wrap gap-1">
            {NAV.map(([to, label]) => (
              <NavLink key={to} to={to} end={to === "/"}
                className={({ isActive }) => `rounded px-3 py-1.5 text-sm font-medium ${isActive ? "bg-indigo-600 text-white" : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"}`}>
                {label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
            {st.data && (
              <NavLink to="/admin" className="flex items-center gap-1.5 rounded border border-slate-200 px-2 py-0.5 text-xs dark:border-slate-600"
                title={`Pipeline ${st.data.config.enabled ? "on" : "off"} · every ${st.data.config.interval_minutes} min`}>
                <span className={`inline-block h-2 w-2 rounded-full ${st.data.running ? "animate-pulse bg-amber-500" : st.data.config.enabled ? "bg-emerald-500" : "bg-slate-400"}`} aria-hidden />
                {st.data.running ? "Pipeline running…" : `Synced ${ago(st.data.config.last_run_at)}`}
                {!st.data.running && st.data.config.enabled && <span className="text-slate-500">· next {inFuture(st.data.config.next_run_at)}</span>}
              </NavLink>
            )}
            <NavLink to="/alerts" className="relative rounded px-2 py-1 text-base" aria-label={`Alerts${al.data?.unread ? `, ${al.data.unread} unread` : ""}`} title="Notification centre">
              🔔{!!al.data?.unread && <span className="absolute -right-1 -top-1 min-w-[1.1rem] rounded-full bg-red-600 px-1 text-center text-[10px] font-bold leading-4 text-white">{al.data.unread > 99 ? "99+" : al.data.unread}</span>}
            </NavLink>
            <label className="flex cursor-pointer items-center gap-2" title="Use cached AI results where available, so the demo is fast and works offline">
              <input type="checkbox" checked={demo} onChange={(e) => setDemo(e.target.checked)} /> Demo mode
            </label>
            <span className={`rounded px-2 py-0.5 text-xs ${meta.data?.llm_available ? "bg-emerald-100 text-emerald-900" : "bg-slate-200 text-slate-700"}`}>
              {meta.data ? meta.data.llm_label : "…"}
            </span>
            <NavLink to="/admin" title="Pipeline, key clauses, values & limits, checklist" className={({ isActive }) => `rounded px-2 py-1 ${isActive ? "bg-slate-200 font-medium dark:bg-slate-700" : "text-slate-500 hover:underline"}`}>⚙ Admin</NavLink>
            <button onClick={() => setDark(!dark)} className="rounded border px-2 py-1" aria-label="Toggle theme">{dark ? "☀ Light" : "☾ Dark"}</button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6"><Outlet /></main>
    </div>
  );
}
