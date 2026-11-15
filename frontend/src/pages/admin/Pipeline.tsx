import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Fragment, ReactNode, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Status, api, fmtDate, inFuture, when } from "../../lib";
import { Btn, Field, Toggle, inputCls } from "../../forms";
import { Card, ConfidenceBadge, Loading, Sev, SeverityChip, Td, Th } from "../../ui";

type Cfg = Status & { inbox: string; inbox_files: number };
type Run = { id: number; pipeline: string; started_at: string; finished_at: string | null; trigger: string; status: string; scanned: number; new_docs: number; updated: number; unchanged: number; failed: number; message: string | null };
type Ev = { id: number; path: string; contract_id: number | null; action: string; detail: string; content_hash: string | null; size_bytes: number | null; reason: string | null; created_at: string };

const FREQ: [number, string][] = [[15, "Every 15 minutes"], [30, "Every 30 minutes"], [60, "Every hour"], [120, "Every 2 hours (default)"], [360, "Every 6 hours"], [720, "Every 12 hours"], [1440, "Daily"]];
const inDays = (n: number) => { const d = new Date(Date.now() + n * 864e5); return d.toLocaleDateString("en-US", { day: "numeric", month: "long", year: "numeric" }); };
const SAMPLE = (customer: string) => `# NDA – Example Supplier

**Parties:** ${customer} (the "Customer") and Example Supplier Inc (the "Supplier")
**Effective Date:** ${inDays(30)}
**Document Type:** NDA

## 1. Term
This NDA commences on ${inDays(30)} and, unless terminated earlier in accordance with its terms, expires on December 1, 2028.

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
  const run = useMutation({ mutationFn: (force?: boolean) => api(`/api/admin/pipelines/${pl.key}/run${force === true ? "?force=true" : ""}`, { method: "POST" }), onSuccess: () => setTimeout(() => qc.invalidateQueries(), 1500) });
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
        <Btn onClick={() => run.mutate(false)} disabled={running || run.isPending}>{running ? "Running…" : "▶ Run now"}</Btn>
        <Btn kind="ghost" onClick={() => { if (window.confirm("Re-read every document with the current engine (Demo = offline, Live = Claude)? Corrections you made are kept.")) run.mutate(true); }} disabled={running || run.isPending} title="Ignore the 'unchanged' shortcut and extract everything again with the engine that is active now">↻ Re-extract all</Btn>
        {save.error && <p className="text-sm text-red-600">{String(save.error)}</p>}
      </div>
    </Card>
  );
}

// ------------------------------------------------------------------ the run in progress (or the last one), document by document
type LiveDoc = { path: string; name: string; format: string; size: number; status: "queued" | "running" | "done" | "error"; started?: number; finished?: number; error?: string;
  action?: string; reason?: string; contract_id?: number; title?: string; type?: string; vendor?: string; parent?: string | null; parent_id?: number | null; overrides?: string[];
  read?: { pages: number; paged: boolean; words: number; scanned: boolean };
  structure?: { clauses: number; types: [string, number][]; title: string; vendor: string; type: string };
  extract?: { engine: string; fields: { field: string; label: string; value: string | null; page: number | null; confidence: number | null }[] };
  index?: { vectors: number; dims: number };
  check?: { checks: number; failed_count: number; failed: { name: string; severity: Sev }[]; act_by: string | null; auto_renew: boolean } };
type Live = { run_id?: number; trigger?: string; engine?: string; status?: "running" | "completed" | "failed"; started?: number; finished?: number | null; order?: string[]; docs?: Record<string, LiveDoc> };
const STEP_NAMES: [keyof LiveDoc, string][] = [["read", "Reading"], ["structure", "Finding clauses"], ["extract", "Extracting terms"], ["index", "Indexing"], ["check", "Checking"]];
const OVERRIDE_LABEL: Record<string, string> = { expiry_date: "end date", payment_terms_days: "payment terms", notice_period_days: "notice period", auto_renew: "renewal", annual_value: "annual value" };
const shortV = (v?: string) => (v ?? "").replace(/,? (Inc|LLC|Co|Corp)\.?$/, "");
const termsOf = (d: LiveDoc) => d.extract?.fields.filter((f) => f.value !== null).length ?? 0;
function showVal(f: { field: string; value: string | null }) {
  if (f.value === null) return f.field === "liability_cap_multiple" ? "no cap stated" : "—";
  if (f.value === "True") return "Yes";
  if (f.value === "False") return "No";
  return /date$/.test(f.field) ? fmtDate(f.value) : f.value;
}

function LiveRun() {
  const [now, setNow] = useState(Date.now());
  const live = useQuery({ queryKey: ["pipeline-live"], queryFn: () => api<Live>("/api/admin/pipeline/live"), refetchInterval: (q) => (q.state.data?.status === "running" ? 1000 : 4000) });
  const L = live.data;
  const running = L?.status === "running";
  useEffect(() => { if (!running) return; const h = setInterval(() => setNow(Date.now()), 500); return () => clearInterval(h); }, [running]);
  const [open, setOpen] = useState<string | null>(null);
  if (!L || !L.run_id) return <Card title="Live run"><p className="text-sm text-slate-500">No run yet in this session. Start one with <b>Run now</b>, add files below, or wait for the schedule: every document will appear here as it is read.</p></Card>;
  const docs = (L.order ?? []).map((k) => L.docs?.[k]).filter(Boolean) as LiveDoc[];
  const done = docs.filter((d) => d.status === "done" || d.status === "error").length;
  const sum = (f: (d: LiveDoc) => number) => docs.reduce((a, d) => a + f(d), 0);
  const elapsed = ((L.finished ? L.finished * 1000 : now) - (L.started ?? 0) * 1000) / 1000;
  const counters: [string, string][] = [
    ["Documents", `${done}/${docs.length}`], ["New or changed", `${docs.filter((d) => d.action === "new" || d.action === "updated").length}`],
    ["Pages read", `${sum((d) => (d.read?.paged ? d.read.pages : 0))}`], ["Clauses indexed", `${sum((d) => d.index?.vectors ?? 0)}`],
    ["Terms extracted", `${sum(termsOf)}`], ["Linked to a parent", `${docs.filter((d) => d.parent && (d.action === "new" || d.action === "updated")).length}`],
    ["Duplicates", `${docs.filter((d) => d.action === "duplicate").length}`], ["Already read", `${docs.filter((d) => d.action === "unchanged" || d.action === "moved").length}`],
    ["Elapsed", `${Math.floor(elapsed / 60)}:${String(Math.floor(elapsed % 60)).padStart(2, "0")}`],
  ];
  const status = (d: LiveDoc): ReactNode => {
    if (d.status === "queued") return <span className="text-slate-400">waiting</span>;
    if (d.status === "running") return <span className="font-medium text-indigo-700 dark:text-indigo-300"><span className="animate-pulse" aria-hidden>● </span>{STEP_NAMES.find(([k]) => !d[k])?.[1] ?? "Saving"}…</span>;
    if (d.status === "error") return <span className="font-medium text-red-700 dark:text-red-300" title={d.error}>✗ failed</span>;
    if (d.action === "duplicate") return <span className="font-medium text-violet-700 dark:text-violet-300" title={d.reason}>⧉ duplicate</span>;
    if (d.action === "unchanged" || d.action === "moved") return <span className="text-slate-500" title={d.reason}>= already read</span>;
    return <span className="font-medium text-emerald-700 dark:text-emerald-300">✓ {d.action === "updated" ? "re-read" : "new"}</span>;
  };
  return (
    <Card title={<>Live run #{L.run_id} · {L.trigger} · {L.engine}</>} right={<span className={`text-sm font-semibold ${running ? "text-amber-600" : L.status === "failed" ? "text-red-600" : "text-emerald-700"}`}>{running ? "Running…" : L.status === "failed" ? "Failed" : `Finished ${L.finished ? new Date(L.finished * 1000).toLocaleTimeString() : ""}`}</span>}>
      <p className="mb-3 text-xs text-slate-500">Every run appears here, whatever started it (schedule, a file appearing in a watched folder, a connector sync, an upload, Run now), for any number of documents.
        Each document is <b>read</b> (text and pages; scans by OCR), split into clauses that are <b>recognised</b>, its terms <b>extracted</b> with their clause and page, its clauses <b>indexed</b> as vectors for search by meaning, and <b>checked</b> against your standards.
        Files read before are recognised by size, time and content fingerprint and skipped.</p>
      <dl className="mb-3 grid grid-cols-3 gap-2 sm:grid-cols-5 xl:grid-cols-9" aria-live="polite">
        {counters.map(([k, v]) => <div key={k} className="rounded-lg border border-line p-2 dark:border-slate-700"><dt className="text-[10.5px] uppercase tracking-wider text-slate-500">{k}</dt><dd className="mt-0.5 text-lg font-semibold tabular-nums">{v}</dd></div>)}
      </dl>
      <div className="max-h-[32rem] overflow-auto rounded border border-slate-100 dark:border-slate-700">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-slate-50 text-left text-xs uppercase text-slate-500 dark:bg-slate-900"><tr><th className="px-2 py-1.5">Document</th><th className="px-2 py-1.5">Status</th><th className="px-2 py-1.5 text-right">Pages</th><th className="px-2 py-1.5 text-right">Clauses</th><th className="px-2 py-1.5 text-right">Terms</th><th className="px-2 py-1.5">Read as</th><th className="px-2 py-1.5">Linked</th><th className="px-2 py-1.5 text-right">Checks</th><th className="px-2 py-1.5 text-right">Time</th></tr></thead>
          <tbody>
            {docs.map((d) => (
              <Fragment key={d.path}>
                <tr className={`cursor-pointer border-t border-slate-100 dark:border-slate-700 ${d.status === "running" ? "bg-indigo-50/70 dark:bg-indigo-950/30" : "hover:bg-slate-50 dark:hover:bg-slate-700/40"}`} onClick={() => setOpen(open === d.path ? null : d.path)}>
                  <td className="px-2 py-1.5"><div className="font-medium">{d.extract ? <span className="text-slate-400">{open === d.path ? "▾ " : "▸ "}</span> : null}{d.name}</div><div className="text-[11px] text-slate-500">{d.format} · {Math.round(d.size / 1024)} KB{d.read?.scanned ? " · scan, read by OCR" : ""}</div></td>
                  <td className="whitespace-nowrap px-2 py-1.5">{status(d)}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums">{d.read ? (d.read.paged ? d.read.pages : "Word") : ""}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums">{d.structure?.clauses ?? ""}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums">{d.extract ? termsOf(d) : ""}</td>
                  <td className="px-2 py-1.5">{d.type || d.structure ? <>{d.contract_id ? <Link onClick={(e) => e.stopPropagation()} className="font-medium text-indigo-700 hover:underline dark:text-indigo-300" to={`/contracts/${d.contract_id}`}>{d.type ?? d.structure?.type}</Link> : <b>{d.structure?.type}</b>} · {shortV(d.vendor ?? d.structure?.vendor)}</> : ""}</td>
                  <td className="px-2 py-1.5 text-xs">{d.parent ? <>under <Link onClick={(e) => e.stopPropagation()} className="text-indigo-700 hover:underline dark:text-indigo-300" to={`/contracts/${d.parent_id}`}>{d.parent.replace(/ – .*$/, "")}</Link>{d.overrides?.length ? <div>changes its {d.overrides.map((o) => OVERRIDE_LABEL[o] ?? o.replace(/_/g, " ")).join(" and ")}</div> : null}</> : ""}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums">{d.check ? <span className={d.check.failed_count ? "text-amber-700 dark:text-amber-300" : ""}>{d.check.failed_count}/{d.check.checks}</span> : ""}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums text-slate-500">{d.started && d.finished ? `${(d.finished - d.started).toFixed(1)}s` : ""}</td>
                </tr>
                {open === d.path && d.extract && (
                  <tr className="bg-slate-50/60 dark:bg-slate-900/40"><td colSpan={9} className="px-3 py-2">
                    <div className="grid gap-4 md:grid-cols-[1.4fr_1fr]">
                      <table className="text-sm"><tbody>{d.extract.fields.map((f) => <tr key={f.field}><td className="pr-3 text-slate-500">{f.label}</td><td className="pr-2 font-medium">{showVal(f)}</td><td className="pr-2 text-xs text-slate-400">{f.value !== null && f.page && d.read?.paged ? `p.${f.page}` : ""}</td><td>{f.value !== null && <ConfidenceBadge v={f.confidence} />}</td></tr>)}</tbody></table>
                      <div className="space-y-1 text-sm">
                        {d.check?.act_by && <p><span className="text-slate-500">{d.check.auto_renew ? "Last day to stop renewal" : "Ends"}:</span> <b>{fmtDate(d.check.act_by)}</b></p>}
                        {d.check?.failed.slice(0, 6).map((f) => <div key={f.name} className="flex justify-between gap-2"><span>{f.name}</span><SeverityChip sev={f.severity} /></div>)}
                        <p className="text-xs text-slate-500">{d.structure?.types.map(([k]) => k.replace(/_/g, " ")).join(" · ")}</p>
                        {d.contract_id && <Link className="text-sm font-medium text-indigo-700 hover:underline dark:text-indigo-300" to={`/contracts/${d.contract_id}`}>Open the contract with its sources →</Link>}
                      </div>
                    </div>
                  </td></tr>)}
              </Fragment>))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function AddFiles() {
  const qc = useQueryClient();
  const [files, setFiles] = useState<File[]>([]);
  const [opt, setOpt] = useState({ category: "", owner: "", status: "active" });
  const [drag, setDrag] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const toB64 = (f: File) => new Promise<string>((res, rej) => { const r = new FileReader(); r.onload = () => res(String(r.result).split(",")[1] ?? ""); r.onerror = rej; r.readAsDataURL(f); });
  const send = useMutation({
    mutationFn: async () => api<{ saved: string[] }>("/api/admin/pipeline/files", { method: "POST", body: JSON.stringify({ ...opt, category: opt.category || null, owner: opt.owner || null, files: await Promise.all(files.map(async (f) => ({ filename: f.name, content_b64: await toB64(f) }))) }) }),
    onSuccess: () => { setFiles([]); setTimeout(() => qc.invalidateQueries(), 800); },
  });
  const add = (fl: FileList | null) => fl && setFiles((cur) => [...cur, ...Array.from(fl).filter((f) => /\.(pdf|docx|md|txt|html?)$/i.test(f.name))]);
  return (
    <Card title="Add documents">
      <div role="button" tabIndex={0} aria-label="Drop PDF or Word files here, or choose files" onClick={() => input.current?.click()} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") input.current?.click(); }}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={(e) => { e.preventDefault(); setDrag(false); add(e.dataTransfer.files); }}
        className={`flex h-28 cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed text-sm ${drag ? "border-indigo-500 bg-indigo-50 dark:bg-indigo-950/40" : "border-slate-300 dark:border-slate-600"}`}>
        <span className="font-medium">Drop any number of PDF or Word contracts here</span>
        <span className="text-xs text-slate-500">or click to choose · scans are read by OCR · up to 15 MB each · they go into the inbox and are read at once</span>
      </div>
      <input ref={input} type="file" multiple accept=".pdf,.docx,.md,.txt,.html,.htm" className="hidden" onChange={(e) => { add(e.target.files); e.target.value = ""; }} />
      {files.length > 0 && (
        <div className="mt-3 space-y-2">
          <p className="text-sm"><b>{files.length}</b> file{files.length === 1 ? "" : "s"}: {files.slice(0, 6).map((f) => f.name).join(", ")}{files.length > 6 ? ` and ${files.length - 6} more` : ""} <button className="ml-2 text-xs text-slate-500 hover:underline" onClick={() => setFiles([])}>clear</button></p>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Treat as"><select className={inputCls} aria-label="Document kind" value={opt.status} onChange={(e) => setOpt({ ...opt, status: e.target.value })}><option value="active">Executed contracts</option><option value="draft">Vendor drafts (redline queue)</option></select></Field>
            <Field label="Category (optional)"><input className={inputCls} value={opt.category} onChange={(e) => setOpt({ ...opt, category: e.target.value })} placeholder="read from each document" /></Field>
            <Field label="Owner (optional)"><input className={inputCls} value={opt.owner} onChange={(e) => setOpt({ ...opt, owner: e.target.value })} /></Field>
          </div>
          <Btn onClick={() => send.mutate()} disabled={send.isPending}>{send.isPending ? "Sending…" : `Add ${files.length} and read now`}</Btn>
        </div>)}
      {send.data && <p className="mt-2 text-sm text-emerald-700 dark:text-emerald-400">✓ {send.data.saved.length} in the inbox; follow them in the live run above.</p>}
      {send.error && <p className="mt-2 text-sm text-red-600">{String(send.error)}</p>}
    </Card>
  );
}

function SampleFolder() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["pipeline-samples"], queryFn: () => api<{ files: { name: string; what: string }[]; loaded: number }>("/api/admin/pipeline/samples") });
  const load = useMutation({ mutationFn: () => api("/api/admin/pipeline/samples", { method: "POST" }), onSuccess: () => setTimeout(() => qc.invalidateQueries(), 800) });
  const remove = useMutation({ mutationFn: () => api("/api/admin/pipeline/samples", { method: "DELETE" }), onSuccess: () => qc.invalidateQueries() });
  if (!q.data?.files.length) return null;
  return (
    <Card title="Demo sample folder" right={<span className="rounded-full bg-violet-100 px-2 py-0.5 text-xs font-semibold text-violet-900 dark:bg-violet-950 dark:text-violet-200">Demo</span>}>
      <p className="text-sm text-slate-500">{q.data.files.length} fictional US hotel supplier documents: a cleaning contractor's NDA, master agreement, two schedules and a scanned amendment; food, HVAC, revenue-management software, valet and waste contracts; and an exact copy of one of them.
        {q.data.loaded ? ` ${q.data.loaded} are in the portfolio.` : ""}</p>
      <details className="mt-1 text-xs text-slate-500"><summary className="cursor-pointer">The files</summary><ul className="mt-1 list-disc pl-5">{q.data.files.map((f) => <li key={f.name}><b>{f.name}</b>: {f.what}</li>)}</ul></details>
      <div className="mt-3 flex flex-wrap gap-2">
        <Btn onClick={() => load.mutate()} disabled={load.isPending}>{q.data.loaded ? "Put the folder in the inbox again" : "Put the folder in the inbox and read it"}</Btn>
        {q.data.loaded > 0 && <Btn kind="ghost" onClick={() => { if (window.confirm("Remove the sample folder and everything read from it?")) remove.mutate(); }} disabled={remove.isPending}>Remove it</Btn>}
      </div>
    </Card>
  );
}

export default function Pipeline() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["pipeline"], queryFn: () => api<Cfg>("/api/admin/pipeline"), refetchInterval: 4000 });
  const srcs = useQuery({ queryKey: ["pipeline-sources"], queryFn: () => api<{ connectors: { id: number; name: string; type_label: string; files: number; enabled: boolean }[] }>("/api/connectors") });
  const meta = useQuery({ queryKey: ["meta"], queryFn: () => api<{ simulators?: boolean }>("/api/meta") });
  const pls = useQuery({ queryKey: ["pipelines"], queryFn: () => api<{ pipelines: Pl[]; running: boolean }>("/api/admin/pipelines"), refetchInterval: 4000 });
  const runs = useQuery({ queryKey: ["runs"], queryFn: () => api<Run[]>("/api/admin/pipeline/runs"), refetchInterval: 4000 });
  const [open, setOpen] = useState<number | null>(null);
  const events = useQuery({ queryKey: ["events", open], enabled: open !== null, queryFn: () => api<Ev[]>(`/api/admin/pipeline/runs/${open}/events`) });
  const who = useQuery({ queryKey: ["meta"], queryFn: () => api<{ customer?: string }>("/api/meta") });
  const [doc, setDoc] = useState({ filename: "new-nda.md", content: "", category: "", owner: "", status: "active" });
  useEffect(() => { if (who.data && !doc.content) setDoc((d) => ({ ...d, content: SAMPLE(who.data!.customer ?? "Our Company") })); }, [who.data, doc.content]);      // the sample names this installation's own company
  const refresh = () => { qc.invalidateQueries(); };
  const upload = useMutation({ mutationFn: () => api<{ run: { new_docs?: number; updated?: number } }>("/api/admin/pipeline/upload", { method: "POST", body: JSON.stringify(doc) }), onSuccess: refresh });
  if (!q.data) return <Loading q={q} />;
  return (
    <div className="space-y-4">
      <LiveRun />
      <div className="grid items-start gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-1" aria-label="Pipelines">
          {pls.data?.pipelines.map((pl) => <PipelineCard key={pl.key} pl={pl} running={pls.data!.running} />)}
          <p className="text-xs text-slate-500">Inbox folder: <span className="break-all font-mono">{q.data.inbox}</span> · {q.data.inbox_files} files · {(q.data.documents.active ?? 0)} executed · {(q.data.documents.draft ?? 0)} draft</p>
        </div>

        <div className="space-y-4 lg:col-span-2">{/* sources and the paste-a-document box share the right-hand column */}
        <Card title="Sources">
          {!srcs.data && <p className="text-sm text-slate-500">Loading…</p>}
          {srcs.data && srcs.data.connectors.length === 0 && <p className="text-sm text-slate-500">No external sources yet. Add one under <Link className="text-indigo-600 hover:underline" to="/admin/connectors">Connectors</Link>.</p>}
          <ul className="divide-y divide-slate-100 dark:divide-slate-700">
            {srcs.data?.connectors.map((c) => (
              <li key={c.id} className="flex items-center justify-between gap-3 py-2 text-sm">
                <div><span className="font-medium">{c.name}</span> <span className="text-slate-500">· {c.type_label} · {c.files} file{c.files === 1 ? "" : "s"} synced{c.enabled ? "" : " · paused"}</span></div>
                {meta.data?.simulators && <span className="rounded-full bg-violet-100 px-2 py-0.5 text-xs font-semibold text-violet-900 dark:bg-violet-950 dark:text-violet-200">Simulated</span>}
              </li>))}
          </ul>
          <p className="mt-2 text-xs text-slate-500">{meta.data?.simulators ? "Violet “Simulated” badges mark stand-ins that speak the real APIs; in production each is replaced by the customer’s own tenant. " : ""}Manage sources in <Link className="text-indigo-600 hover:underline" to="/admin/connectors">Connectors</Link>.</p>
        </Card>

        <AddFiles />
        {meta.data?.simulators && <SampleFolder />}
        <details className="rounded-xl border border-line bg-white p-5 dark:border-slate-700 dark:bg-slate-800">
          <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wider text-ink-mute dark:text-slate-400">Paste a document as text</summary>
          <p className="mb-2 mt-3 text-sm text-slate-500">Anything placed in the inbox folder is picked up on the next run. Paste a document here to drop it in and process it immediately (Markdown or plain text; vendor, type and parent are read from the document).</p>
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
        </details>
        </div>
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
                      {events.data?.map((e) => (
                        <li key={e.id} className="flex flex-wrap gap-2"><span className={`w-16 shrink-0 font-semibold uppercase ${e.action === "failed" ? "text-red-600" : e.action === "new" ? "text-emerald-700" : e.action === "unchanged" ? "text-slate-400" : "text-sky-700"}`}>{e.action === "unchanged" ? "skipped" : e.action}</span>
                          <span className="font-mono text-slate-500">{e.path}</span>
                          {e.content_hash && <span className="font-mono text-slate-400" title={`sha256 ${e.content_hash}`}>#{e.content_hash.slice(0, 10)}</span>}
                          <span>{e.contract_id && e.action !== "unchanged" ? <Link className="text-indigo-600 hover:underline" to={`/contracts/${e.contract_id}`}>{e.detail}</Link> : e.detail}</span>{e.reason && e.action !== "unchanged" && <span className="text-slate-400">· {e.reason}</span>}</li>))}
                      </ul></td></tr>)}
              </Fragment>))}
          </tbody></table>
      </Card>
    </div>
  );
}
