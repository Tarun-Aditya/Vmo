import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../../lib";
import { Btn, DOC_TYPES, Field, Toggle, inputCls } from "../../forms";
import { Card, Loading, Sev, SeverityChip, Td, Th } from "../../ui";

type R = {
  key: string; name: string; description: string | null; rule_type: string; kcc_key: string | null; metric_key: string | null; operator: string | null;
  threshold: number | null; threshold_text: string | null; phrase: string | null; severity: Sev; applies_to: string[]; stage: string; suggested_text: string | null;
  enabled: boolean; builtin: boolean; results: { pass?: number; fail?: number; na?: number };
};
type K = { key: string; name: string };
type M = { key: string; name: string; unit: string | null; kind: string };
const TYPES: [string, string][] = [["clause_required", "A clause must be present"], ["clause_forbidden", "A clause must be absent"], ["metric_threshold", "A value must meet a limit"], ["text_forbidden", "Forbidden wording"]];
const BLANK = { key: "", name: "", description: "", rule_type: "metric_threshold", kcc_key: "", metric_key: "", operator: "<=", threshold: "", threshold_text: "", phrase: "", severity: "medium" as Sev, applies_to: [] as string[], stage: "any", suggested_text: "", enabled: true };

export default function Checklist() {
  const qc = useQueryClient();
  const rules = useQuery({ queryKey: ["rules"], queryFn: () => api<R[]>("/api/admin/rules") });
  const kccs = useQuery({ queryKey: ["kcc"], queryFn: () => api<K[]>("/api/admin/kcc") });
  const mets = useQuery({ queryKey: ["metrics"], queryFn: () => api<M[]>("/api/admin/metrics") });
  const [edit, setEdit] = useState<string | "new" | null>(null);
  const [f, setF] = useState(BLANK);
  const body = () => ({ ...f, key: f.key || undefined, kcc_key: f.kcc_key || null, metric_key: f.metric_key || null, operator: f.rule_type === "metric_threshold" ? f.operator : null,
    threshold: f.threshold === "" ? null : Number(f.threshold), threshold_text: f.threshold_text || null, phrase: f.phrase || null, suggested_text: f.suggested_text || null });
  const done = () => { qc.invalidateQueries(); setEdit(null); };
  const save = useMutation({ mutationFn: () => edit === "new" ? api("/api/admin/rules", { method: "POST", body: JSON.stringify(body()) }) : api(`/api/admin/rules/${edit}`, { method: "PUT", body: JSON.stringify(body()) }), onSuccess: done });
  const del = useMutation({ mutationFn: (k: string) => api(`/api/admin/rules/${k}`, { method: "DELETE" }), onSuccess: done });
  const toggle = useMutation({ mutationFn: (r: R) => api(`/api/admin/rules/${r.key}`, { method: "PUT", body: JSON.stringify({ ...r, enabled: !r.enabled }) }), onSuccess: () => qc.invalidateQueries() });
  const open = (r: R | null) => {
    if (!r) { setF(BLANK); setEdit("new"); return; }
    setF({ key: r.key, name: r.name, description: r.description ?? "", rule_type: r.rule_type, kcc_key: r.kcc_key ?? "", metric_key: r.metric_key ?? "", operator: r.operator ?? "<=", threshold: r.threshold === null ? "" : String(r.threshold), threshold_text: r.threshold_text ?? "", phrase: r.phrase ?? "", severity: r.severity, applies_to: r.applies_to, stage: r.stage, suggested_text: r.suggested_text ?? "", enabled: r.enabled });
    setEdit(r.key);
  };
  if (!rules.data) return <Loading q={rules} />;
  const kn = (k: string | null) => kccs.data?.find((x) => x.key === k)?.name ?? k;
  const mn = (k: string | null) => mets.data?.find((x) => x.key === k);
  const cond = (r: R) => r.rule_type === "clause_required" ? `${kn(r.kcc_key)} clause must be present`
    : r.rule_type === "clause_forbidden" ? `${kn(r.kcc_key)} clause must be absent`
    : r.rule_type === "text_forbidden" ? `Must not contain “${r.phrase}”${r.kcc_key ? ` (in ${kn(r.kcc_key)})` : ""}`
    : `${mn(r.metric_key)?.name ?? r.metric_key} ${r.operator} ${r.threshold_text ?? r.threshold ?? ""} ${mn(r.metric_key)?.unit ?? ""}`;
  const metric = mn(f.metric_key || null);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-3xl text-sm text-slate-600 dark:text-slate-300">
          The checklist run on every contract before signing, and again on executed ones. Each rule is a clause that must (or must not) be present, a value that must meet a threshold, or wording that is not allowed. Failed rules appear in <b>Redline</b> and on the contract, with the suggested replacement wording.
        </p>
        <Btn onClick={() => open(null)}>+ Add rule</Btn>
      </div>
      {edit && (
        <Card title={edit === "new" ? "New checklist rule" : `Edit: ${f.name}`}>
          <div className="grid gap-3 md:grid-cols-3">
            <Field label="Rule name" className="md:col-span-2"><input className={inputCls} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="e.g. Price increases capped at 5%" /></Field>
            <Field label="Severity if it fails"><select className={inputCls} value={f.severity} onChange={(e) => setF({ ...f, severity: e.target.value as Sev })}>{["low", "medium", "high", "critical"].map((s) => <option key={s}>{s}</option>)}</select></Field>
            <Field label="Rule type"><select className={inputCls} value={f.rule_type} onChange={(e) => setF({ ...f, rule_type: e.target.value })}>{TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>
            {(f.rule_type === "clause_required" || f.rule_type === "clause_forbidden" || f.rule_type === "text_forbidden") && (
              <Field label={f.rule_type === "text_forbidden" ? "Only look in clause (optional)" : "Clause"}><select className={inputCls} value={f.kcc_key} onChange={(e) => setF({ ...f, kcc_key: e.target.value })}><option value="">{f.rule_type === "text_forbidden" ? "Whole document" : "Choose…"}</option>{kccs.data?.map((k) => <option key={k.key} value={k.key}>{k.name}</option>)}</select></Field>)}
            {f.rule_type === "metric_threshold" && (<>
              <Field label="Value"><select className={inputCls} value={f.metric_key} onChange={(e) => setF({ ...f, metric_key: e.target.value })}><option value="">Choose…</option>{mets.data?.map((m) => <option key={m.key} value={m.key}>{m.name}{m.unit ? ` (${m.unit})` : ""}</option>)}</select></Field>
              <Field label="Must be"><div className="flex gap-2"><select className={`${inputCls} w-20`} value={f.operator} onChange={(e) => setF({ ...f, operator: e.target.value })}>{["<=", ">=", "<", ">", "="].map((o) => <option key={o}>{o}</option>)}</select>
                {metric?.kind === "text" ? <input className={`${inputCls} flex-1`} placeholder="text" value={f.threshold_text} onChange={(e) => setF({ ...f, threshold_text: e.target.value })} /> : <input className={`${inputCls} flex-1`} type="number" step="any" placeholder={metric?.unit ?? "limit"} value={f.threshold} onChange={(e) => setF({ ...f, threshold: e.target.value })} />}</div></Field></>)}
            {f.rule_type === "text_forbidden" && <Field label="Forbidden wording" hint="Text or regular expression, case-insensitive."><input className={`${inputCls} font-mono`} value={f.phrase} onChange={(e) => setF({ ...f, phrase: e.target.value })} placeholder="unlimited|uncapped" /></Field>}
            <Field label="Applies to" className="md:col-span-2"><div className="flex flex-wrap gap-2">{DOC_TYPES.map((t) => <label key={t} className="flex items-center gap-1 text-sm"><input type="checkbox" checked={f.applies_to.includes(t)} onChange={(e) => setF({ ...f, applies_to: e.target.checked ? [...f.applies_to, t] : f.applies_to.filter((x) => x !== t) })} />{t}</label>)}<span className="text-xs text-slate-500">(none ticked = all)</span></div></Field>
            <Field label="Runs"><select className={inputCls} value={f.stage} onChange={(e) => setF({ ...f, stage: e.target.value })}><option value="any">Before and after signing</option><option value="pre_sign">Before signing only</option><option value="post_sign">After signing only</option></select></Field>
            <Field label="Suggested replacement wording (shown when it fails)" className="md:col-span-3"><textarea className={`${inputCls} h-16`} value={f.suggested_text} onChange={(e) => setF({ ...f, suggested_text: e.target.value })} /></Field>
          </div>
          <div className="mt-3 flex items-center gap-2"><Btn onClick={() => save.mutate()} disabled={!f.name || save.isPending}>{save.isPending ? "Saving & re-running…" : "Save & re-run on all documents"}</Btn><Btn kind="ghost" onClick={() => setEdit(null)}>Cancel</Btn>{save.error && <span className="text-sm text-red-600">{String(save.error)}</span>}</div>
        </Card>)}
      <Card>
        <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr><Th>Severity</Th><Th>Rule</Th><Th>Condition</Th><Th>Applies to</Th><Th>Runs</Th><Th className="text-right">Pass</Th><Th className="text-right">Fail</Th><Th>On</Th><Th /></tr></thead><tbody>
          {rules.data.map((r) => (
            <tr key={r.key} className={`border-t border-slate-100 dark:border-slate-700 ${r.enabled ? "" : "opacity-50"}`}>
              <Td><SeverityChip sev={r.severity} /></Td>
              <Td><div className="font-medium">{r.name}</div><div className="font-mono text-[11px] text-slate-500">{r.key}{r.builtin ? "" : " · custom"}</div></Td>
              <Td className="max-w-xs text-xs">{cond(r)}</Td><Td className="max-w-[9rem] text-xs">{r.applies_to.join(", ") || "all"}</Td>
              <Td className="text-xs">{r.stage === "pre_sign" ? "pre-sign" : r.stage === "post_sign" ? "post-sign" : "any time"}</Td>
              <Td className="text-right tabular-nums text-emerald-700 dark:text-emerald-400">{r.results.pass ?? 0}</Td><Td className={`text-right tabular-nums ${r.results.fail ? "font-bold text-red-600" : ""}`}>{r.results.fail ?? 0}</Td>
              <Td><Toggle checked={r.enabled} label={`${r.name} enabled`} onChange={() => toggle.mutate(r)} /></Td>
              <Td className="whitespace-nowrap text-right"><button className="text-indigo-600 hover:underline" onClick={() => open(r)}>Edit</button>{!r.builtin && <button className="ml-3 text-red-600 hover:underline" onClick={() => confirm(`Delete “${r.name}”?`) && del.mutate(r.key)}>Delete</button>}</Td>
            </tr>))}
        </tbody></table></div>
      </Card>
    </div>
  );
}
