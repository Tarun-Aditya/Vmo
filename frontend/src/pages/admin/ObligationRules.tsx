import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Btn, Field, Toggle, inputCls } from "../../forms";
import { api } from "../../lib";
import { Card, Loading } from "../../ui";

type R = { key: string; name: string; metric_key: string | null; kind: string; party: string; title_template: string; frequency: string; unit: string | null; annual: boolean; enabled: boolean; builtin: boolean; obligations: number };
type Res = { rules: R[]; metrics: { key: string; name: string; unit: string | null }[] };
const BLANK = { key: "", name: "", metric_key: "", kind: "", party: "Supplier", title_template: "", frequency: "event", unit: "", annual: false, enabled: true };

export default function ObligationRules() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["obl-rules"], queryFn: () => api<Res>("/api/admin/obligation-rules") });
  const [f, setF] = useState<typeof BLANK | null>(null);
  const save = useMutation({
    mutationFn: (b: typeof BLANK) => api(b.key ? `/api/admin/obligation-rules/${b.key}` : "/api/admin/obligation-rules", { method: b.key ? "PUT" : "POST", body: JSON.stringify({ ...b, key: b.key || undefined, metric_key: b.metric_key || null }) }),
    onSuccess: () => { setF(null); qc.invalidateQueries(); },
  });
  const toggle = useMutation({ mutationFn: (r: R) => api(`/api/admin/obligation-rules/${r.key}`, { method: "PUT", body: JSON.stringify({ ...r, enabled: !r.enabled }) }), onSuccess: () => qc.invalidateQueries() });
  const del = useMutation({ mutationFn: (k: string) => api(`/api/admin/obligation-rules/${k}`, { method: "DELETE" }), onSuccess: () => qc.invalidateQueries() });
  if (!q.data) return <Loading q={q} />;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-3xl text-sm text-slate-500">An obligation rule turns a value found in a contract (a metric from Values &amp; limits) into a tracked duty: who owes it, how it is worded, how often. Dated milestones and renewal-notice deadlines are always read from the text. Claude adds further duties (reporting, certificates…) when it is available. Saving re-derives every contract's obligations.</p>
        <Btn onClick={() => setF({ ...BLANK })}>+ Add rule</Btn>
      </div>
      {f && (
        <Card title={f.key ? `Edit ${f.name}` : "New obligation rule"}>
          <div className="grid gap-3 md:grid-cols-3">
            <Field label="Name"><input className={inputCls} aria-label="Rule name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
            <Field label="Value it reads (metric)"><select className={inputCls} aria-label="Metric" value={f.metric_key} onChange={(e) => setF({ ...f, metric_key: e.target.value, unit: q.data!.metrics.find((m) => m.key === e.target.value)?.unit ?? f.unit })}><option value="">Choose…</option>{q.data.metrics.map((m) => <option key={m.key} value={m.key}>{m.name}</option>)}</select></Field>
            <Field label="Kind" hint="A short label, e.g. warranty, reporting"><input className={inputCls} aria-label="Kind" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })} /></Field>
            <Field label="Who owes it"><select className={inputCls} aria-label="Party" value={f.party} onChange={(e) => setF({ ...f, party: e.target.value })}><option>Supplier</option><option>Customer</option><option>Both</option></select></Field>
            <Field label="How often"><select className={inputCls} aria-label="Frequency" value={f.frequency} onChange={(e) => setF({ ...f, frequency: e.target.value })}>{["event", "once", "monthly", "quarterly", "annual"].map((x) => <option key={x}>{x}</option>)}</select></Field>
            <Field label="Title" hint="Use {v} for the value, e.g. Pay within {v:g} days" className="md:col-span-3"><input className={inputCls} aria-label="Title template" value={f.title_template} onChange={(e) => setF({ ...f, title_template: e.target.value })} /></Field>
          </div>
          <div className="mt-3 flex items-center gap-3"><Btn onClick={() => save.mutate(f)} disabled={!f.name || !f.kind || !f.title_template || save.isPending}>{save.isPending ? "Saving & re-running…" : "Save & re-derive"}</Btn><Btn kind="ghost" onClick={() => setF(null)}>Cancel</Btn>{save.error && <span className="text-sm text-red-600">{String(save.error)}</span>}</div>
        </Card>)}
      <Card>
        <table className="w-full text-sm" aria-label="Obligation rules">
          <thead><tr className="text-left text-xs uppercase text-slate-500"><th className="py-1">Rule</th><th>Reads</th><th>Wording</th><th>Owed by</th><th className="text-right">Obligations</th><th>On</th><th /></tr></thead>
          <tbody>
            {q.data.rules.map((r) => (
              <tr key={r.key} className={`border-t border-slate-100 dark:border-slate-700 ${r.enabled ? "" : "opacity-50"}`}>
                <td className="py-2 font-medium">{r.name}<div className="text-xs font-normal text-slate-500">{r.kind} · {r.frequency}</div></td>
                <td>{q.data!.metrics.find((m) => m.key === r.metric_key)?.name ?? "—"}</td><td className="text-xs text-slate-600 dark:text-slate-300">{r.title_template}</td><td>{r.party}</td>
                <td className="text-right tabular-nums">{r.obligations}</td>
                <td><Toggle checked={r.enabled} label={`${r.name} enabled`} onChange={() => toggle.mutate(r)} /></td>
                <td className="whitespace-nowrap text-right text-xs"><button className="text-indigo-600 hover:underline" onClick={() => setF({ ...BLANK, ...r, metric_key: r.metric_key ?? "", unit: r.unit ?? "" })}>Edit</button>{!r.builtin && <button className="ml-2 text-red-600 hover:underline" onClick={() => window.confirm(`Delete “${r.name}”?`) && del.mutate(r.key)}>Delete</button>}</td>
              </tr>))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
