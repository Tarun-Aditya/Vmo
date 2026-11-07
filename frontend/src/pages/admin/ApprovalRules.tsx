import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Btn, Field, inputCls } from "../../forms";
import { api } from "../../lib";
import { Card, Loading } from "../../ui";

type Step = { label: string; approvers: string[] };
type Rule = { id?: number; name: string; doc_types: string[]; min_value: number | null; min_severity: string | null; steps: Step[]; enabled: boolean; sort_order: number; remind_after_days: number };
const blank = (): Rule => ({ name: "", doc_types: [], min_value: null, min_severity: null, steps: [{ label: "Legal", approvers: [] }], enabled: true, sort_order: 100, remind_after_days: 3 });
const TYPES = ["MSA", "SOW", "Work Order", "NDA", "SaaS", "DPA"];

export default function ApprovalRules() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["approval-rules"], queryFn: () => api<Rule[]>("/api/admin/approval-rules") });
  const [edit, setEdit] = useState<Rule | null>(null);
  const done = () => { setEdit(null); qc.invalidateQueries({ queryKey: ["approval-rules"] }); };
  const save = useMutation({ mutationFn: (r: Rule) => api(r.id ? `/api/admin/approval-rules/${r.id}` : "/api/admin/approval-rules", { method: r.id ? "PUT" : "POST", body: JSON.stringify(r) }), onSuccess: done });
  const del = useMutation({ mutationFn: (id: number) => api(`/api/admin/approval-rules/${id}`, { method: "DELETE" }), onSuccess: done });
  if (!q.data) return <Loading q={q} />;
  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4"><p className="max-w-3xl text-sm text-slate-500">Rules pick who must approve a draft, in order. The first enabled rule (lowest order) whose document type, minimum value and worst deviation severity match is used. Approvers are notified, stalled steps raise reminders, and the last approval approves the draft.</p><Btn onClick={() => setEdit(blank())}>+ Add rule</Btn></div>
      {edit && (
        <Card title={edit.id ? "Edit rule" : "New rule"}>
          <div className="grid gap-3 md:grid-cols-3">
            <Field label="Name"><input className={inputCls} aria-label="Rule name" value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></Field>
            <Field label="Document types (none = all)"><div className="flex flex-wrap gap-2 pt-1 text-sm">{TYPES.map((t) => <label key={t} className="flex items-center gap-1"><input type="checkbox" checked={edit.doc_types.includes(t)} onChange={(e) => setEdit({ ...edit, doc_types: e.target.checked ? [...edit.doc_types, t] : edit.doc_types.filter((x) => x !== t) })} />{t}</label>)}</div></Field>
            <Field label="Minimum value (USD)"><input className={inputCls} type="number" aria-label="Minimum value" value={edit.min_value ?? ""} onChange={(e) => setEdit({ ...edit, min_value: e.target.value ? Number(e.target.value) : null })} /></Field>
            <Field label="Worst deviation at least"><select className={inputCls} aria-label="Minimum severity" value={edit.min_severity ?? ""} onChange={(e) => setEdit({ ...edit, min_severity: e.target.value || null })}><option value="">any</option>{["low", "medium", "high", "critical"].map((s) => <option key={s}>{s}</option>)}</select></Field>
            <Field label="Order"><input className={inputCls} type="number" aria-label="Rule order" value={edit.sort_order} onChange={(e) => setEdit({ ...edit, sort_order: Number(e.target.value) })} /></Field>
            <Field label="Remind after (days)"><input className={inputCls} type="number" aria-label="Remind after days" value={edit.remind_after_days} onChange={(e) => setEdit({ ...edit, remind_after_days: Number(e.target.value) })} /></Field>
          </div>
          <div className="mt-3 space-y-2">
            {edit.steps.map((s, i) => (
              <div key={i} className="flex flex-wrap items-center gap-2 text-sm"><b>Step {i + 1}</b>
                <input className={`${inputCls} w-40`} aria-label={`Step ${i + 1} label`} placeholder="Label (Legal)" value={s.label} onChange={(e) => setEdit({ ...edit, steps: edit.steps.map((x, j) => j === i ? { ...x, label: e.target.value } : x) })} />
                <input className={`${inputCls} flex-1`} aria-label={`Step ${i + 1} approvers`} placeholder="Approver e-mails, comma separated" value={s.approvers.join(", ")} onChange={(e) => setEdit({ ...edit, steps: edit.steps.map((x, j) => j === i ? { ...x, approvers: e.target.value.split(",").map((a) => a.trim()).filter(Boolean) } : x) })} />
                {edit.steps.length > 1 && <button className="text-xs text-red-600 hover:underline" onClick={() => setEdit({ ...edit, steps: edit.steps.filter((_, j) => j !== i) })}>Remove</button>}</div>))}
            <button className="text-xs text-indigo-600 hover:underline dark:text-indigo-400" onClick={() => setEdit({ ...edit, steps: [...edit.steps, { label: "", approvers: [] }] })}>+ Add step</button>
          </div>
          <div className="mt-3 flex items-center gap-2"><Btn onClick={() => save.mutate(edit)} disabled={!edit.name.trim() || save.isPending}>Save rule</Btn><Btn kind="ghost" onClick={() => setEdit(null)}>Cancel</Btn>{save.error && <span className="text-sm text-red-600">{String(save.error).replace("Error: ", "")}</span>}</div>
        </Card>)}
      {q.data.length === 0 && !edit && <Card><p className="text-sm text-slate-500">No approval rules yet.</p></Card>}
      {q.data.map((r) => (
        <Card key={r.id} title={`${r.sort_order}. ${r.name}`} right={<div className="flex gap-3 text-xs"><button className="text-indigo-600 hover:underline" onClick={() => setEdit(r)}>Edit</button><button className="text-red-600 hover:underline" onClick={() => window.confirm(`Delete rule “${r.name}”?`) && del.mutate(r.id!)}>Delete</button></div>}>
          <p className="text-sm text-slate-600 dark:text-slate-300">{r.doc_types.length ? r.doc_types.join(", ") : "All types"} · {r.min_value ? `value ≥ $${r.min_value.toLocaleString()}` : "any value"} · {r.min_severity ? `worst deviation ≥ ${r.min_severity}` : "any deviation"}{!r.enabled && " · disabled"}</p>
          <ol className="mt-1 text-sm">{r.steps.map((s, i) => <li key={i}>{i + 1}. <b>{s.label}</b>: {s.approvers.join(", ")}</li>)}</ol>
        </Card>))}
    </div>
  );
}
