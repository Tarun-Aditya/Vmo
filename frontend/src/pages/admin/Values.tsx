import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib";
import { Btn, Field, Toggle, inputCls } from "../../forms";
import { Card, Loading, Td, Th } from "../../ui";

type M = { key: string; name: string; description: string | null; kcc_key: string | null; pattern: string; kind: string; unit: string | null; scale: number; enabled: boolean; builtin: boolean; documents: number; better: string | null; sla: boolean };
type K = { key: string; name: string };
type Test = { matches: number; examples: { title: string; value: string | number; page: number; excerpt: string }[] };
const BLANK = { key: "", name: "", description: "", kcc_key: "", pattern: "", kind: "number", unit: "", scale: 1, enabled: true, better: "", sla: false };

export default function Values() {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["metrics"], queryFn: () => api<M[]>("/api/admin/metrics") });
  const kccs = useQuery({ queryKey: ["kcc"], queryFn: () => api<K[]>("/api/admin/kcc") });
  const [edit, setEdit] = useState<string | "new" | null>(null);
  const [f, setF] = useState(BLANK);
  const [test, setTest] = useState<Test | null>(null);
  const body = () => ({ ...f, key: f.key || undefined, kcc_key: f.kcc_key || null, scale: Number(f.scale) || 1, better: f.better || null });
  const done = () => { qc.invalidateQueries(); setEdit(null); setTest(null); };
  const save = useMutation({ mutationFn: () => edit === "new" ? api("/api/admin/metrics", { method: "POST", body: JSON.stringify(body()) }) : api(`/api/admin/metrics/${edit}`, { method: "PUT", body: JSON.stringify(body()) }), onSuccess: done });
  const del = useMutation({ mutationFn: (k: string) => api(`/api/admin/metrics/${k}`, { method: "DELETE" }), onSuccess: done });
  const quick = useMutation({ mutationFn: (m: M) => api(`/api/admin/metrics/${m.key}`, { method: "PUT", body: JSON.stringify({ ...m, enabled: !m.enabled }) }), onSuccess: () => qc.invalidateQueries() });
  const run = useMutation({ mutationFn: () => api<Test>("/api/admin/metrics/test", { method: "POST", body: JSON.stringify(body()) }), onSuccess: setTest });
  const open = (m: M | null) => { setTest(null); if (!m) { setF(BLANK); setEdit("new"); return; } setF({ key: m.key, name: m.name, description: m.description ?? "", kcc_key: m.kcc_key ?? "", pattern: m.pattern, kind: m.kind, unit: m.unit ?? "", scale: m.scale, enabled: m.enabled, better: m.better ?? "", sla: m.sla }); setEdit(m.key); };
  if (!list.data) return <Loading q={list} />;
  const kname = (k: string | null) => kccs.data?.find((x) => x.key === k)?.name ?? (k || "any clause");
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-3xl text-sm text-slate-600 dark:text-slate-300">
          Values and limits are the numbers inside a clause: payment days, liability cap multiple, insurance cover, notice periods, uptime. Each one is extracted from its clause with a pattern, stored per document and shown on the contract. Checklist rules compare these values to your thresholds.
        </p>
        <Btn onClick={() => open(null)}>+ Add value</Btn>
      </div>
      {edit && (
        <Card title={edit === "new" ? "New value to extract" : `Edit: ${f.name}`}>
          <div className="grid gap-3 md:grid-cols-3">
            <Field label="Name"><input className={inputCls} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="e.g. Price increase cap" /></Field>
            <Field label="Found in clause"><select className={inputCls} value={f.kcc_key} onChange={(e) => setF({ ...f, kcc_key: e.target.value })}><option value="">Any clause</option>{kccs.data?.map((k) => <option key={k.key} value={k.key}>{k.name}</option>)}</select></Field>
            <Field label="Type"><select className={inputCls} value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>{["number", "money", "text"].map((k) => <option key={k}>{k}</option>)}</select></Field>
            <Field label="Pattern" hint="A regular expression with ONE capture group around the value." className="md:col-span-2"><input className={`${inputCls} font-mono`} value={f.pattern} onChange={(e) => setF({ ...f, pattern: e.target.value })} placeholder="increase of (\d+)% per year" /></Field>
            <Field label="Unit"><input className={inputCls} value={f.unit} onChange={(e) => setF({ ...f, unit: e.target.value })} placeholder="days, %, USD, hours" /></Field>
            <Field label="Which way is good?" hint="Used for benchmarks and SLA breach direction."><select className={inputCls} aria-label="Which way is good" value={f.better} onChange={(e) => setF({ ...f, better: e.target.value })}><option value="">Not applicable</option><option value="higher">Higher is better (e.g. availability)</option><option value="lower">Lower is better (e.g. response time)</option></select></Field>
            <Field label="Measured monthly (SLA)" hint="Actuals arrive in the monitoring feed (sla*.csv) and are tracked against the contract's target."><label className="flex items-center gap-2 pt-1"><input type="checkbox" checked={f.sla} onChange={(e) => setF({ ...f, sla: e.target.checked })} />Track as an SLA</label></Field>
            <Field label="Description" className="md:col-span-3"><input className={inputCls} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Btn onClick={() => save.mutate()} disabled={!f.name || !f.pattern || save.isPending}>{save.isPending ? "Saving & re-running…" : "Save & re-run on all documents"}</Btn>
            <Btn kind="ghost" onClick={() => run.mutate()} disabled={!f.pattern || run.isPending}>🔍 Preview extraction</Btn>
            <Btn kind="ghost" onClick={() => { setEdit(null); setTest(null); }}>Cancel</Btn>
            {(save.error || run.error) && <span className="text-sm text-red-600">{String(save.error || run.error)}</span>}
          </div>
          {test && (
            <div className="mt-3 rounded border border-slate-200 p-3 text-sm dark:border-slate-700">
              <p className="font-medium">Extracts a value from <b>{test.matches}</b> clause{test.matches !== 1 ? "s" : ""}.</p>
              <table className="mt-2 w-full text-xs"><tbody>{test.examples.map((e, i) => <tr key={i} className="border-t border-slate-100 dark:border-slate-700"><Td className="w-1/2">{e.title}</Td><Td className="font-semibold tabular-nums">{String(e.value)}</Td><Td className="text-slate-500">p.{e.page}</Td></tr>)}</tbody></table>
            </div>)}
        </Card>)}
      <Card>
        <table className="w-full text-sm"><thead><tr><Th>Value</Th><Th>From clause</Th><Th>Pattern</Th><Th>Type</Th><Th className="text-right">Extracted from</Th><Th>On</Th><Th /></tr></thead><tbody>
          {list.data.map((m) => (
            <tr key={m.key} className={`border-t border-slate-100 dark:border-slate-700 ${m.enabled ? "" : "opacity-50"}`}>
              <Td><div className="font-medium">{m.name}</div><div className="text-[11px] text-slate-500">{m.description}</div></Td>
              <Td>{kname(m.kcc_key)}</Td><Td className="font-mono text-xs text-slate-600 dark:text-slate-400">{m.pattern}</Td>
              <Td className="text-xs">{m.kind}{m.unit ? ` · ${m.unit}` : ""}</Td><Td className="text-right tabular-nums"><Link to="/contracts" className="hover:underline">{m.documents} docs</Link></Td>
              <Td><Toggle checked={m.enabled} label={`${m.name} enabled`} onChange={() => quick.mutate(m)} /></Td>
              <Td className="whitespace-nowrap text-right"><button className="text-indigo-600 hover:underline" onClick={() => open(m)}>Edit</button>{!m.builtin && <button className="ml-3 text-red-600 hover:underline" onClick={() => confirm(`Delete “${m.name}” and its rules?`) && del.mutate(m.key)}>Delete</button>}</Td>
            </tr>))}
        </tbody></table>
      </Card>
    </div>
  );
}
