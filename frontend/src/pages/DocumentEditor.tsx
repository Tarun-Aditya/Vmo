import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import DocEditor from "../components/DocEditor";
import { Btn, inputCls } from "../forms";
import { API, api, when } from "../lib";
import { Card, Loading, Sev, SeverityChip } from "../ui";

type Content = { id: number; title: string; vendor: string; type: string; status: string; md: string; editable: boolean; version: number; versions: { version: number; note: string | null; created_at: string; chars: number }[] };
type Check = { rule_key: string; name: string; status: "pass" | "fail" | "na"; severity: Sev; actual: string | null; expected: string | null; suggested_text: string | null };
type Analysis = { checks: Check[]; summary: { pass: number; fail: number; na: number }; deviations: number };

/** Open a draft in the online Word-style editor with a live checklist, versions and save. */
export default function DocumentEditor() {
  const { id } = useParams();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["doc-content", id], queryFn: () => api<Content>(`/api/documents/${id}/content`) });
  const [md, setMd] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [saved, setSaved] = useState<string>("");
  const loaded = useRef<string>("");
  const check = useMutation({ mutationFn: (t: string) => api<Analysis>("/api/generator/analyze", { method: "POST", body: JSON.stringify({ template: "x", md: t }) }), onSuccess: setAnalysis });
  useEffect(() => { if (q.data && q.data.md !== loaded.current) { loaded.current = q.data.md; setMd(q.data.md); check.mutate(q.data.md); } }, [q.data?.md]);
  const save = useMutation({
    mutationFn: () => api<{ version: number }>(`/api/documents/${id}/content`, { method: "PUT", body: JSON.stringify({ md, note: note || null }) }),
    onSuccess: (r) => { setSaved(`Saved as version ${r.version}`); setNote(""); qc.invalidateQueries(); },
  });
  if (!q.data || md === null) return <Loading q={q} />;
  const d = q.data;
  const dirty = md !== d.md;
  const restore = async (v: number) => { const r = await api<{ md: string }>(`/api/documents/${id}/versions/${v}`); setMd(r.md); check.mutate(r.md); setSaved(`Loaded version ${v} — save to keep it`); };
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">{d.title}</h1>
        <span className="rounded bg-slate-200 px-1.5 text-xs font-semibold uppercase dark:bg-slate-700">{d.type}</span>
        <span className={`rounded px-1.5 text-xs font-semibold ${d.editable ? "bg-amber-100 text-amber-900" : "bg-slate-200 text-slate-700"}`}>{d.editable ? "DRAFT" : "EXECUTED · read only"}</span>
        <span className="ml-auto flex gap-3 text-sm"><a className="text-indigo-600 hover:underline" href={`${API}/api/documents/${d.id}/export.docx`} download>⬇ Download .docx</a><Link className="text-indigo-600 hover:underline" to={`/redline/${d.id}`}>Review redline</Link><Link className="text-indigo-600 hover:underline" to={`/contracts/${d.id}`}>Open details</Link></span>
      </div>
      <div className="grid gap-4 lg:grid-cols-4">
        <div className="lg:col-span-3">
          <DocEditor value={md} onChange={setMd} readOnly={!d.editable} title={d.title} status={dirty ? "Unsaved changes" : saved || `Version ${d.version}`} height="75vh" />
        </div>
        <div className="space-y-3">
          {d.editable && (
            <Card title="Save">
              <input className={inputCls} placeholder="What changed? (optional)" aria-label="Version note" value={note} onChange={(e) => setNote(e.target.value)} />
              <div className="mt-2 flex items-center gap-2"><Btn onClick={() => save.mutate()} disabled={!dirty || save.isPending}>{save.isPending ? "Saving…" : "Save new version"}</Btn>
                <Btn kind="ghost" onClick={() => check.mutate(md)} disabled={check.isPending}>{check.isPending ? "Checking…" : "Check"}</Btn></div>
              <p className="mt-2 text-xs text-slate-500">Saving writes the document back to the watched folder; it is re-extracted and re-checked straight away, and every screen updates.</p>
              {save.error && <p className="mt-1 text-sm text-red-600">{String(save.error)}</p>}
            </Card>)}
          <Card title={analysis ? `Checklist — ${analysis.summary.pass} pass · ${analysis.summary.fail} fail` : "Checklist"}>
            {!analysis ? <p className="text-sm text-slate-500">Checking…</p> : (
              <ul className="space-y-1 text-sm">
                {analysis.checks.filter((c) => c.status !== "na").map((c) => (
                  <li key={c.rule_key} className="rounded border border-slate-200 px-2 py-1 dark:border-slate-700">
                    <div className="flex items-center gap-2"><b className={c.status === "pass" ? "text-emerald-600" : "text-red-600"}>{c.status === "pass" ? "✓" : "✗"}</b><span className="flex-1">{c.name}</span>{c.status === "fail" && <SeverityChip sev={c.severity} />}</div>
                    {c.status === "fail" && c.suggested_text && <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">Suggested: {c.suggested_text}</p>}
                  </li>))}
              </ul>)}
            <p className="mt-2 text-xs text-slate-500">{analysis?.deviations ?? 0} change(s) from the standard template.</p>
          </Card>
          <Card title="Version history">
            <ul className="space-y-1 text-sm">
              {d.versions.length === 0 && <li className="text-slate-500">Original version — no edits yet.</li>}
              {d.versions.map((v) => (
                <li key={v.version} className="flex items-center gap-2"><b>v{v.version}</b><span className="flex-1 truncate text-slate-600 dark:text-slate-300">{v.note}</span><span className="text-xs text-slate-500">{when(v.created_at)}</span>
                  {d.editable && <button className="text-xs text-indigo-600 hover:underline" onClick={() => restore(v.version)}>Load</button>}</li>))}
            </ul>
          </Card>
        </div>
      </div>
    </div>
  );
}
