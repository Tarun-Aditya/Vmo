import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, daysLabel, fmtDate, usd } from "../lib";
import { Card, Loading, Sev, SeverityChip } from "../ui";

type Item = { id: number; title: string; vendor: string; type: string; expiry_date: string | null; auto_renew: boolean; notice_deadline: string | null; days_left: number | null; annual_value: number | null };
type MapData = { today: string; families: { vendor: string; items: Item[] }[] };

const MONTHS = 12, DAY = 86400000;
type Decision = { contract_id: number; decision: string; owner: string | null; note: string | null; decided_by: string | null; decided_at: string };
const DECISIONS: [string, string][] = [["renew", "Renew as is"], ["renegotiate", "Renegotiate"], ["exit", "Exit"], ["extend", "Extend short term"]];

/** What expires in the next 12 months, and the last day to act on each (expiry minus the notice period). */
export default function Renewals() {
  const q = useQuery({ queryKey: ["map", ""], queryFn: () => api<MapData>("/api/portfolio-map") });
  const [view, setView] = useState<"timeline" | "list">("timeline");
  const qc = useQueryClient();
  const dq = useQuery({ queryKey: ["renewal-decisions"], queryFn: () => api<Decision[]>("/api/renewals/decisions") });
  const [form, setForm] = useState({ contract_id: "", decision: "renegotiate", owner: "", note: "" });
  const save = useMutation({ mutationFn: () => api("/api/renewals/decisions", { method: "POST", body: JSON.stringify({ ...form, contract_id: Number(form.contract_id) }) }),
    onSuccess: () => { setForm({ ...form, note: "" }); qc.invalidateQueries({ queryKey: ["renewal-decisions"] }); } });
  const decided = Object.fromEntries((dq.data ?? []).map((d) => [d.contract_id, d]));
  if (!q.data) return <Loading q={q} />;
  const today = new Date(q.data.today + "T00:00:00"), start = new Date(today.getFullYear(), today.getMonth(), 1), end = new Date(start.getFullYear(), start.getMonth() + MONTHS, 1);
  const span = end.getTime() - start.getTime();
  const pos = (s: string) => Math.max(0, Math.min(100, ((new Date(s + "T00:00:00").getTime() - start.getTime()) / span) * 100));
  const all = q.data.families.flatMap((f) => f.items).filter((i) => i.expiry_date && i.type !== "Amendment" && i.days_left !== null && i.days_left >= -30 && new Date(i.expiry_date) < end);
  const key = (i: Item) => (i.auto_renew && i.notice_deadline ? (new Date(i.notice_deadline).getTime() - today.getTime()) / DAY : (i.days_left ?? 999));
  const rows = [...all].sort((a, b) => key(a) - key(b));
  const months = Array.from({ length: MONTHS }, (_, i) => new Date(start.getFullYear(), start.getMonth() + i, 1));
  const sevOf = (i: Item): Sev => { const k = key(i); return k < 0 ? "critical" : k <= 30 ? "critical" : k <= 60 ? "high" : k <= 90 ? "medium" : "low"; };
  const why = (i: Item) => (i.auto_renew && i.notice_deadline ? (key(i) < 0 ? `Notice passed ${Math.round(-key(i))} days ago` : `Last day to cancel ${fmtDate(i.notice_deadline)}`) : `Ends ${fmtDate(i.expiry_date)} · ${daysLabel(i.days_left ?? 0)}`);
  const colour = (i: Item) => { const k = i.days_left ?? 999; return k <= 30 ? "#D14A3D" : k <= 90 ? "#E89B2D" : "#8EA3E8"; };
  const month = rows.filter((i) => key(i) <= 30);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h1 className="font-serif text-3xl md:text-4xl">Renewals</h1><div className="text-sm text-ink-mute dark:text-slate-400">What expires in the next 12 months, and the last day to act on each.</div></div>
        <div className="inline-flex overflow-hidden rounded-md border border-slate-300 bg-white text-[12.5px] font-semibold dark:border-slate-600 dark:bg-slate-800" role="group" aria-label="View">
          {(["timeline", "list"] as const).map((v) => <button key={v} className={`min-h-[32px] px-3 capitalize ${view === v ? "bg-ink text-white" : "text-ink-mute"}`} onClick={() => setView(v)}>{v}</button>)}</div>
      </div>
      <div className="flex flex-wrap items-start gap-4">
        <section className="min-w-0 flex-[999_1_760px] overflow-hidden rounded-lg border border-line bg-white dark:border-slate-700 dark:bg-slate-800" aria-label="Renewals">
          {view === "timeline" ? (
            <div className="overflow-x-auto"><div className="min-w-[820px]">
              <div className="grid grid-cols-[260px_1fr_80px] border-b border-line bg-slate-50 dark:border-slate-700 dark:bg-slate-900"><div className="px-3 py-2 text-[11.5px] font-semibold uppercase tracking-wide text-ink-mute">Contract</div>
                <div className="grid" style={{ gridTemplateColumns: `repeat(${MONTHS}, 1fr)` }}>{months.map((m, i) => <div key={i} className="border-l border-line py-2 text-center text-[11.5px] font-semibold uppercase text-ink-mute dark:border-slate-700">{m.toLocaleDateString("en-GB", { month: "short" })}{m.getMonth() === 0 ? ` ${String(m.getFullYear()).slice(2)}` : ""}</div>)}</div>
                <div className="px-3 py-2 text-right text-[11.5px] font-semibold uppercase text-ink-mute">Value</div></div>
              <div className="relative">
                <div className="pointer-events-none absolute bottom-0 top-0 z-10 w-0.5 bg-indigo-600" style={{ left: `calc(260px + (100% - 340px) * ${pos(q.data.today) / 100})` }} title="today" />
                {rows.map((i) => (
                  <div key={i.id} className="grid grid-cols-[260px_1fr_80px] items-center border-t border-slate-100 dark:border-slate-700">
                    <div className="min-w-0 px-3 py-2"><Link to={`/contracts/${i.id}`} className="block truncate text-[13px] font-semibold hover:underline" title={i.title}>{i.title}</Link><div className="truncate text-[11.5px] text-ink-mute">{i.vendor} · {i.type}{decided[i.id] && <span className="ml-1 rounded bg-indigo-100 px-1 font-semibold text-indigo-900">{decided[i.id].decision}</span>}</div></div>
                    <div className="relative h-9">
                      <span className="absolute top-3 h-3.5 rounded" style={{ left: `${pos(q.data.today)}%`, width: `${Math.max(pos(i.expiry_date!) - pos(q.data.today), 1)}%`, background: colour(i) }} />
                      {i.auto_renew && i.notice_deadline && <span className="absolute top-[9px] z-10" style={{ left: `calc(${pos(i.notice_deadline)}% - 7px)` }} title={`Last day to act: ${fmtDate(i.notice_deadline)}`}>
                        {key(i) <= 30 ? <svg width="14" height="14" viewBox="0 0 10 10"><path d="M5 0l5 5-5 5-5-5z" fill="#B3261E" /></svg> : <svg width="14" height="14" viewBox="0 0 10 10"><path d="M5 0l5 10H0z" fill="#C2570C" /></svg>}</span>}
                      <span className="num absolute top-2.5 text-[11.5px] text-ink-mute" style={{ left: `calc(${pos(i.expiry_date!)}% + 8px)` }}>{fmtDate(i.expiry_date)}</span>
                    </div>
                    <div className="num px-3 text-right text-[13px]">{usd(i.annual_value)}</div>
                  </div>))}
                {!rows.length && <p className="p-6 text-center text-sm text-ink-mute">Nothing expires in the next 12 months.</p>}
              </div>
            </div></div>
          ) : (
            <table className="w-full text-[13px]"><thead className="bg-slate-50 dark:bg-slate-900"><tr>{["Why", "Contract", "Vendor", "Ends", "Annual value"].map((h, n) => <th key={h} className={`px-3 py-2 text-[11.5px] font-semibold uppercase tracking-wide text-ink-mute ${n === 4 ? "text-right" : "text-left"}`}>{h}</th>)}</tr></thead>
              <tbody>{rows.map((i) => <tr key={i.id} className="border-t border-slate-100 dark:border-slate-700"><td className="px-3 py-2"><SeverityChip sev={sevOf(i)} label={why(i)} /></td><td className="px-3 py-2"><Link to={`/contracts/${i.id}`} className="font-semibold text-indigo-600 hover:underline">{i.title}</Link></td><td className="px-3 py-2">{i.vendor}{decided[i.id] && <span className="ml-1 rounded bg-indigo-100 px-1 text-[11px] font-semibold text-indigo-900">{decided[i.id].decision}</span>}</td><td className="num px-3 py-2">{fmtDate(i.expiry_date)}</td><td className="num px-3 py-2 text-right">{usd(i.annual_value)}</td></tr>)}</tbody></table>)}
          <div className="border-t border-line px-3 py-2 text-xs text-ink-mute dark:border-slate-700">Blue line = today · bar ends at expiry · ◆ ▲ = last day to act (passed or within 30 days · later)</div>
        </section>
        <aside className="flex min-w-0 flex-[1_1_300px] flex-col gap-4">
          <Card title="Decisions this month">
            <ul className="space-y-2 text-[13px]">{month.map((i) => <li key={i.id} className="flex items-start justify-between gap-2"><Link to={`/contracts/${i.id}`} className="font-semibold hover:underline">{i.vendor.replace(/ (Inc|LLC|LLP|Ltd)\.?$/, "")}</Link><SeverityChip sev={sevOf(i)} label={why(i)} /></li>)}
              {!month.length && <li className="text-ink-mute">No decision is due in the next 30 days.</li>}</ul>
          </Card>
          <Card title="Record a decision">
            <form className="space-y-2.5 text-[13px]" onSubmit={(e) => { e.preventDefault(); if (form.contract_id) save.mutate(); }}>
              <label className="block">Contract<select className="mt-1 block min-h-[36px] w-full rounded border border-slate-300 bg-white px-2 dark:border-slate-600 dark:bg-slate-900" value={form.contract_id} onChange={(e) => setForm({ ...form, contract_id: e.target.value })} required>
                <option value="">Choose…</option>{rows.map((i) => <option key={i.id} value={i.id}>{i.vendor} · {i.title}</option>)}</select></label>
              <label className="block">Decision<select className="mt-1 block min-h-[36px] w-full rounded border border-slate-300 bg-white px-2 dark:border-slate-600 dark:bg-slate-900" value={form.decision} onChange={(e) => setForm({ ...form, decision: e.target.value })}>{DECISIONS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
              <label className="block">Owner<input className="mt-1 block min-h-[36px] w-full rounded border border-slate-300 bg-white px-2 dark:border-slate-600 dark:bg-slate-900" value={form.owner} onChange={(e) => setForm({ ...form, owner: e.target.value })} placeholder="who will act" /></label>
              <label className="block">Note<input className="mt-1 block min-h-[36px] w-full rounded border border-slate-300 bg-white px-2 dark:border-slate-600 dark:bg-slate-900" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} placeholder="why" /></label>
              <button className="inline-flex min-h-[36px] items-center rounded-md border border-indigo-600 bg-indigo-600 px-4 text-[13px] font-semibold text-white disabled:opacity-50" disabled={!form.contract_id || save.isPending}>{save.isPending ? "Saving…" : "Save decision"}</button>
              {save.isSuccess && <span className="ml-2 text-indigo-700">Saved</span>}{save.isError && <span className="ml-2 text-red-700">Could not save</span>}
            </form>
          </Card>
        </aside>
      </div>
    </div>
  );
}
