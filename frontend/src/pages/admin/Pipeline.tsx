import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Fragment, useState } from "react";
import { Link } from "react-router-dom";
import { Status, api, inFuture, when } from "../../lib";
import { Btn, Field, Toggle, inputCls } from "../../forms";
import { Card, Loading, Td, Th } from "../../ui";

type Cfg = Status & { inbox: string; inbox_files: number };
type Run = { id: number; pipeline: string; started_at: string; finished_at: string | null; trigger: string; status: string; scanned: number; new_docs: number; updated: number; unchanged: number; failed: number; message: string | null };
type Ev = { id: number; path: string; contract_id: number | null; action: string; detail: string; created_at: string };

const FREQ: [number, string][] = [[15, "Every 15 minutes"], [30, "Every 30 minutes"], [60, "Every hour"], [120, "Every 2 hours (default)"], [360, "Every 6 hours"], [720, "Every 12 hours"], [1440, "Daily"]];
const inDays = (n: number) => { const d = new Date(Date.now() + n * 864e5); return d.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" }); };
const SAMPLE = () => `# NDA – Example Supplier

**Parties:** Arcadia Retail Inc. (the "Customer") and Example Supplier Inc (the "Supplier")
**Effective Date:** ${inDays(30)}
**Document Type:** NDA

## 1. Term
This NDA commences on ${inDays(30)} and, unless terminated earlier in accordance with its terms, expires on 1 December 2028.

## 2. Confidentiality
Each party shall keep the other party's Confidential Information confidential, use it only for the purposes of this NDA, and continue to do so for 3 years after the NDA ends.
`;


type Pl = { key: string; name: string; description: string; folders: string; trigger_mode: "periodic" | "on_change" | "manual"; enabled: boolean; interval_minutes: number; last_run_at: string | null; next_run_at: string | null; files: number };
const TRIGGERS: [Pl["trigger_mode"], string][] = [["periodic", "Periodic — on a schedule"], ["on_change", "Dynamic — when a new or changed file appears"], ["manual", "Manual only"]];

function PipelineCard({ pl, running }: { pl: Pl; running: boolean }) {
  const qc = useQueryClient();
  const [mode, setMode] = useState(pl.trigger_mode);
  const [mins, setMins] = useState(pl.interval_minutes);
  const [folders, setFolders] = useState(pl.folders);
  const save = useMutation({
    mutationFn: (v: Partial<{ enabled: boolean; trigger_mode: string; interval_minutes: number; folders: string }>) =>
      api(`/api/admin/pipelines/${pl.key}`, { method: "PUT", body: JSON.stringify({ enabled: pl.enabled, trigger_mode: mode, interval_minutes: mins, folders, ...v }) }),
    onSuccess: () => qc.invalidateQueries(),
  });
  const run = useMutation({ mutationFn: () => api(`/api/admin/pipelines/${pl.key}/run`, { method: "POST" }), onSuccess: () => setTimeout(() => qc.invalidateQueries(), 1500) });
  const freq = FREQ.some(([m]) => m === mins) ? String(mins) : "custom";
  return (
    <Card title={pl.name} right={<Toggle checked={pl.enabled} label={`${pl.name} enabled`} onChange={(v) => save.mutate({ enabled: v })} />}>
      <div className="space-y-3" data-pipeline={pl.key}>
        <p className="text-xs text-slate-500">{pl.description}</p>
        <Field label="When to run">
          <select className={inputCls} aria-label={`${pl.name} trigger`} value={mode} onChange={(e) => { const m = e.target.value as Pl["trigger_mode"]; setMode(m); save.mutate({ trigger_mode: m }); }}>
            {TRIGGERS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </Field>
        {mode === "periodic" && (
          <Field label="Frequency" hint="How often the folders are scanned.">
            <select className={inputCls} aria-label={`${pl.name} frequency`} value={freq} onChange={(e) => { if (e.target.value !== "custom") { const m = Number(e.target.value); setMins(m); save.mutate({ interval_minutes: m }); } }}>
              {FREQ.map(([m, l]) => <option key={m} value={m}>{l}</option>)}<option value="custom">Custom ({mins} min)</option>
            </select>
          </Field>)}
        {mode === "on_change" && <p className="text-xs text-slate-500">Checked every 20 seconds; runs as soon as a file is added or edited in the watched folders.</p>}
        <Field label="Watched folders" hint="Sub-folders of the inbox, comma separated.">
          <input className={inputCls} aria-label={`${pl.name} folders`} value={folders} onChange={(e) => setFolders(e.target.value)} onBlur={() => folders !== pl.folders && save.mutate({ folders })} />
        </Field>
        <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
          <dt className="text-slate-500">Status</dt><dd>{running ? <b className="text-amber-600">Running…</b> : !pl.enabled ? "Paused" : "Idle"}</dd>
          <dt className="text-slate-500">Files watched</dt><dd>{pl.files}</dd>
          <dt className="text-slate-500">Last run</dt><dd>{when(pl.last_run_at)}</dd>
          <dt className="text-slate-500">Next run</dt><dd>{!pl.enabled ? "paused" : mode === "manual" ? "manual" : mode === "on_change" ? "on next change" : `${when(pl.next_run_at)} (${inFuture(pl.next_run_at)})`}</dd>
        </dl>
        <Btn onClick={() => run.mutate()} disabled={running || run.isPending}>{running ? "Running…" : "▶ Run now"}</Btn>
        {save.error && <p className="text-sm text-red-600">{String(save.error)}</p>}
      </div>
    </Card>
  );
}

export default function Pipeline() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["pipeline"], queryFn: () => api<Cfg>("/api/admin/pipeline"), refetchInterval: 4000 });
  const pls = useQuery({ queryKey: ["pipelines"], queryFn: () => api<{ pipelines: Pl[]; running: boolean }>("/api/admin/pipelines"), refetchInterval: 4000 });
  const runs = useQuery({ queryKey: ["runs"], queryFn: () => api<Run[]>("/api/admin/pipeline/runs"), refetchInterval: 4000 });
  const [open, setOpen] = useState<number | null>(null);
  const events = useQuery({ queryKey: ["events", open], enabled: open !== null, queryFn: () => api<Ev[]>(`/api/admin/pipeline/runs/${open}/events`) });
  const [doc, setDoc] = useState({ filename: "new-nda.md", content: SAMPLE(), category: "", owner: "", status: "active" });
  const refresh = () => { qc.invalidateQueries(); };
  const upload = useMutation({ mutationFn: () => api<{ run: { new_docs?: number; updated?: number } }>("/api/admin/pipeline/upload", { method: "POST", body: JSON.stringify(doc) }), onSuccess: refresh });
  if (!q.data) return <Loading q={q} />;
  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-1" aria-label="Pipelines">
          {pls.data?.pipelines.map((pl) => <PipelineCard key={pl.key} pl={pl} running={pls.data!.running} />)}
          <p className="text-xs text-slate-500">Inbox folder: <span className="break-all font-mono">{q.data.inbox}</span> · {q.data.inbox_files} files · {(q.data.documents.active ?? 0)} executed · {(q.data.documents.draft ?? 0)} draft</p>
        </div>

        <Card title="Add a document to the folder" className="lg:col-span-2">
          <p className="mb-2 text-sm text-slate-500">Anything placed in the inbox folder is picked up on the next run. Paste a document here to drop it in and process it immediately (Markdown or plain text; vendor, type and parent are read from the document).</p>
          <div className="grid gap-3 sm:grid-cols-4">
            <Field label="File name"><input className={inputCls} value={doc.filename} onChange={(e) => setDoc({ ...doc, filename: e.target.value })} /></Field>
            <Field label="Category (optional)"><input className={inputCls} value={doc.category} onChange={(e) => setDoc({ ...doc, category: e.target.value })} /></Field>
            <Field label="Treat as"><select className={inputCls} aria-label="Document kind" value={doc.status} onChange={(e) => setDoc({ ...doc, status: e.target.value })}><option value="active">Executed contract</option><option value="draft">Vendor draft (redline queue)</option></select></Field>
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
        <table className="w-full text-sm"><thead><tr><Th>Run</Th><Th>Started</Th><Th>Pipeline</Th><Th>Trigger</Th><Th className="text-right">Scanned</Th><Th className="text-right">New</Th><Th className="text-right">Updated</Th><Th className="text-right">Unchanged</Th><Th className="text-right">Failed</Th><Th>Status</Th></tr></thead>
          <tbody>
            {runs.data?.map((r) => (
              <Fragment key={r.id}>
                <tr className="cursor-pointer border-t border-slate-100 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-700/40" onClick={() => setOpen(open === r.id ? null : r.id)}>
                  <Td>#{r.id} <span className="text-slate-400">{open === r.id ? "▾" : "▸"}</span></Td><Td className="whitespace-nowrap">{when(r.started_at)}</Td><Td className="capitalize">{r.pipeline}</Td><Td className="capitalize">{r.trigger}</Td>
                  <Td className="text-right tabular-nums">{r.scanned}</Td><Td className="text-right tabular-nums font-medium">{r.new_docs}</Td><Td className="text-right tabular-nums">{r.updated}</Td>
                  <Td className="text-right tabular-nums text-slate-500">{r.unchanged}</Td><Td className={`text-right tabular-nums ${r.failed ? "font-bold text-red-600" : ""}`}>{r.failed}</Td>
                  <Td>{r.status === "completed" ? <span className="font-medium text-emerald-700 dark:text-emerald-400">✓ completed</span> : r.status === "running" ? <span className="text-amber-600">running…</span> : <span className="text-red-600">✗ {r.status}</span>}</Td>
                </tr>
                {open === r.id && (
                  <tr><td colSpan={10} className="bg-slate-50 p-3 dark:bg-slate-900/50">
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
