import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib";
import { Card, Loading, Sev, SeverityChip } from "../ui";

type Lib = { key: string; heading: string; preview: string; in_templates: string[] };
const KEYS: [string, string][] = [["MSA", "MSA"], ["SOW", "SOW"], ["WO", "Work Order"], ["NDA", "NDA"], ["SaaS", "SaaS"], ["DPA", "DPA"]];
const GEN_KEY: Record<string, string> = { MSA: "MSA", SOW: "SOW", "Work Order": "WO", NDA: "NDA", SaaS: "SaaS", DPA: "DPA" };
type T = { id: number; name: string; type: string; clause_count: number; contracts: number; deviating_contracts: number };
type Clause = { id: number; clause_type: string; heading: string; standard_text: string; playbook_position: string; fallback_text: string | null; variable: boolean; deviation_count: number };
type Cell = { severity: Sev; deviation_summary: string } | null;
type Detail = { template: T; clauses: Clause[]; matrix: { contract: { id: number; title: string; vendor: string }; cells: Record<string, Cell> }[] };

const CELL: Record<Sev, string> = { critical: "bg-red-600 text-white", high: "bg-orange-500 text-white", medium: "bg-amber-300 text-amber-950", low: "bg-sky-200 text-sky-950" };
const GLYPH: Record<Sev, string> = { critical: "▲▲", high: "▲", medium: "●", low: "○" };

export default function Templates() {
  const list = useQuery({ queryKey: ["templates"], queryFn: () => api<T[]>("/api/templates") });
  const lib = useQuery({ queryKey: ["gen-library"], queryFn: () => api<Lib[]>("/api/generator/library") });
  const [sel, setSel] = useState<number | null>(null);
  const id = sel ?? list.data?.[0]?.id;
  const d = useQuery({ queryKey: ["template", id], enabled: !!id, queryFn: () => api<Detail>(`/api/templates/${id}`) });
  const [focus, setFocus] = useState<{ title: string; heading: string; cell: NonNullable<Cell> } | null>(null);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h1>Template library</h1><p className="mt-1 text-sm text-slate-500">{list.data ? `${list.data.length} standard templates` : "Standard templates"} · clause by clause, and where executed contracts drift from them</p></div>
        <Link to="/redline" className="inline-flex min-h-[44px] items-center rounded-lg bg-indigo-600 px-4 text-sm font-semibold text-white hover:bg-indigo-700">Compare a draft</Link>
      </div>
      <div className="flex flex-wrap gap-2">
        {list.data?.map((t) => (
          <button key={t.id} onClick={() => { setSel(t.id); setFocus(null); }} className={`rounded-lg border px-4 py-2 text-left text-sm ${t.id === id ? "border-indigo-600 bg-indigo-600 text-white" : "border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-800"}`}>
            <div className="font-semibold">{t.name.replace(" (Standard)", "")}</div><div className={`text-xs ${t.id === id ? "text-indigo-100" : "text-slate-500"}`}>{t.clause_count} clauses · {t.deviating_contracts}/{t.contracts} contracts deviate</div>
          </button>))}
      </div>
      {list.data && id && (
        <div className="flex items-center gap-3 rounded-lg border border-indigo-200 bg-indigo-50 p-3 text-sm dark:border-indigo-900 dark:bg-slate-800">
          <span className="flex-1">Templates are the starting point for new contracts: pick the clauses to include, fill the placeholders from a brief or the form, and edit in the online editor.</span>
          <Link className="rounded bg-indigo-600 px-3 py-1.5 font-medium text-white hover:bg-indigo-700" to={`/new?template=${GEN_KEY[list.data.find((t) => t.id === id)?.type ?? "MSA"] ?? "MSA"}`}>Create a contract from this template →</Link>
        </div>)}
      {lib.data && (
        <details className="rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800" open>
          <summary className="cursor-pointer text-sm font-semibold">Clause library coverage — which clauses each template contains ({lib.data.length} clauses × {KEYS.length} templates)</summary>
          <div className="mt-2 max-h-80 overflow-auto">
            <table className="w-full text-xs" aria-label="Clause coverage by template">
              <thead className="sticky top-0 bg-white dark:bg-slate-800"><tr><th className="p-1 text-left">Clause</th>{KEYS.map(([, l]) => <th key={l} className="w-16 p-1">{l}</th>)}</tr></thead>
              <tbody>
                {lib.data.map((c) => (
                  <tr key={c.key} className="border-t border-slate-100 dark:border-slate-700" title={c.preview}>
                    <td className="p-1">{c.heading}</td>
                    {KEYS.map(([k, l]) => <td key={k} className="p-1 text-center">{c.in_templates.includes(k) ? <b className="text-emerald-600" aria-label={`${l} includes ${c.heading}`}>✓</b> : <span className="text-slate-300" aria-hidden>·</span>}</td>)}
                  </tr>))}
              </tbody>
            </table>
          </div>
        </details>)}
      <Loading q={d} />
      {d.data && (
        <>
          <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
          <Card title={`${d.data.template.name} — clause by clause`}>
            <div className="max-h-[75vh] space-y-3 overflow-auto pr-1">
              {d.data.clauses.map((c, i) => (
                <div key={c.id} className="rounded border border-slate-200 p-3 text-sm dark:border-slate-700">
                  <div className="flex items-center gap-2"><b>{i + 1}. {c.heading}</b>
                    {c.variable && <span className="rounded bg-slate-200 px-1 text-[10px] dark:bg-slate-700">DEAL-SPECIFIC</span>}
                    {c.deviation_count > 0 && <span className="rounded border border-slate-400 px-1 text-[11px]">{c.deviation_count} contract{c.deviation_count > 1 ? "s" : ""} deviate</span>}</div>
                  <p className="mt-1">{c.standard_text}</p>
                  {c.playbook_position && <p className="mt-1 text-xs text-slate-500"><b>Playbook:</b> {c.playbook_position}{c.fallback_text && <> <b>Fallback:</b> {c.fallback_text}</>}</p>}
                </div>))}
            </div>
          </Card>
          <Card title="Deviation heatmap — executed contracts vs this template">
            {d.data.matrix.length === 0 ? <p className="text-sm text-slate-500">No executed contracts use this template.</p> : (
              <div className="overflow-x-auto">
                <table className="text-xs">
                  <thead><tr><th className="p-1 text-left">Contract</th>{d.data.clauses.filter((c) => !c.variable).map((c) => <th key={c.id} className="h-40 w-8 align-bottom"><div className="w-8 origin-bottom-left -rotate-[60deg] whitespace-nowrap pb-1 text-left font-medium">{c.heading}</div></th>)}</tr></thead>
                  <tbody>
                    {d.data.matrix.map((r) => (
                      <tr key={r.contract.id} className="border-t border-slate-100 dark:border-slate-700">
                        <td className="whitespace-nowrap p-1 pr-3"><Link className="text-indigo-600 hover:underline dark:text-indigo-400" to={`/contracts/${r.contract.id}`}>{r.contract.title}</Link></td>
                        {d.data!.clauses.filter((c) => !c.variable).map((c) => {
                          const cell = r.cells[String(c.id)];
                          return <td key={c.id} className="p-0.5 text-center">
                            {cell ? <button title={cell.deviation_summary} onClick={() => setFocus({ title: r.contract.title, heading: c.heading, cell })} className={`h-6 w-7 rounded text-[10px] font-bold ${CELL[cell.severity]}`}>{GLYPH[cell.severity]}</button>
                              : <span className="inline-block h-6 w-7 rounded bg-slate-100 dark:bg-slate-700/50" />}
                          </td>;
                        })}
                      </tr>))}
                  </tbody>
                </table>
                <div className="mt-2 flex items-center gap-3 text-xs text-slate-500">Legend: {(["critical", "high", "medium", "low"] as Sev[]).map((s) => <span key={s} className={`rounded px-1.5 py-0.5 font-bold ${CELL[s]}`}>{GLYPH[s]} {s}</span>)}<span className="rounded bg-slate-100 px-1.5 py-0.5 dark:bg-slate-700">matches standard</span></div>
              </div>)}
            {focus && <div className="mt-3 rounded border border-slate-300 p-3 text-sm dark:border-slate-600"><b>{focus.title}</b> · {focus.heading} <SeverityChip sev={focus.cell.severity} /><p className="mt-1">{focus.cell.deviation_summary}</p></div>}
          </Card>
          </div>
        </>)}
    </div>
  );
}
