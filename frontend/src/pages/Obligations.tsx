import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Pill, Tile } from "../components/vmo";
import { Btn, Field, inputCls } from "../forms";
import { api, fmtDate, usd } from "../lib";
import { Card, Loading, Td, Th } from "../ui";

type Ob = { obligation_id: number; contract_id: number; contract: string; vendor: string; type: string; kind: string; party: string; obligation: string; due_date: string | null; frequency: string; target_value: number | null; target_unit: string | null; status: "open" | "overdue" | "done" | "waived"; completed_on: string | null; days_left: number | null; source: string };
type ObRes = { rows: Ob[]; summary: { open: number; overdue: number; due_30: number; done: number; ongoing: number }; kinds: string[]; vendors: string[] };
type Series = { contract_id: number; title: string; vendor: string; metric_key: string; target: number | null; unit: string; points: { period: string; actual: number; breach: boolean; incidents: number; credit_usd: number }[]; breaches: number; credit_usd: number };
type SlaRes = { series: Series[]; summary: { contracts: number; breach_months: number; credit_usd: number; compliant: number } };

const STATUS: Record<Ob["status"], { label: string; cls: string }> = {
  overdue: { label: "▲▲ Overdue", cls: "bg-red-100 text-red-900 dark:bg-red-950 dark:text-red-200" },
  open: { label: "Open", cls: "bg-sky-100 text-sky-900 dark:bg-sky-950 dark:text-sky-200" },
  done: { label: "✓ Done", cls: "bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200" },
  waived: { label: "Waived", cls: "bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200" },
};
const KIND: Record<string, string> = { milestone: "Milestone", sla: "SLA", notice: "Notice", payment: "Payment", acceptance: "Acceptance", personnel: "Key personnel", cure: "Breach cure", audit: "Audit", renewal: "Renewal", warranty: "Warranty", insurance: "Insurance" };
const METRIC: Record<string, string> = { sla_availability_pct: "Availability", incident_notice_hours: "Incident notification time" };

function SlaCard({ s }: { s: Series }) {
  const data = s.points.map((p) => ({ ...p, label: new Date(p.period).toLocaleDateString("en-US", { month: "short", year: "2-digit" }) }));
  const lo = Math.min(...data.map((d) => d.actual), s.target ?? Infinity), hi = Math.max(...data.map((d) => d.actual), s.target ?? -Infinity);
  const pad = (hi - lo) * 0.25 || 1;
  return (
    <Card title={<span>{METRIC[s.metric_key] ?? s.metric_key} · <Link className="text-indigo-600 hover:underline dark:text-indigo-400" to={`/contracts/${s.contract_id}`}>{s.title}</Link></span>}
      right={s.breaches ? <Pill cls="bg-red-100 text-red-900 dark:bg-red-950 dark:text-red-200">▲▲ {s.breaches} breach{s.breaches > 1 ? "es" : ""}{s.credit_usd ? ` · ~${usd(s.credit_usd)} credit` : ""}</Pill> : <Pill cls="bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200">✓ within target</Pill>}>
      <div className="text-xs text-slate-500">{s.vendor} · target {s.metric_key === "sla_availability_pct" ? `≥ ${s.target}%` : `≤ ${s.target} ${s.unit}`}</div>
      <div className="mt-2 h-40" role="img" aria-label={`${METRIC[s.metric_key]} by month against the target of ${s.target}`}>
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#cbd5e1" />
            <XAxis dataKey="label" tick={{ fontSize: 11 }} />
            <YAxis domain={[Math.floor((lo - pad) * 100) / 100, Math.ceil((hi + pad) * 100) / 100]} tick={{ fontSize: 11 }} width={46} />
            <Tooltip formatter={(v: number) => [`${v}${s.unit === "%" ? "%" : " h"}`, "Actual"]} />
            {s.target !== null && <ReferenceLine y={s.target} stroke="#dc2626" strokeDasharray="5 4" label={{ value: "target", position: "insideTopRight", fontSize: 10, fill: "#dc2626" }} />}
            <Line type="linear" dataKey="actual" stroke="#4f46e5" strokeWidth={2} isAnimationActive={false} dot={(p: { cx?: number; cy?: number; payload?: { breach: boolean }; index?: number }) => <circle key={p.index} cx={p.cx} cy={p.cy} r={p.payload?.breach ? 6 : 3.5} fill={p.payload?.breach ? "#dc2626" : "#4f46e5"} stroke="#fff" strokeWidth={1.5} />} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      {s.breaches > 0 && <ul className="mt-1 text-xs text-slate-600 dark:text-slate-300">{s.points.filter((p) => p.breach).map((p) => <li key={p.period}>▲ {fmtDate(p.period)}: {p.actual}{s.unit === "%" ? "%" : " h"}{p.credit_usd ? ` · estimated service credit ${usd(p.credit_usd)}` : ""}</li>)}</ul>}
    </Card>
  );
}

export default function Obligations() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<"obl" | "sla">("obl");
  const [status, setStatus] = useState("");
  const [kind, setKind] = useState("");
  const [vendor, setVendor] = useState("");
  const [party, setParty] = useState("");
  const [find, setFind] = useState("");
  const qs = new URLSearchParams({ ...(status && { status }), ...(kind && { kind }), ...(vendor && { vendor }), ...(party && { party }), ...(find && { q: find }) }).toString();
  const q = useQuery({ queryKey: ["obligations", qs], queryFn: () => api<ObRes>(`/api/obligations?${qs}`) });
  const sla = useQuery({ queryKey: ["sla"], queryFn: () => api<SlaRes>("/api/sla") });
  const patch = useMutation({
    mutationFn: (v: { id: number; status: string }) => api(`/api/obligations/${v.id}`, { method: "PATCH", body: JSON.stringify({ status: v.status }) }),
    onSuccess: () => qc.invalidateQueries(),
  });
  const [m, setM] = useState({ contract_id: 0, metric_key: "sla_availability_pct", period: new Date().toISOString().slice(0, 7) + "-01", actual: "", note: "" });
  const add = useMutation({
    mutationFn: () => api("/api/sla/measurements", { method: "POST", body: JSON.stringify({ ...m, actual: Number(m.actual) }) }),
    onSuccess: () => { qc.invalidateQueries(); setM({ ...m, actual: "", note: "" }); },
  });
  if (!q.data) return <Loading q={q} />;
  const sm = q.data.summary;
  return (
    <div className="space-y-4">
      <div>
        <h1>Obligations & SLAs</h1>
        <p className="text-sm text-slate-500">What each party must do under every contract — milestones, SLA targets, notices, renewals, insurance — read from the documents, with dates and status. SLA actuals come from monitoring feeds.</p>
      </div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Tile l="Overdue" v={sm.overdue} tone={sm.overdue ? "red" : undefined} sub="open and past their date" />
        <Tile l="Due in 30 days" v={sm.due_30} tone={sm.due_30 ? "amber" : undefined} />
        <Tile l="Open" v={sm.open} sub={`${sm.ongoing} ongoing, no date`} />
        <Tile l="Done" v={sm.done} tone="green" />
        <Tile l="SLA breach months" v={sla.data?.summary.breach_months ?? "…"} tone={sla.data?.summary.breach_months ? "red" : undefined} sub={sla.data ? `~${usd(sla.data.summary.credit_usd)} estimated credits` : undefined} />
      </div>
      <div className="flex gap-2" role="tablist">
        {([["obl", "Obligations"], ["sla", "SLA performance"]] as const).map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)} className={`rounded-t px-3 py-1.5 text-sm font-medium ${tab === k ? "bg-indigo-600 text-white" : "bg-slate-200 dark:bg-slate-700"}`}>{l}</button>)}
      </div>

      {tab === "obl" && (
        <Card>
          <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
            {[["", "All"], ["overdue", "Overdue"], ["open", "Open"], ["done", "Done"]].map(([v, l]) => <button key={v} onClick={() => setStatus(v)} aria-pressed={status === v} className={`rounded px-2 py-1 ${status === v ? "bg-indigo-600 text-white" : "bg-slate-100 dark:bg-slate-700"}`}>{l}</button>)}
            <select className={`${inputCls} w-auto`} aria-label="Kind" value={kind} onChange={(e) => setKind(e.target.value)}><option value="">All kinds</option>{q.data.kinds.map((k) => <option key={k} value={k}>{KIND[k] ?? k}</option>)}</select>
            <select className={`${inputCls} w-auto`} aria-label="Vendor" value={vendor} onChange={(e) => setVendor(e.target.value)}><option value="">All vendors</option>{q.data.vendors.map((v) => <option key={v}>{v}</option>)}</select>
            <select className={`${inputCls} w-auto`} aria-label="Party" value={party} onChange={(e) => setParty(e.target.value)}><option value="">Either party</option><option>Supplier</option><option>Customer</option><option>Both</option></select>
            <input className={`${inputCls} w-48`} placeholder="Search…" aria-label="Search obligations" value={find} onChange={(e) => setFind(e.target.value)} />
            <span className="ml-auto text-xs text-slate-500">{q.data.rows.length} shown</span>
          </div>
          <div className="max-h-[34rem] overflow-auto">
            <table className="w-full text-sm" aria-label="Obligations">
              <thead className="sticky top-0 bg-slate-100 dark:bg-slate-900"><tr><Th>Status</Th><Th>Obligation</Th><Th>Contract</Th><Th>Due</Th><Th>{""}</Th></tr></thead>
              <tbody>
                {q.data.rows.map((o) => (
                  <tr key={o.obligation_id} className="border-t border-slate-100 align-top dark:border-slate-700">
                    <Td><span className={`rounded px-1.5 py-0.5 text-xs font-semibold ${STATUS[o.status].cls}`}>{STATUS[o.status].label}</span></Td>
                    <Td><div>{o.obligation}</div><div className="mt-0.5 flex flex-wrap gap-1"><Pill>{KIND[o.kind] ?? o.kind}</Pill><Pill cls={o.party === "Customer" ? "bg-indigo-100 text-indigo-900 dark:bg-indigo-950 dark:text-indigo-200" : undefined}>{o.party}</Pill>{o.source === "llm" && <Pill cls="bg-violet-100 text-violet-900 dark:bg-violet-950 dark:text-violet-200">found by Claude</Pill>}{o.frequency !== "once" && o.frequency !== "event" && <Pill>{o.frequency}</Pill>}</div></Td>
                    <Td><Link className="text-indigo-600 hover:underline dark:text-indigo-400" to={`/contracts/${o.contract_id}`}>{o.contract}</Link><div className="text-xs text-slate-500">{o.vendor}</div></Td>
                    <Td className="whitespace-nowrap">{o.due_date ? <><div>{fmtDate(o.due_date)}</div><div className={`text-xs ${o.status === "overdue" ? "font-semibold text-red-600" : "text-slate-500"}`}>{o.status === "done" ? `done ${fmtDate(o.completed_on)}` : o.days_left! < 0 ? `${-o.days_left!} days late` : `in ${o.days_left} days`}</div></> : <span className="text-slate-400">{o.frequency === "event" ? "when it occurs" : "ongoing"}</span>}</Td>
                    <Td className="whitespace-nowrap text-right">
                      {o.status === "done" ? <button className="text-xs text-indigo-600 hover:underline" onClick={() => patch.mutate({ id: o.obligation_id, status: "open" })}>Reopen</button>
                        : <><button className="rounded border border-emerald-600 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:text-emerald-300" onClick={() => patch.mutate({ id: o.obligation_id, status: "done" })} aria-label={`Mark done: ${o.obligation}`}>Mark done</button>{o.status !== "waived" && <button className="ml-2 text-xs text-slate-500 hover:underline" onClick={() => patch.mutate({ id: o.obligation_id, status: "waived" })}>Waive</button>}</>}
                    </Td>
                  </tr>))}
                {q.data.rows.length === 0 && <tr><td colSpan={5} className="py-6 text-center text-slate-500">Nothing matches.</td></tr>}
              </tbody>
            </table>
          </div>
        </Card>)}

      {tab === "sla" && (
        <div className="space-y-4">
          {!sla.data && <Loading q={sla} />}
          {sla.data && (
            <>
              <p className="text-sm text-slate-600 dark:text-slate-300">{sla.data.summary.contracts} contracts have SLA targets in their text; monthly actuals arrive in the feeds folder (sla*.csv) or are entered below. Service credits are an estimate from typical tiers (5% / 10% / 20% of the monthly fee) — the clause's own tiers are not extracted yet.</p>
              <div className="grid gap-4 lg:grid-cols-2">{sla.data.series.map((s) => <SlaCard key={`${s.contract_id}${s.metric_key}`} s={s} />)}</div>
              <Card title="Add a measurement">
                <div className="grid gap-3 sm:grid-cols-5">
                  <Field label="Contract"><select className={inputCls} aria-label="Contract" value={m.contract_id} onChange={(e) => setM({ ...m, contract_id: Number(e.target.value) })}><option value={0}>Choose…</option>{[...new Map(sla.data.series.map((s) => [s.contract_id, s])).values()].map((s) => <option key={s.contract_id} value={s.contract_id}>{s.title}</option>)}</select></Field>
                  <Field label="Measure"><select className={inputCls} aria-label="Measure" value={m.metric_key} onChange={(e) => setM({ ...m, metric_key: e.target.value })}><option value="sla_availability_pct">Availability %</option><option value="incident_notice_hours">Incident notification (hours)</option></select></Field>
                  <Field label="Month"><input className={inputCls} type="date" aria-label="Month" value={m.period} onChange={(e) => setM({ ...m, period: e.target.value })} /></Field>
                  <Field label="Actual"><input className={inputCls} type="number" step="any" aria-label="Actual" value={m.actual} onChange={(e) => setM({ ...m, actual: e.target.value })} /></Field>
                  <div className="flex items-end"><Btn onClick={() => add.mutate()} disabled={!m.contract_id || !m.actual || add.isPending}>{add.isPending ? "Saving…" : "Save"}</Btn></div>
                </div>
                {add.error && <p className="mt-2 text-sm text-red-600">{String(add.error)}</p>}
                {add.isSuccess && <p className="mt-2 text-sm text-emerald-700">Saved — charts and vendor risk scores updated.</p>}
              </Card>
            </>)}
        </div>)}
    </div>
  );
}
