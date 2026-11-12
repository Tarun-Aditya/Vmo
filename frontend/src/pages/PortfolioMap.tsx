import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, fmtDate, usd } from "../lib";
import { Card, Loading, Sev, SeverityChip } from "../ui";

type Item = { id: number; title: string; vendor: string; type: string; parent_id: number | null; property: string | null; effective_date: string | null; expiry_date: string | null;
  auto_renew: boolean; notice_days: number | null; notice_deadline: string | null; days_left: number | null; annual_value: number | null; uncapped: boolean };
type Issue = { severity: "critical" | "high" | "medium"; kind: string; contract_id: number; title: string; vendor: string; detail: string; action: string };
type Map = { today: string; families: { vendor: string; category: string; items: Item[] }[]; issues: Issue[]; properties: { property: string; contracts: number }[];
  summary: { families: number; documents: number; ending_90: number; problems: number; no_end_date: number; notice_passed: number } };

const MONTHS_BACK = 1, MONTHS = 15;
const DAY = 86400000;
const KIND: Record<string, string> = { child_outlives_parent: "Child outlives parent", nda_before_msa: "NDA ends before its agreement", orphan: "No parent agreement", no_end_date: "No end date found", notice_unknown: "Auto-renews, notice unknown" };

/** Every contract family on one timeline: the parent first, its schedules and amendments beneath, the last day to act marked on each. */
export default function PortfolioMap() {
  const [sp] = useSearchParams();
  const [property, setProperty] = useState(sp.get("property") ?? ""); const [vendor, setVendor] = useState(sp.get("vendor") ?? "");
  const f = useQuery({ queryKey: ["filters"], queryFn: () => api<Record<string, string[]>>("/api/contracts/filters") });
  const q = useQuery({ queryKey: ["map", property, vendor], queryFn: () => api<Map>(`/api/portfolio-map?${new URLSearchParams({ ...(property && { property }), ...(vendor && { vendor }) })}`) });
  if (!q.data) return <Loading q={q} />;
  const d = q.data, today = new Date(d.today + "T00:00:00");
  const start = new Date(today.getFullYear(), today.getMonth() - MONTHS_BACK, 1), end = new Date(start.getFullYear(), start.getMonth() + MONTHS, 1);
  const span = end.getTime() - start.getTime();
  const pos = (s: string) => Math.max(0, Math.min(100, ((new Date(s + "T00:00:00").getTime() - start.getTime()) / span) * 100));
  const months = Array.from({ length: MONTHS }, (_, i) => new Date(start.getFullYear(), start.getMonth() + i, 1));
  const todayPct = ((today.getTime() - start.getTime()) / span) * 100;
  const flagged = new Set(d.issues.filter((i) => i.severity !== "medium").map((i) => i.contract_id));
  const tone = (dl: number | null) => (dl === null ? "#B8B2A4" : dl <= 30 ? "#D9695B" : dl <= 90 ? "#E5A24F" : "#2E8F80");
  const sev = (i: Item): Sev | null => (i.notice_deadline ? (new Date(i.notice_deadline) < today ? "critical" : (new Date(i.notice_deadline).getTime() - today.getTime()) / DAY <= 30 ? "high" : "medium") : null);
  const shape = (s: Sev) => (s === "critical" ? <svg width="14" height="14" viewBox="0 0 10 10"><path d="M5 0l5 5-5 5-5-5z" fill="#B42318" /></svg> : s === "high" ? <svg width="14" height="14" viewBox="0 0 10 10"><path d="M5 0l5 10H0z" fill="#C2570C" /></svg> : <svg width="14" height="14" viewBox="0 0 10 10"><circle cx="5" cy="5" r="5" fill="#8A6D00" /></svg>);
  return (
    <div className="space-y-6">
      <header><h1 className="font-serif text-3xl md:text-4xl">Portfolio map</h1>
        <p className="mt-1 text-sm text-ink-mute dark:text-slate-400">All contracts as families: the parent, its schedules and amendments, with the last day to act on each.</p></header>
      <section className="grid grid-cols-2 gap-4 lg:grid-cols-5" aria-label="Summary">
        {[["Contract families", d.summary.families, `${d.summary.documents} documents`, ""], ["Ending within 90 days", d.summary.ending_90, "", "border-orange-400"], ["Hierarchy and data problems", d.summary.problems, "need a look", "border-red-500"],
          ["Missing end dates", d.summary.no_end_date, "", ""], ["Notice already passed", d.summary.notice_passed, "", "border-red-500"]].map(([l, v, s, c]) => (
          <div key={String(l)} className={`rounded-xl border bg-white p-4 dark:bg-slate-800 ${c || "border-line dark:border-slate-700"}`}><div className="text-xs font-semibold uppercase tracking-wider text-ink-mute dark:text-slate-400">{l}</div>
            <div className="mt-1 font-serif text-4xl tabular-nums">{v}</div><div className="text-xs text-ink-mute dark:text-slate-400">{s}</div></div>))}
      </section>
      <div className="flex flex-wrap items-start gap-5">
        <section className="min-w-0 flex-[999_1_760px] overflow-hidden rounded-xl border border-line bg-white dark:border-slate-700 dark:bg-slate-800" aria-label="Timeline of all contracts">
          <div className="flex flex-wrap items-end gap-3 border-b border-line p-3 dark:border-slate-700">
            <label className="text-xs">Property<select className="mt-1 block min-h-[40px] rounded border border-slate-300 bg-white px-2 text-sm dark:border-slate-600 dark:bg-slate-900" value={property} onChange={(e) => setProperty(e.target.value)}><option value="">All properties</option>{(f.data?.property ?? []).map((p) => <option key={p}>{p}</option>)}</select></label>
            <label className="text-xs">Vendor<select className="mt-1 block min-h-[40px] rounded border border-slate-300 bg-white px-2 text-sm dark:border-slate-600 dark:bg-slate-900" value={vendor} onChange={(e) => setVendor(e.target.value)}><option value="">All vendors</option>{(f.data?.vendor ?? []).map((p) => <option key={p}>{p}</option>)}</select></label>
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-mute dark:text-slate-400">
              {[["#D9695B", "ends within 30 days"], ["#E5A24F", "within 90 days"], ["#2E8F80", "later"]].map(([c, t]) => <span key={t}><span className="mr-1 inline-block h-2.5 w-3.5 rounded" style={{ background: c }} />{t}</span>)}
              <span><span className="mr-1 inline-block h-2.5 w-3.5 rounded border-2 border-dashed border-slate-500" />no end date</span><span><span className="mr-1 inline-block h-2.5 w-3.5 rounded outline outline-2 outline-red-700" />hierarchy problem</span><span>◆ ▲ ● last day to act: passed, ≤30 days, later</span></div>
          </div>
          <div className="overflow-x-auto"><div className="min-w-[860px]">
            <div className="grid grid-cols-[300px_1fr] border-b border-slate-300 dark:border-slate-600"><div className="p-2 text-xs font-semibold uppercase text-ink-mute">Contract family</div>
              <div className="grid" style={{ gridTemplateColumns: `repeat(${MONTHS}, 1fr)` }}>{months.map((m, i) => <div key={i} className="border-l border-line py-2 text-center text-[11px] font-semibold uppercase text-ink-mute dark:border-slate-700">{m.toLocaleDateString("en-GB", { month: "short" })}{m.getMonth() === 0 || i === 0 ? ` ${String(m.getFullYear()).slice(2)}` : ""}</div>)}</div></div>
            <div className="relative">
              <div className="pointer-events-none absolute bottom-0 top-0 z-10 w-0.5 bg-indigo-600" style={{ left: `calc(300px + (100% - 300px) * ${todayPct / 100})` }} title="today" />
              {d.families.map((fam) => {
                const ids = new Set(fam.items.map((i) => i.id));
                return (
                  <div key={fam.vendor}>
                    <div className="border-t border-line bg-paper px-3 py-2 text-sm font-semibold dark:border-slate-700 dark:bg-slate-900"><Link to={`/vendors/${encodeURIComponent(fam.vendor)}`} className="hover:underline">{fam.vendor}</Link> <span className="font-normal text-ink-mute">· {fam.category}</span></div>
                    {fam.items.map((i) => {
                      const child = !!i.parent_id && ids.has(i.parent_id);
                      const s0 = i.effective_date ? pos(i.effective_date) : 0, e0 = i.expiry_date ? pos(i.expiry_date) : 100, w = Math.max(e0 - s0, 2), sv = sev(i);
                      return (
                        <div key={i.id} className="grid grid-cols-[300px_1fr] items-center border-t border-line dark:border-slate-700">
                          <div className="min-w-0 py-2 pr-2" style={{ paddingLeft: child ? 28 : 12 }}>
                            <Link to={`/contracts/${i.id}`} className="block truncate text-[13px] font-semibold hover:underline" title={i.title}>{child ? "└ " : ""}{i.title}</Link>
                            <div className="truncate text-[11px] text-ink-mute dark:text-slate-400">{i.type}{i.property ? ` · ${i.property}` : ""} · {i.expiry_date ? `ends ${fmtDate(i.expiry_date)}` : "no end date found"}{i.annual_value ? ` · ${usd(i.annual_value)}` : ""}</div>
                          </div>
                          <div className="relative my-1.5 h-8">
                            {i.type === "Amendment" ? <span className="absolute left-1 top-1.5 rounded bg-slate-200 px-1.5 text-[11px] font-semibold dark:bg-slate-700">overrides parent</span> : (
                              <span className={`absolute top-1.5 flex h-5 items-center overflow-hidden whitespace-nowrap rounded-md px-2 text-[11px] font-semibold ${i.expiry_date ? (i.days_left !== null && i.days_left <= 90 && i.days_left > 30 ? "text-slate-900" : "text-white") : "border-2 border-dashed border-slate-500 bg-paper text-slate-900"} ${flagged.has(i.id) ? "outline outline-2 outline-offset-2 outline-red-700" : ""}`}
                                style={{ left: `${s0}%`, width: `${w}%`, background: i.expiry_date ? tone(i.days_left) : undefined }}>{i.expiry_date ? fmtDate(i.expiry_date) : "?"}</span>)}
                            {i.notice_deadline && sv && <span className="absolute top-2 z-10" style={{ left: `calc(${pos(i.notice_deadline)}% - 7px)` }} title={`Last day to act: ${fmtDate(i.notice_deadline)}`}>{shape(sv)}</span>}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                );
              })}
              {!d.families.length && <p className="p-6 text-center text-sm text-ink-mute">No contracts match.</p>}
            </div>
          </div></div>
        </section>
        <aside className="flex min-w-0 flex-[1_1_320px] flex-col gap-5">
          <Card title={<span className="flex items-center gap-2">Needs a look <SeverityChip sev="critical" label={`${d.issues.length} open`} /></span>}>
            <ul className="divide-y divide-line text-sm dark:divide-slate-700">
              {d.issues.map((i, n) => (
                <li key={n} className="py-3"><div className="flex flex-wrap items-center gap-2"><SeverityChip sev={i.severity} label={i.severity} /><b>{KIND[i.kind] ?? i.kind}</b></div>
                  <div className="mt-0.5 text-ink-mute dark:text-slate-400"><Link to={`/contracts/${i.contract_id}`} className="font-medium text-indigo-600 hover:underline">{i.title}</Link>. {i.detail}</div>
                  <div className="mt-1 text-xs font-semibold text-indigo-700 dark:text-indigo-300">{i.action} ›</div></li>))}
              {!d.issues.length && <li className="py-4 text-center text-ink-mute">No hierarchy or date problems found.</li>}
            </ul>
          </Card>
          {!!d.properties.length && (
            <Card title="Contracts by property">
              <ul className="space-y-1 text-sm">{d.properties.map((p) => <li key={p.property} className="flex justify-between gap-2"><button className="text-left text-indigo-600 hover:underline" onClick={() => setProperty(p.property)}>{p.property}</button><span className="tabular-nums">{p.contracts}</span></li>)}</ul>
            </Card>)}
        </aside>
      </div>
    </div>
  );
}
