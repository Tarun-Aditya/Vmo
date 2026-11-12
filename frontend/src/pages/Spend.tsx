import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Meter, Pill, Tile } from "../components/vmo";
import { Btn, Field, inputCls } from "../forms";
import { api, fmtDate, usd } from "../lib";
import { Card, Loading, Sev, SeverityChip, Td, Th } from "../ui";

type Summary = { billed: number; billed_90d: number; invoices: number; off_contract: number; planned: number; exceptions: number; at_risk: number; serious: number;
  by_vendor: { vendor: string; billed: number; planned: number; exceptions: number; at_risk: number }[]; monthly: { month: string; on_contract: number | null; off_contract: number | null }[];
  by_kind: { kind: string; severity: Sev; n: number; at_risk: number }[] };
type CS = { contract_id: number; title: string; vendor: string; type: string; effective_date: string; expiry_date: string; planned_value: number; billed: number; invoices: number; last_invoice: string | null; elapsed_pct: number; expected_to_date: number; pct_of_planned: number | null; exceptions: number };
type Ex = { exception_id: number; kind: string; severity: Sev; amount_at_risk: number; detail: string; vendor: string; contract_id: number | null; contract_title: string | null; invoice_no: string | null; invoice_date: string | null };

export const KIND: Record<string, string> = { no_contract: "No contract on file", unsigned_contract: "Billed against an unsigned contract", billed_before_effective: "Billed before the contract starts", billed_after_expiry: "Billed after expiry", duplicate: "Duplicate invoice",
  above_run_rate: "Above the usual invoice", over_contract_value: "Over the contract value", late_payment: "Paid late" };

export default function Spend() {
  const qc = useQueryClient();
  const sum = useQuery({ queryKey: ["spend-summary"], queryFn: () => api<Summary>("/api/spend/summary") });
  const cs = useQuery({ queryKey: ["spend-contracts"], queryFn: () => api<CS[]>("/api/spend/contracts") });
  const [sev, setSev] = useState("");
  const [kind, setKind] = useState("");
  const qs = new URLSearchParams({ ...(sev && { severity: sev }), ...(kind && { kind }) }).toString();
  const ex = useQuery({ queryKey: ["spend-exceptions", qs], queryFn: () => api<Ex[]>(`/api/spend/exceptions?${qs}`) });
  const file = useRef<HTMLInputElement>(null);
  const [feed, setFeed] = useState({ name: "invoices_export.csv", content: "" });
  const up = useMutation({ mutationFn: () => api<{ new_docs: number; updated: number; exceptions: number }>("/api/feeds/upload", { method: "POST", body: JSON.stringify(feed) }), onSuccess: () => qc.invalidateQueries() });
  if (!sum.data) return <Loading q={sum} />;
  const s = sum.data;
  return (
    <div className="space-y-4">
      <div>
        <h1>Spend vs contract</h1>
        <p className="text-sm text-slate-500">Every invoice from the AP/ERP feed is matched to the contract it bills and checked: unsigned or missing contracts, over-billing, duplicates, billing outside the term, late payment.</p>
      </div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Tile l="Billed to date" v={usd(s.billed)} sub={`${s.invoices} invoices · ${usd(s.billed_90d)} in 90 days`} />
        <Tile l="Off-contract spend" v={usd(s.off_contract)} tone={s.off_contract ? "red" : undefined} sub="no agreement on file" />
        <Tile l="Exceptions" v={s.exceptions} tone={s.serious ? "red" : undefined} sub={`${s.serious} high or critical`} />
        <Tile l="Amount at risk" v={usd(s.at_risk)} tone={s.at_risk ? "amber" : undefined} sub="recoverable or unprotected" />
        <Tile l="Contracts billed" v={cs.data?.filter((c) => c.invoices > 0).length ?? "…"} sub={cs.data ? `of ${cs.data.length} with a value` : undefined} />
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Billing by month" className="lg:col-span-2">
          <div className="h-60" role="img" aria-label="Monthly billing, on-contract and off-contract">
            <ResponsiveContainer><BarChart data={s.monthly} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#cbd5e1" /><XAxis dataKey="month" tick={{ fontSize: 11 }} /><YAxis tickFormatter={(v) => usd(v)} tick={{ fontSize: 11 }} width={56} />
              <Tooltip formatter={(v: number) => usd(v)} /><Legend />
              <Bar dataKey="on_contract" name="On contract" stackId="a" fill="#4f46e5" /><Bar dataKey="off_contract" name="No contract on file" stackId="a" fill="#dc2626" />
            </BarChart></ResponsiveContainer>
          </div>
        </Card>
        <Card title="By vendor">
          <table className="w-full text-sm"><thead><tr><Th>Vendor</Th><Th className="text-right">Billed</Th><Th className="text-right">At risk</Th></tr></thead>
            <tbody>{s.by_vendor.map((v) => <tr key={v.vendor} className="border-t border-slate-100 dark:border-slate-700"><Td><Link className="text-indigo-600 hover:underline dark:text-indigo-400" to={`/vendors/${encodeURIComponent(v.vendor)}`}>{v.vendor.replace(/ (Inc|LLP|Ltd)$/, "")}</Link></Td><Td className="text-right tabular-nums">{usd(v.billed)}</Td><Td className="text-right tabular-nums">{v.at_risk ? <span className="font-medium text-amber-700 dark:text-amber-300">{usd(v.at_risk)}</span> : "—"}</Td></tr>)}</tbody></table>
        </Card>
      </div>

      <Card title={`Spend exceptions (${ex.data?.length ?? "…"})`} right={
        <div className="flex gap-2 text-sm">
          <select className={`${inputCls} w-auto`} aria-label="Severity" value={sev} onChange={(e) => setSev(e.target.value)}><option value="">All severities</option><option>critical</option><option>high</option><option>medium</option><option>low</option></select>
          <select className={`${inputCls} w-auto`} aria-label="Exception type" value={kind} onChange={(e) => setKind(e.target.value)}><option value="">All types</option>{Object.entries(KIND).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
        </div>}>
        <div className="max-h-[26rem] overflow-auto">
          <table className="w-full text-sm" aria-label="Spend exceptions">
            <thead className="sticky top-0 bg-slate-100 dark:bg-slate-900"><tr><Th>Severity</Th><Th>Problem</Th><Th>Contract</Th><Th className="text-right">At risk</Th></tr></thead>
            <tbody>
              {ex.data?.map((e) => (
                <tr key={e.exception_id} className="border-t border-slate-100 align-top dark:border-slate-700">
                  <Td><SeverityChip sev={e.severity} /></Td>
                  <Td><div className="font-medium">{KIND[e.kind] ?? e.kind}</div><div className="text-slate-600 dark:text-slate-300">{e.detail}</div></Td>
                  <Td>{e.contract_id ? <Link className="text-indigo-600 hover:underline dark:text-indigo-400" to={`/contracts/${e.contract_id}`}>{e.contract_title}</Link> : <Pill cls="bg-red-100 text-red-900 dark:bg-red-950 dark:text-red-200">none</Pill>}<div className="text-xs text-slate-500">{e.vendor}</div></Td>
                  <Td className="text-right tabular-nums">{usd(e.amount_at_risk)}</Td>
                </tr>))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card title="Contract utilisation — billed against planned value">
        <p className="mb-2 text-xs text-slate-500">The black marker is where billing should be by today (share of the term elapsed); the bar is what has been billed.</p>
        <div className="max-h-[28rem] overflow-auto">
          <table className="w-full text-sm" aria-label="Contract utilisation">
            <thead className="sticky top-0 bg-slate-100 dark:bg-slate-900"><tr><Th>Contract</Th><Th>Term</Th><Th className="w-64">Billed vs planned</Th><Th className="text-right">Billed</Th><Th className="text-right">Planned</Th></tr></thead>
            <tbody>
              {cs.data?.map((c) => {
                const pct = (c.pct_of_planned ?? 0) * 100;
                return (
                  <tr key={c.contract_id} className="border-t border-slate-100 dark:border-slate-700">
                    <Td><Link className="text-indigo-600 hover:underline dark:text-indigo-400" to={`/contracts/${c.contract_id}`}>{c.title}</Link><div className="text-xs text-slate-500">{c.vendor}{c.exceptions ? <span className="ml-2 font-medium text-amber-700 dark:text-amber-300">{c.exceptions} exception{c.exceptions > 1 ? "s" : ""}</span> : null}</div></Td>
                    <Td className="whitespace-nowrap text-xs">{fmtDate(c.effective_date)} → {fmtDate(c.expiry_date)}</Td>
                    <Td><Meter value={Math.min(pct, 100)} marker={c.elapsed_pct * 100} tone={pct > 100.1 ? "red" : "indigo"} label={`${c.title} billed ${pct.toFixed(0)}% of planned`} /><div className="mt-0.5 text-[11px] tabular-nums text-slate-500">{pct.toFixed(0)}% billed · {(c.elapsed_pct * 100).toFixed(0)}% of term elapsed</div></Td>
                    <Td className="text-right tabular-nums">{usd(c.billed)}</Td><Td className="text-right tabular-nums text-slate-500">{usd(c.planned_value)}</Td>
                  </tr>);
              })}
            </tbody>
          </table>
        </div>
      </Card>

      <Card title="Add an export (CSV)">
        <p className="mb-2 text-sm text-slate-500">Drop invoice, SLA or obligation-status exports in the <code>feeds</code> folder (the pipeline picks them up) or paste / upload one here. Columns: <code>external_id, vendor, contract_title, invoice_no, invoice_date, due_date, paid_date, amount, description</code>.</p>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="File name"><input className={inputCls} aria-label="Feed file name" value={feed.name} onChange={(e) => setFeed({ ...feed, name: e.target.value })} /></Field>
          <div className="flex items-end gap-2">
            <input ref={file} type="file" accept=".csv" className="hidden" aria-label="Choose a CSV" onChange={async (e) => { const f = e.target.files?.[0]; if (f) setFeed({ name: f.name, content: await f.text() }); e.target.value = ""; }} />
            <Btn kind="ghost" onClick={() => file.current?.click()}>⬆ Choose a CSV</Btn>
            <Btn onClick={() => up.mutate()} disabled={!feed.content.trim() || up.isPending}>{up.isPending ? "Loading…" : "Load & check"}</Btn>
          </div>
        </div>
        {feed.content && <p className="mt-2 text-xs text-slate-500">{feed.content.split("\n").length - 1} rows ready.</p>}
        {up.data && <p className="mt-2 text-sm text-emerald-700 dark:text-emerald-400">✓ Loaded: {up.data.new_docs} new, {up.data.updated} updated rows; {up.data.exceptions} exceptions now.</p>}
        {up.error && <p className="mt-2 text-sm text-red-600">{String(up.error)}</p>}
      </Card>
    </div>
  );
}
