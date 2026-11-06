import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib";
import { Btn, DOC_TYPES, Field, Toggle, csv, inputCls } from "../../forms";
import { Card, Loading, Sev, SeverityChip, Td, Th } from "../../ui";

type K = {
  key: string; name: string; description: string | null; category: string | null; keywords: string[]; heading_aliases: string[];
  standard_text: string | null; playbook_position: string | null; fallback_text: string | null; severity_if_missing: Sev; applies_to: string[];
  in_matrix: boolean; enabled: boolean; builtin: boolean; documents: number;
};
type Test = { clauses: number; documents: number; examples: { title: string; heading: string; page: number; text: string; matched_by: string; contract_id: number }[] };
const BLANK = { key: "", name: "", description: "", category: "Key clause", keywords: "", aliases: "", standard_text: "", playbook_position: "", fallback_text: "", severity_if_missing: "medium" as Sev, applies_to: [] as string[], in_matrix: true, enabled: true };

export default function Kcc() {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["kcc"], queryFn: () => api<K[]>("/api/admin/kcc") });
  const [edit, setEdit] = useState<string | "new" | null>(null);
  const [f, setF] = useState(BLANK);
  const [test, setTest] = useState<Test | null>(null);
  const [filter, setFilter] = useState("");
  const body = () => ({ ...f, keywords: csv(f.keywords), heading_aliases: csv(f.aliases), key: f.key || undefined });
  const done = () => { qc.invalidateQueries(); setEdit(null); setTest(null); };
  const save = useMutation({
    mutationFn: () => edit === "new" ? api("/api/admin/kcc", { method: "POST", body: JSON.stringify(body()) }) : api(`/api/admin/kcc/${edit}`, { method: "PUT", body: JSON.stringify(body()) }),
    onSuccess: done,
  });
  const del = useMutation({ mutationFn: (k: string) => api(`/api/admin/kcc/${k}`, { method: "DELETE" }), onSuccess: done });
  const quick = useMutation({
    mutationFn: ({ k, patch }: { k: K; patch: Partial<K> }) => api(`/api/admin/kcc/${k.key}`, { method: "PUT", body: JSON.stringify({ ...k, ...patch }) }),
    onSuccess: () => qc.invalidateQueries(),
  });
  const run = useMutation({ mutationFn: () => api<Test>("/api/admin/kcc/test", { method: "POST", body: JSON.stringify({ keywords: csv(f.keywords), heading_aliases: csv(f.aliases) }) }), onSuccess: setTest });
  const open = (k: K | null) => {
    setTest(null);
    if (!k) { setF(BLANK); setEdit("new"); return; }
    setF({ key: k.key, name: k.name, description: k.description ?? "", category: k.category ?? "", keywords: k.keywords.join(", "), aliases: k.heading_aliases.join(", "), standard_text: k.standard_text ?? "", playbook_position: k.playbook_position ?? "", fallback_text: k.fallback_text ?? "", severity_if_missing: k.severity_if_missing, applies_to: k.applies_to, in_matrix: k.in_matrix, enabled: k.enabled });
    setEdit(k.key);
  };
  if (!list.data) return <Loading q={list} />;
  const rows = list.data.filter((k) => !filter || (k.name + k.key + (k.category ?? "")).toLowerCase().includes(filter.toLowerCase()));
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-3xl text-sm text-slate-600 dark:text-slate-300">
          The library of key contract clauses (KCCs) the platform looks for in every document. A clause is identified by its heading or by keywords in its text. Turn a clause on for the <b>matrix</b> to give it a column on the Key clauses page and in Ask. Add any number of your own.
        </p>
        <div className="flex gap-2"><input className={`${inputCls} w-48`} placeholder="Filter clauses…" aria-label="Filter clauses" value={filter} onChange={(e) => setFilter(e.target.value)} /><Btn onClick={() => open(null)}>+ Add clause</Btn></div>
      </div>

      {edit && (
        <Card title={edit === "new" ? "New key clause" : `Edit: ${f.name}`}>
          <div className="grid gap-3 md:grid-cols-2">
            <Field label="Clause name" hint="Shown as the column heading and in answers."><input className={inputCls} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="e.g. Most Favoured Customer" /></Field>
            <Field label="Severity if missing"><select className={inputCls} value={f.severity_if_missing} onChange={(e) => setF({ ...f, severity_if_missing: e.target.value as Sev })}>{["low", "medium", "high", "critical"].map((s) => <option key={s}>{s}</option>)}</select></Field>
            <Field label="Heading aliases" hint="Comma-separated headings that name this clause."><input className={inputCls} value={f.aliases} onChange={(e) => setF({ ...f, aliases: e.target.value })} placeholder="Most Favoured Customer, MFC, Price Parity" /></Field>
            <Field label="Keywords / phrases" hint="Comma-separated words or regex found in the clause text (used when the heading is unusual)."><input className={inputCls} value={f.keywords} onChange={(e) => setF({ ...f, keywords: e.target.value })} placeholder="most favou?red customer, price parity" /></Field>
            <Field label="Description"><input className={inputCls} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
            <Field label="Expected in (document types)" hint="Where a missing clause counts as a gap."><div className="flex flex-wrap gap-2">{DOC_TYPES.map((t) => <label key={t} className="flex items-center gap-1 text-sm"><input type="checkbox" checked={f.applies_to.includes(t)} onChange={(e) => setF({ ...f, applies_to: e.target.checked ? [...f.applies_to, t] : f.applies_to.filter((x) => x !== t) })} />{t}</label>)}</div></Field>
            <Field label="Standard wording (optional)" className="md:col-span-2"><textarea className={`${inputCls} h-16`} value={f.standard_text} onChange={(e) => setF({ ...f, standard_text: e.target.value })} /></Field>
            <Field label="Playbook position"><input className={inputCls} value={f.playbook_position} onChange={(e) => setF({ ...f, playbook_position: e.target.value })} /></Field>
            <Field label="Fallback wording"><input className={inputCls} value={f.fallback_text} onChange={(e) => setF({ ...f, fallback_text: e.target.value })} /></Field>
            <div className="flex items-center gap-6 md:col-span-2">
              <label className="flex items-center gap-2 text-sm"><Toggle checked={f.in_matrix} label="Show in matrix" onChange={(v) => setF({ ...f, in_matrix: v })} />Show in key-clause matrix</label>
              <label className="flex items-center gap-2 text-sm"><Toggle checked={f.enabled} label="Enabled" onChange={(v) => setF({ ...f, enabled: v })} />Enabled</label>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Btn onClick={() => save.mutate()} disabled={!f.name || save.isPending}>{save.isPending ? "Saving & re-running…" : "Save & re-run on all documents"}</Btn>
            <Btn kind="ghost" onClick={() => run.mutate()} disabled={run.isPending}>🔍 Preview matches</Btn>
            <Btn kind="ghost" onClick={() => { setEdit(null); setTest(null); }}>Cancel</Btn>
            {save.error && <span className="text-sm text-red-600">{String(save.error)}</span>}
          </div>
          {test && (
            <div className="mt-3 rounded border border-slate-200 p-3 text-sm dark:border-slate-700">
              <p className="font-medium">This definition identifies <b>{test.clauses}</b> clause{test.clauses !== 1 ? "s" : ""} in <b>{test.documents}</b> document{test.documents !== 1 ? "s" : ""}.</p>
              <ul className="mt-2 max-h-52 space-y-1 overflow-auto">{test.examples.map((e, i) => <li key={i} className="text-xs"><Link className="font-medium text-indigo-600 hover:underline" to={`/contracts/${e.contract_id}`}>{e.title}</Link> · {e.heading} · p.{e.page} <span className="text-slate-500">({e.matched_by})</span><div className="text-slate-600 dark:text-slate-400">“{e.text}”</div></li>)}</ul>
            </div>
          )}
        </Card>
      )}

      <Card>
        <div className="overflow-x-auto"><table className="w-full text-sm">
          <thead><tr><Th>Clause</Th><Th>Type</Th><Th>Identified by</Th><Th className="text-right">Found in</Th><Th>If missing</Th><Th>Expected in</Th><Th>Matrix</Th><Th>On</Th><Th /></tr></thead>
          <tbody>
            {rows.map((k) => (
              <tr key={k.key} className={`border-t border-slate-100 dark:border-slate-700 ${k.enabled ? "" : "opacity-50"}`}>
                <Td><div className="font-medium">{k.name}</div><div className="font-mono text-[11px] text-slate-500">{k.key}{k.builtin ? "" : " · custom"}</div></Td>
                <Td className="text-xs">{k.category}</Td>
                <Td className="max-w-xs text-xs text-slate-600 dark:text-slate-400"><div>{k.heading_aliases.slice(0, 3).join(" · ")}</div><div className="truncate" title={k.keywords.join(", ")}>{k.keywords.length ? `“${k.keywords.slice(0, 2).join("”, “")}”${k.keywords.length > 2 ? " …" : ""}` : ""}</div></Td>
                <Td className="text-right tabular-nums">{k.documents}</Td>
                <Td><SeverityChip sev={k.severity_if_missing} /></Td>
                <Td className="max-w-[10rem] text-xs">{k.applies_to.join(", ") || "—"}</Td>
                <Td><Toggle checked={k.in_matrix} label={`${k.name} in matrix`} onChange={(v) => quick.mutate({ k, patch: { in_matrix: v } })} /></Td>
                <Td><Toggle checked={k.enabled} label={`${k.name} enabled`} onChange={(v) => quick.mutate({ k, patch: { enabled: v } })} /></Td>
                <Td className="whitespace-nowrap text-right"><button className="text-indigo-600 hover:underline" onClick={() => open(k)}>Edit</button>{!k.builtin && <button className="ml-3 text-red-600 hover:underline" onClick={() => confirm(`Delete “${k.name}”?`) && del.mutate(k.key)}>Delete</button>}</Td>
              </tr>))}
          </tbody></table></div>
      </Card>
    </div>
  );
}
