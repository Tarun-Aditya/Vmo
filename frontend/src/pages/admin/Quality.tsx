import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Btn } from "../../forms";
import { API, api, authUrl, when } from "../../lib";
import { Card, Loading } from "../../ui";

type Sum = { documents_reviewed: number; overall_agreement: number | null; fields: { field: string; extracted: number; corrected: number; agreement: number | null }[]; recent: { contract_id: number; field: string; original_value: string | null; corrected_value: string | null; corrected_by: string; created_at: string }[] };
const pct = (v: number | null) => (v === null ? "—" : `${(v * 100).toFixed(1)}%`);

/** Accuracy measured from corrections on reviewed contracts; export a review sheet, have it checked in a spreadsheet, import it back. */
export default function Quality() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["quality"], queryFn: () => api<Sum>("/api/quality/summary") });
  const [msg, setMsg] = useState("");
  const imp = useMutation({ mutationFn: (content: string) => api<{ applied: number; rejected: { row: string; error: string }[] }>("/api/quality/review-sheet", { method: "POST", body: JSON.stringify({ content }) }),
    onSuccess: (r) => { setMsg(`${r.applied} correction(s) applied${r.rejected.length ? `, ${r.rejected.length} rejected: ${r.rejected.map((x) => `${x.row} (${x.error})`).join("; ").slice(0, 300)}` : ""}`); qc.invalidateQueries(); } });
  if (!q.data) return <Loading q={q} />;
  return (
    <div className="space-y-4">
      <Card title="Review sheet">
        <p className="mb-2 text-sm text-slate-500">Download every extracted field of every executed contract as a spreadsheet, have someone fix the <code>correct_value</code> column where the extraction is wrong, and import it back. Corrected values replace the extraction everywhere, survive re-processing, and measure how accurate the extraction was.</p>
        <div className="flex flex-wrap items-center gap-3">
          <a className="rounded border border-slate-300 px-3 py-1.5 text-sm font-medium hover:bg-slate-100 dark:border-slate-600 dark:hover:bg-slate-700" href={authUrl("/api/quality/review-sheet")} download>⬇ Download review sheet (.csv)</a>
          <label className="cursor-pointer"><span className="rounded bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700">Import corrected sheet…</span>
            <input type="file" accept=".csv" className="sr-only" aria-label="Import corrected sheet" onChange={async (e) => { const f = e.target.files?.[0]; if (f) imp.mutate(await f.text()); e.target.value = ""; }} /></label>
          {msg && <span role="status" className="text-sm">{msg}</span>}
        </div>
      </Card>
      <Card title={`Measured accuracy — ${q.data.documents_reviewed} reviewed document${q.data.documents_reviewed !== 1 ? "s" : ""} · overall ${pct(q.data.overall_agreement)}`}>
        {q.data.fields.length === 0 ? <p className="text-sm text-slate-500">Nothing corrected yet: correct a field on a contract (edit next to the value) or import a review sheet.</p> : (
          <table className="w-full text-sm"><thead className="text-left text-xs text-slate-500"><tr><th className="py-1">Field</th><th>Extracted</th><th>Corrected</th><th>Agreement</th></tr></thead>
            <tbody>{q.data.fields.map((f) => <tr key={f.field} className="border-t border-slate-100 dark:border-slate-700"><td className="py-1">{f.field}</td><td className="tabular-nums">{f.extracted}</td><td className="tabular-nums">{f.corrected}</td><td className="tabular-nums font-medium">{pct(f.agreement)}</td></tr>)}</tbody></table>)}
        <p className="mt-2 text-xs text-slate-500">Agreement = share of extracted values nobody had to correct, over the documents that were reviewed. Labels for <code>evals/real_eval.py</code>: <a className="text-indigo-600 underline" href={`${API}/api/quality/labels`}>/api/quality/labels</a>.</p>
      </Card>
      {q.data.recent.length > 0 && <Card title="Recent corrections"><ul className="space-y-0.5 text-xs">{q.data.recent.map((r, i) => <li key={i}>{when(r.created_at)} · contract {r.contract_id} · <b>{r.field}</b>: {r.original_value ?? "—"} → {r.corrected_value ?? "—"} <span className="text-slate-500">({r.corrected_by})</span></li>)}</ul></Card>}
    </div>
  );
}
