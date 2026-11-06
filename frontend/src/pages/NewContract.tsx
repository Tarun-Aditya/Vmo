import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib";
import { Btn, Field, inputCls } from "../forms";
import { Card, Loading, Sev, SeverityChip } from "../ui";

type Form = { template: string; name: string; type: string; parent_type: string | null; clauses: number; fields: string[] };
type Forms = { forms: Form[]; vendors: string[]; parents: { id: number; title: string; type: string; vendor: string }[] };
type Check = { rule_key: string; name: string; status: "pass" | "fail" | "na"; severity: Sev; actual: string | null; expected: string | null; suggested_text: string | null };
type Analysis = { type: string; clauses: number; checks: Check[]; summary: { pass: number; fail: number; na: number }; deviations: number };
type Preview = { title: string; md: string; analysis: Analysis };
type Created = { status: string; contract_id: number | null; title: string; failed_checks: { name: string; severity: Sev; actual: string | null; expected: string | null }[]; message?: string };

type Meta = { label: string; type: "text" | "number" | "date" | "bool" | "area" | "vendor" | "parent"; hint?: string };
const META: Record<string, Meta> = {
  vendor: { label: "Vendor (supplier)", type: "vendor", hint: "Pick an existing vendor or type a new one." },
  title: { label: "Title (optional)", type: "text", hint: "Left blank, a title is generated." },
  effective_date: { label: "Effective date", type: "date" }, term_months: { label: "Term (months)", type: "number" },
  owner: { label: "Contract owner", type: "text" }, category: { label: "Category", type: "text" },
  parent_id: { label: "Parent agreement", type: "parent", hint: "The MSA / SOW / SaaS agreement this document sits under." },
  scope: { label: "Scope of work", type: "area" }, annual_fees: { label: "Annual fees (USD)", type: "number" }, fixed_fee: { label: "Fixed fee (USD)", type: "number" },
  payment_terms_days: { label: "Payment terms (days)", type: "number" }, auto_renew: { label: "Auto-renews", type: "bool" }, notice_days: { label: "Non-renewal notice (days)", type: "number" },
  governing_law: { label: "Governing law", type: "text" }, liability_cap: { label: "Liability cap (× annual fees)", type: "number" }, tfc_notice_days: { label: "Termination for convenience notice (days)", type: "number" },
  warranty_days: { label: "Warranty (days)", type: "number" }, insurance_cover_usd: { label: "Insurance cover per claim (USD)", type: "number" },
  confidentiality_years: { label: "Confidentiality survives (years)", type: "number" }, sla: { label: "Availability SLA (%)", type: "number" },
  personal_data: { label: "Processes personal data", type: "bool" }, subjects: { label: "Whose personal data", type: "text" },
};
const DEFAULTS: Record<string, unknown> = { term_months: 12, payment_terms_days: 45, notice_days: 60, governing_law: "New York", liability_cap: 1, tfc_notice_days: 30, warranty_days: 90, insurance_cover_usd: 5000000, confidentiality_years: 3, sla: 99.9, owner: "", category: "", auto_renew: false, personal_data: false };

function Checks({ a }: { a: Analysis }) {
  return (
    <div className="space-y-2">
      <p className="text-sm"><b className="text-emerald-700 dark:text-emerald-400">{a.summary.pass} pass</b> · <b className={a.summary.fail ? "text-red-600" : ""}>{a.summary.fail} fail</b> · {a.summary.na} n/a · {a.deviations} change{a.deviations !== 1 ? "s" : ""} from the standard template</p>
      <ul className="space-y-1">
        {a.checks.filter((c) => c.status !== "na").map((c) => (
          <li key={c.rule_key} className="rounded border border-slate-200 px-2 py-1 text-sm dark:border-slate-700">
            <div className="flex items-center gap-2"><b className={c.status === "pass" ? "text-emerald-600" : "text-red-600"}>{c.status === "pass" ? "✓" : "✗"}</b><span className="flex-1">{c.name}</span>
              <span className="text-xs text-slate-500">{c.actual}{c.expected ? ` · limit ${c.expected}` : ""}</span>{c.status === "fail" && <SeverityChip sev={c.severity} />}</div>
            {c.status === "fail" && c.suggested_text && <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">Suggested: {c.suggested_text}</p>}
          </li>))}
      </ul>
    </div>
  );
}

export default function NewContract() {
  const forms = useQuery({ queryKey: ["gen-forms"], queryFn: () => api<Forms>("/api/generator/forms") });
  const [tk, setTk] = useState<string | null>(null);
  const [p, setP] = useState<Record<string, unknown>>({ ...DEFAULTS, effective_date: new Date().toISOString().slice(0, 10) });
  const [md, setMd] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [title, setTitle] = useState("");
  const preview = useMutation({ mutationFn: () => api<Preview>("/api/generator/preview", { method: "POST", body: JSON.stringify({ template: tk, params: p }) }), onSuccess: (d) => { setMd(d.md); setAnalysis(d.analysis); setTitle(d.title); } });
  const recheck = useMutation({ mutationFn: () => api<Analysis>("/api/generator/analyze", { method: "POST", body: JSON.stringify({ template: tk, md }) }), onSuccess: setAnalysis });
  const create = useMutation({ mutationFn: () => api<Created>("/api/generator/create", { method: "POST", body: JSON.stringify({ template: tk, params: p, md }) }) });
  if (!forms.data) return <Loading q={forms} />;
  const form = forms.data.forms.find((f) => f.template === tk);
  const set = (k: string, v: unknown) => setP((x) => ({ ...x, [k]: v }));
  const parents = form ? forms.data.parents.filter((x) => x.type === form.parent_type && (!p.vendor || x.vendor === p.vendor)) : [];
  const valid = form && p.vendor && (!form.fields.includes("parent_id") || form.parent_type === null || p.parent_id || form.template === "NDA");
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">New contract from a template</h1>
        <p className="text-sm text-slate-500">Start from one of the standard templates, set the key terms, edit the text, and check it against the pre-signature checklist before it goes to the vendor. Saving it drops the document into the pipeline folder, so it is extracted and appears everywhere.</p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" role="radiogroup" aria-label="Template">
        {forms.data.forms.map((f) => (
          <button key={f.template} role="radio" aria-checked={tk === f.template} onClick={() => { setTk(f.template); setMd(null); setAnalysis(null); create.reset(); }}
            className={`rounded-lg border p-3 text-left ${tk === f.template ? "border-indigo-600 bg-indigo-50 ring-1 ring-indigo-600 dark:bg-slate-700" : "border-slate-200 bg-white hover:border-indigo-300 dark:border-slate-700 dark:bg-slate-800"}`}>
            <div className="font-medium">{f.name}</div><div className="text-xs text-slate-500">{f.clauses} standard clauses{f.parent_type ? ` · sits under a ${f.parent_type}` : ""}</div>
          </button>))}
      </div>

      {form && !md && (
        <Card title={`${form.name} — key terms`}>
          <div className="grid gap-3 md:grid-cols-3">
            {form.fields.map((fk) => {
              const m = META[fk];
              if (!m) return null;
              const v = p[fk];
              return (
                <Field key={fk} label={m.label} hint={m.hint} className={m.type === "area" ? "md:col-span-3" : ""}>
                  {m.type === "bool" ? <label className="flex items-center gap-2 pt-1"><input type="checkbox" checked={!!v} onChange={(e) => set(fk, e.target.checked)} />Yes</label>
                    : m.type === "area" ? <textarea className={`${inputCls} h-16`} value={String(v ?? "")} onChange={(e) => set(fk, e.target.value)} />
                    : m.type === "vendor" ? <><input className={inputCls} list="vendors" value={String(v ?? "")} onChange={(e) => set(fk, e.target.value)} /><datalist id="vendors">{forms.data.vendors.map((x) => <option key={x} value={x} />)}</datalist></>
                    : m.type === "parent" ? <select className={inputCls} value={String(v ?? "")} onChange={(e) => set(fk, e.target.value ? Number(e.target.value) : "")}><option value="">{form.template === "NDA" ? "None (standalone)" : "Choose…"}</option>{parents.map((x) => <option key={x.id} value={x.id}>{x.title}</option>)}</select>
                    : <input className={inputCls} type={m.type} step="any" value={String(v ?? "")} onChange={(e) => set(fk, m.type === "number" ? (e.target.value === "" ? "" : Number(e.target.value)) : e.target.value)} />}
                </Field>);
            })}
          </div>
          <div className="mt-4 flex items-center gap-3">
            <Btn onClick={() => preview.mutate()} disabled={!valid || preview.isPending}>{preview.isPending ? "Building…" : "Preview & check"}</Btn>
            {!valid && <span className="text-xs text-slate-500">Enter the vendor{form.parent_type && form.template !== "NDA" ? " and the parent agreement" : ""} first.</span>}
            {preview.error && <span className="text-sm text-red-600">{String(preview.error)}</span>}
          </div>
        </Card>)}

      {form && md !== null && !create.data && (
        <div className="grid gap-4 lg:grid-cols-5">
          <Card title={`Draft: ${title}`} className="lg:col-span-3" right={<button className="text-xs text-indigo-600 hover:underline" onClick={() => { setMd(null); setAnalysis(null); }}>← Change terms</button>}>
            <p className="mb-2 text-xs text-slate-500">Edit the text freely, then re-check. Clauses are identified by their headings.</p>
            <textarea className={`${inputCls} h-[30rem] w-full font-mono text-xs leading-relaxed`} aria-label="Contract text" value={md} onChange={(e) => setMd(e.target.value)} />
            <div className="mt-3 flex items-center gap-2">
              <Btn kind="ghost" onClick={() => recheck.mutate()} disabled={recheck.isPending}>{recheck.isPending ? "Checking…" : "Re-check my edits"}</Btn>
              <Btn onClick={() => create.mutate()} disabled={create.isPending}>{create.isPending ? "Creating…" : "Create draft & add to repository"}</Btn>
              {create.error && <span className="text-sm text-red-600">{String(create.error)}</span>}
            </div>
          </Card>
          <Card title="Pre-signature checklist" className="lg:col-span-2">{analysis ? <Checks a={analysis} /> : null}</Card>
        </div>)}

      {create.data && (
        <Card title="Draft created">
          {create.data.status === "busy" ? <p className="text-sm text-amber-700">The pipeline is busy; try again in a moment.</p> : (<>
            <p className="text-sm"><b>{create.data.title}</b> was added to the folder, extracted and indexed. It now appears in the repository, key clauses, vendors and Ask.</p>
            <div className="mt-2 flex gap-3 text-sm">{create.data.contract_id && <><Link className="font-medium text-indigo-600 hover:underline" to={`/contracts/${create.data.contract_id}`}>Open the contract</Link><Link className="font-medium text-indigo-600 hover:underline" to={`/redline/${create.data.contract_id}`}>Review in Redline</Link><Link className="font-medium text-indigo-600 hover:underline" to={`/ask?doc=${create.data.contract_id}`}>Ask about it</Link></>}</div>
            <p className="mt-3 text-sm font-medium">{create.data.failed_checks.length === 0 ? <span className="text-emerald-700 dark:text-emerald-400">Every applicable checklist rule passes.</span> : `${create.data.failed_checks.length} checklist rule(s) still fail:`}</p>
            <ul className="mt-1 space-y-1 text-sm">{create.data.failed_checks.map((c) => <li key={c.name} className="flex items-center gap-2"><SeverityChip sev={c.severity} /> {c.name} <span className="text-xs text-slate-500">{c.actual}</span></li>)}</ul></>)}
        </Card>)}
    </div>
  );
}
