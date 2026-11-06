import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Fragment, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Status, api, inFuture, when } from "../../lib";
import { Btn, Field, Toggle, inputCls } from "../../forms";
import { Card, Loading, Td, Th } from "../../ui";

type Cfg = Status & { inbox: string; inbox_files: number };
type Run = { id: number; started_at: string; finished_at: string | null; trigger: string; status: string; scanned: number; new_docs: number; updated: number; unchanged: number; failed: number; message: string | null };
type Ev = { id: number; path: string; contract_id: number | null; action: string; detail: string; created_at: string };

const FREQ: [number, string][] = [[15, "Every 15 minutes"], [30, "Every 30 minutes"], [60, "Every hour"], [120, "Every 2 hours (default)"], [360, "Every 6 hours"], [720, "Every 12 hours"], [1440, "Daily"]];
const SAMPLE = `# NDA – Example Supplier

**Parties:** Arcadia Retail Inc. (the "Customer") and Example Supplier Inc (the "Supplier")
**Effective Date:** 1 December 2026
**Document Type:** NDA

## 1. Term
This NDA commences on 1 December 2026 and, unless terminated earlier in accordance with its terms, expires on 1 December 2028.

## 2. Confidentiality
Each party shall keep the other party's Confidential Information confidential, use it only for the purposes of this NDA, and continue to do so for 3 years after the NDA ends.
`;

export default function Pipeline() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["pipeline"], queryFn: () => api<Cfg>("/api/admin/pipeline"), refetchInterval: 4000 });
  const runs = useQuery({ queryKey: ["runs"], queryFn: () => api<Run[]>("/api/admin/pipeline/runs"), refetchInterval: 4000 });
  const [minutes, setMinutes] = useState<number>(120);
  const [custom, setCustom] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const events = useQuery({ queryKey: ["events", open], enabled: open !== null, queryFn: () => api<Ev[]>(`/api/admin/pipeline/runs/${open}/events`) });
  const [doc, setDoc] = useState({ filename: "new-nda.md", content: SAMPLE, category: "Legal", owner: "Legal Operations" });
  useEffect(() => { if (q.data) setMinutes(q.data.config.interval_minutes); }, [q.data?.config.interval_minutes]);
  const refresh = () => { qc.invalidateQueries(); };
  const save = useMutation({
    mutationFn: (v: { enabled: boolean; interval_minutes: number }) => api("/api/admin/pipeline", { method: "PUT", body: JSON.stringify(v) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pipeline"] }),
  });
  const run = useMutation({ mutationFn: () => api("/api/admin/pipeline/run", { method: "POST" }), onSuccess: () => setTimeout(refresh, 1500) });
  const upload = useMutation({ mutationFn: () => api<{ run: { new_docs?: number; updated?: number } }>("/api/admin/pipeline/upload", { method: "POST", body: JSON.stringify(doc) }), onSuccess: refresh });
  if (!q.data) return <Loading q={q} />;
  const c = q.data.config;
  const freqValue = FREQ.some(([m]) => m === minutes) ? String(minutes) : "custom";
  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Schedule" className="lg:col-span-1">
          <div className="space-y-3">
            <div className="flex items-center justify-between"><span className="text-sm font-medium">Automatic processing</span><Toggle checked={c.enabled} label="Automatic processing" onChange={(v) => save.mutate({ enabled: v, interval_minutes: minutes })} /></div>
            <Field label="Frequency" hint="How often the folder is scanned for new or changed documents.">
              <select className={inputCls} value={freqValue} onChange={(e) => { if (e.target.value === "custom") { setCustom(String(minutes)); } else { const m = Number(e.target.value); setMinutes(m); save.mutate({ enabled: c.enabled, interval_minutes: m }); } }}>
                {FREQ.map(([m, l]) => <option key={m} value={m}>{l}</option>)}<option value="custom">Custom…</option>
              </select>
            </Field>
            {freqValue === "custom" && (
              <div className="flex items-end gap-2"><Field label="Every (minutes)"><input className={`${inputCls} w-28`} type="number" min={1} value={custom || minutes} onChange={(e) => setCustom(e.target.value)} /></Field>
                <Btn onClick={() => { const m = Number(custom); if (m >= 1) { setMinutes(m); save.mutate({ enabled: c.enabled, interval_minutes: m }); } }}>Apply</Btn></div>
            )}
            {save.error && <p className="text-sm text-red-600">{String(save.error)}</p>}
            <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
              <dt className="text-slate-500">Status</dt><dd>{q.data.running ? <b className="text-amber-600">Running…</b> : c.enabled ? "Idle" : "Paused"}</dd>
              <dt className="text-slate-500">Last run</dt><dd>{when(c.last_run_at)}</dd>
              <dt className="text-slate-500">Next run</dt><dd>{c.enabled ? `${when(c.next_run_at)} (${inFuture(c.next_run_at)})` : "paused"}</dd>
              <dt className="text-slate-500">Inbox folder</dt><dd className="break-all font-mono text-xs">{q.data.inbox}</dd>
              <dt className="text-slate-500">Files in folder</dt><dd>{q.data.inbox_files}</dd>
              <dt className="text-slate-500">Documents</dt><dd>{(q.data.documents.active ?? 0)} executed · {(q.data.documents.draft ?? 0)} draft</dd>
            </dl>
            <Btn onClick={() => run.mutate()} disabled={q.data.running || run.isPending}>{q.data.running ? "Running…" : "▶ Run now"}</Btn>
          </div>
        </Card>

        <Card title="Add a document to the folder" className="lg:col-span-2">
          <p className="mb-2 text-sm text-slate-500">Anything placed in the inbox folder is picked up on the next run. Paste a document here to drop it in and process it immediately (Markdown or plain text; vendor, type and parent are read from the document).</p>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="File name"><input className={inputCls} value={doc.filename} onChange={(e) => setDoc({ ...doc, filename: e.target.value })} /></Field>
            <Field label="Category (optional)"><input className={inputCls} value={doc.category} onChange={(e) => setDoc({ ...doc, category: e.target.value })} /></Field>
            <Field label="Owner (optional)"><input className={inputCls} value={doc.owner} onChange={(e) => setDoc({ ...doc, owner: e.target.value })} /></Field>
          </div>
          <Field label="Document text" className="mt-3"><textarea className={`${inputCls} h-40 font-mono text-xs`} value={doc.content} onChange={(e) => setDoc({ ...doc, content: e.target.value })} /></Field>
          <div className="mt-3 flex items-center gap-3">
            <Btn onClick={() => upload.mutate()} disabled={upload.isPending}>{upload.isPending ? "Processing…" : "Add to folder & process"}</Btn>
            {upload.data && <span className="text-sm text-emerald-700 dark:text-emerald-400">✓ Saved as {(upload.data as { saved_as?: string }).saved_as}. Processed; it now appears in Contracts.</span>}
            {upload.error && <span className="text-sm text-red-600">{String(upload.error)}</span>}
          </div>
        </Card>
      </div>

      <Card title="Run history">
        {runs.data && runs.data.length === 0 && <p className="text-sm text-slate-500">No runs yet.</p>}
        <table className="w-full text-sm"><thead><tr><Th>Run</Th><Th>Started</Th><Th>Trigger</Th><Th className="text-right">Scanned</Th><Th className="text-right">New</Th><Th className="text-right">Updated</Th><Th className="text-right">Unchanged</Th><Th className="text-right">Failed</Th><Th>Status</Th></tr></thead>
          <tbody>
            {runs.data?.map((r) => (
              <Fragment key={r.id}>
                <tr className="cursor-pointer border-t border-slate-100 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-700/40" onClick={() => setOpen(open === r.id ? null : r.id)}>
                  <Td>#{r.id} <span className="text-slate-400">{open === r.id ? "▾" : "▸"}</span></Td><Td className="whitespace-nowrap">{when(r.started_at)}</Td><Td className="capitalize">{r.trigger}</Td>
                  <Td className="text-right tabular-nums">{r.scanned}</Td><Td className="text-right tabular-nums font-medium">{r.new_docs}</Td><Td className="text-right tabular-nums">{r.updated}</Td>
                  <Td className="text-right tabular-nums text-slate-500">{r.unchanged}</Td><Td className={`text-right tabular-nums ${r.failed ? "font-bold text-red-600" : ""}`}>{r.failed}</Td>
                  <Td>{r.status === "completed" ? <span className="font-medium text-emerald-700 dark:text-emerald-400">✓ completed</span> : r.status === "running" ? <span className="text-amber-600">running…</span> : <span className="text-red-600">✗ {r.status}</span>}</Td>
                </tr>
                {open === r.id && (
                  <tr><td colSpan={9} className="bg-slate-50 p-3 dark:bg-slate-900/50">
                    {r.message && <p className="mb-2 text-xs text-slate-500">{r.message}</p>}
                    <ul className="max-h-60 space-y-0.5 overflow-auto text-xs">
                      {events.data?.filter((e) => e.action !== "unchanged").map((e) => (
                        <li key={e.id} className="flex gap-2"><span className={`w-16 shrink-0 font-semibold uppercase ${e.action === "failed" ? "text-red-600" : e.action === "new" ? "text-emerald-700" : "text-sky-700"}`}>{e.action}</span>
                          <span className="font-mono text-slate-500">{e.path}</span><span>{e.contract_id ? <Link className="text-indigo-600 hover:underline" to={`/contracts/${e.contract_id}`}>{e.detail}</Link> : e.detail}</span></li>))}
                      {events.data && events.data.every((e) => e.action === "unchanged") && <li className="text-slate-500">All {events.data.length} files were unchanged — nothing to process.</li>}
                    </ul></td></tr>)}
              </Fragment>))}
          </tbody></table>
      </Card>
    </div>
  );
}
