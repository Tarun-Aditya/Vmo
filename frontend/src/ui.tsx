import { ReactNode, useEffect, useRef, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Status, ago, api, inFuture, setToken, useSetting } from "./lib";

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
    <section className={`rounded-lg border border-line bg-white p-4 dark:border-slate-700 dark:bg-slate-800 ${className}`}>
      {(title || right) && (
        <div className="mb-3 flex items-center justify-between gap-2">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-ink-mute dark:text-slate-400">{title}</h2>{right}
        </div>
      )}
      {children}
    </section>
  );
}

export const Th = ({ children, className = "" }: { children?: ReactNode; className?: string }) =>
  <th className={`px-2.5 py-2 text-left text-[11.5px] font-semibold uppercase tracking-wide text-ink-mute dark:text-slate-400 ${className}`}>{children}</th>;
export const Td = ({ children, className = "" }: { children?: ReactNode; className?: string }) =>
  <td className={`px-2.5 py-2 align-middle ${className}`}>{children}</td>;

export function Loading({ q }: { q: { isLoading: boolean; error: unknown } }) {
  if (q.isLoading) return <p className="text-sm text-slate-500">Loading…</p>;
  if (q.error) return <p className="text-sm text-red-600">Could not load: {String(q.error)}</p>;
  return null;
}

const ICON: Record<string, string> = {
  "/": "M3 3h7v9H3zM14 3h7v5h-7zM14 12h7v9h-7zM3 16h7v5H3z", "/map": "M6 8.5a2.5 2.5 0 100-5 2.5 2.5 0 000 5zM18 14.5a2.5 2.5 0 100-5 2.5 2.5 0 000 5zM6 20.5a2.5 2.5 0 100-5 2.5 2.5 0 000 5zM8 7l8 4M8 17l8-4", "/contracts": "M6 3h9l4 4v14H6zM9 12h7M9 16h7", "/vendors": "M9 11a3.5 3.5 0 100-7 3.5 3.5 0 000 7zM3 20c0-4 3-6 6-6s6 2 6 6M16 5a3 3 0 010 6M18 14c2 1 3 3 3 6",
  "/clauses": "M4 6h16M4 12h10M4 18h13", "/ask": "M4 5h16v11H9l-5 4z", "/redline": "M4 20l4-1 11-11-3-3L5 16z", "/templates": "M12 3l9 5-9 5-9-5zM3 13l9 5 9-5",
  "/obligations": "M5 12l4 4 10-10M3 3h18v18H3z", "/spend": "M4 20V10M10 20V4M16 20v-7M22 20H2", "/risk": "M12 3l8 4v5c0 4-3 7-8 9-5-2-8-5-8-9V7z", "/new": "M12 5v14M5 12h14",
  "/alerts": "M6 17V11a6 6 0 0112 0v6l2 2H4zM10 21h4", "/admin": "M12 15a3 3 0 100-6 3 3 0 000 6zM12 2v3M12 19v3M2 12h3M19 12h3",
};
const NAV = [["/", "Overview"], ["/renewals", "Renewals"], ["/map", "Map"], ["/properties", "Properties"], ["/contracts", "Contracts"], ["/vendors", "Vendors"], ["/spend", "Spend"], ["/obligations", "Obligations"], ["/risk", "Risk"], ["/ask", "Ask"], ["/redline", "Redline"], ["/clauses", "Key clauses"], ["/templates", "Templates"]];

export function Layout() {
  const [dark, setDark] = useSetting("dark", window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false);
  useEffect(() => { document.documentElement.classList.toggle("dark", dark); }, [dark]);
  const meta = useQuery({ queryKey: ["meta"], queryFn: () => api<{ demo_mode: boolean; llm_available: boolean; llm_label: string; llm_provider: string; today: string }>("/api/meta") });
  const qc = useQueryClient();
  const modeSw = useMutation({ mutationFn: (demo: boolean) => api("/api/admin/mode", { method: "PUT", body: JSON.stringify({ demo }) }), onSuccess: () => qc.invalidateQueries() });
  const st = useQuery({ queryKey: ["status"], queryFn: () => api<Status>("/api/status"), refetchInterval: 10000 });
  const al = useQuery({ queryKey: ["alerts-summary"], queryFn: () => api<{ unread: number; open: number; critical: number }>("/api/alerts/summary"), refetchInterval: 30000 });
  const who = useQuery({ queryKey: ["whoami"], queryFn: () => api<{ email: string; name?: string; role: string; auth_required: boolean }>("/api/auth/me") });
  const lastRun = useRef<number | null>(null);
  useEffect(() => {
    // A pipeline run finished: refresh every screen, so all modules show the same new data.
    const id = st.data?.last_run?.id ?? null;
    if (lastRun.current !== null && id !== lastRun.current) qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "status" });
    lastRun.current = id;
  }, [st.data?.last_run?.id, qc]);
  const [open, setOpen] = useState(false);
  const link = (to: string, label: string, close?: () => void) => (
    <NavLink key={to} to={to} end={to === "/"} onClick={close}
      className={({ isActive }) => `whitespace-nowrap border-b-2 py-3.5 text-[13px] font-medium ${isActive ? "border-[#6F8CFF] text-white" : "border-transparent text-slate-300 hover:text-white"} max-md:flex max-md:min-h-[44px] max-md:items-center max-md:border-b-0 max-md:border-l-2 max-md:py-0 max-md:pl-3`}>
      {label}
    </NavLink>);
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 bg-ink text-slate-300">
        <div className="mx-auto flex max-w-[1440px] flex-wrap items-center gap-x-5 gap-y-1 px-4 md:px-6">
          <span className="flex items-center gap-2 py-3 font-bold tracking-tight text-white">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#6F8CFF" strokeWidth="2.2" aria-hidden><path d="M5 4h10l4 4v12H5z" /><path d="M9 13l2 2 4-4" /></svg>ContractIQ
          </span>
          <button className="ml-auto min-h-[44px] rounded border border-slate-600 px-3 text-sm text-white md:hidden" onClick={() => setOpen(!open)} aria-label="Menu" aria-expanded={open}>☰ Menu</button>
          <nav aria-label="Main" className={`${open ? "flex" : "hidden"} w-full flex-col md:flex md:w-auto md:flex-row md:gap-4`}>
            {NAV.map(([to, label]) => link(to, label, () => setOpen(false)))}
            {link("/admin", "Admin", () => setOpen(false))}
          </nav>
          <div className="ml-auto flex flex-wrap items-center gap-2 py-2 text-xs">
            <label className="flex cursor-pointer items-center gap-1.5 rounded-full border border-slate-600 px-2.5 py-1 text-slate-200" title="ON: demo mode, no Claude anywhere (offline engine, cached results, simulated external systems). OFF: live, every module is LLM-based.">
              <input type="checkbox" aria-label="Demo mode" checked={!!meta.data?.demo_mode} disabled={!meta.data || modeSw.isPending} onChange={(e) => modeSw.mutate(e.target.checked)} />
              <span className={`inline-block h-2 w-2 rounded-full ${meta.data?.demo_mode ? "bg-amber-400" : "bg-emerald-400"}`} aria-hidden />
              {meta.data?.demo_mode ? "Demo" : "Live"}<span className="hidden xl:inline"> · {meta.data ? (meta.data.demo_mode ? "no Claude" : meta.data.llm_label) : "…"}</span>
            </label>
            {st.data && (
              <NavLink to="/admin" className="flex items-center gap-1.5 rounded-full border border-slate-600 px-2.5 py-1" title={`Pipeline ${st.data.config.enabled ? "on" : "off"} · every ${st.data.config.interval_minutes} min`}>
                <span className={`inline-block h-2 w-2 rounded-full ${st.data.running ? "animate-pulse bg-amber-400" : st.data.config.enabled ? "bg-[#6F8CFF]" : "bg-slate-500"}`} aria-hidden />
                {st.data.running ? "Running…" : ago(st.data.config.last_run_at)}
              </NavLink>
            )}
            <NavLink to="/alerts" className="relative flex min-h-[36px] min-w-[36px] items-center justify-center rounded-full border border-slate-600" aria-label={`Alerts${al.data?.unread ? `, ${al.data.unread} unread` : ""}`} title="Notification centre">
              <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden><path d={ICON["/alerts"]} /></svg>
              {!!al.data?.unread && <span className="absolute -right-1 -top-1 min-w-[1.1rem] rounded-full bg-red-600 px-1 text-center text-[10px] font-bold leading-4 text-white">{al.data.unread > 99 ? "99+" : al.data.unread}</span>}
            </NavLink>
            {who.data?.auth_required && (
              <span className="flex items-center gap-1 text-slate-300" title={who.data.email}>{who.data.name || who.data.email} · {who.data.role}
                <NavLink to="/security" className="ml-1 underline">Security</NavLink><button className="ml-1 rounded border border-slate-600 px-1.5 py-0.5 hover:bg-ink-soft" onClick={() => { setToken(null); qc.clear(); window.dispatchEvent(new Event("ciq-signed-out")); }}>Sign out</button></span>)}
            <button onClick={() => setDark(!dark)} className="min-h-[36px] min-w-[36px] rounded-full border border-slate-600" aria-label="Toggle theme">{dark ? "☀" : "☾"}</button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-[1440px] px-4 py-5 md:px-6"><Outlet /></main>
    </div>
  );
}
