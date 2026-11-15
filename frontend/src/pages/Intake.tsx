import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ReactNode, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { API, api, authUrl, fmtDate, getToken, usd } from "../lib";
import { Btn } from "../forms";
import { Card, ConfidenceBadge, Sev, SeverityChip } from "../ui";

type Sample = { file: string; what: string; group: string; category: string | null; property: string | null; format: string; size: number; contract_id: number | null };
type FolderFile = { name: string; file: string; what: string; format: string; size: number; duplicate: boolean };
type Field = { field: string; label: string; value: string | null; page: number | null; confidence: number | null };
type Doc = {
  name: string; status: "queued" | "running" | "done" | "error"; error?: string; contract_id?: number; started?: number; finished?: number;
  action?: string; reason?: string; title?: string; type?: string; vendor?: string; parent?: string | null; parent_id?: number | null; overrides?: string[];
  read?: { pages: number; paged: boolean; words: number; format: string; scanned: boolean; seconds: number };
  structure?: { clauses: number; types: [string, number][]; other: number; title: string; vendor: string; type: string; property: string | null; category: string };
  extract?: { engine: string; seconds: number; vendor: string; fields: Field[] };
  index?: { vectors: number; dims: number; model: string; seconds: number };
  check?: { checks: number; failed: { name: string; severity: Sev; actual: string | null }[]; failed_count: number; deviations: number; obligations: number; act_by: string | null; auto_renew: boolean };
};
type Summary = { contracts: number; annual: number; uncapped: number; personal: number; serious_failures: number; clauses: number; portfolio_total: number; processed?: number; files?: number;
  deadlines: { contract_id: number; title: string; vendor: string; notice_deadline: string | null; expiry_date: string | null; days_to_notice: number | null }[] };
type Detail = { clauses: { id: number; clause_type: string; heading: string; text: string; page: number }[]; fields: { field: string; value: string | null; source_clause_id: number | null }[] };

const STEPS = [
  ["read", "Read", "Text and page numbers from the PDF or Word file (scans go through OCR)"],
  ["structure", "Structure", "Split into clauses and recognise each one: renewal, liability, payment, insurance…"],
  ["extract", "Extract", "The terms that matter, each tied to the clause and page it was read from, with a confidence"],
  ["index", "Index", "Every clause turned into a vector, so it can be found by meaning, not just keywords"],
  ["check", "Check", "Compared with your standards: missing clauses, risky terms, deadlines to act on"],
] as const;
type StepKey = (typeof STEPS)[number][0];

const human = (k: string) => k.replace(/_/g, " ").replace(/\b(sla|dpa|ip|pci)\b/g, (m) => m.toUpperCase());
const shortVendor = (v?: string) => (v ?? "").replace(/,? (Inc|LLC|Co|Corp)\.?$/, "");
const OVERRIDE_LABEL: Record<string, string> = { expiry_date: "end date", payment_terms_days: "payment terms", notice_period_days: "notice period", auto_renew: "renewal", annual_value: "annual value", total_value: "total value" };
function fmtValue(f: { field: string; value: string | null }): string {
  if (f.value === null || f.value === "") return f.field === "liability_cap_multiple" ? "No cap stated (uncapped)" : "—";
  if (f.value === "True") return "Yes";
  if (f.value === "False") return "No";
  if (/date$/.test(f.field)) return fmtDate(f.value);
  if (/value$/.test(f.field)) return usd(f.value);
  if (f.field === "liability_cap_multiple") return `${Number(f.value)}× annual fees`;
  return f.value;
}

/** The ways a value can be written in a contract, so the passage it came from can be marked. */
function variants(field: string, value: string | null): string[] {
  if (!value || value === "True" || value === "False") return [];
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const d = new Date(value + "T00:00:00"), m = d.toLocaleDateString("en-US", { month: "long" }), day = d.getDate(), y = d.getFullYear();
    return [`${m} ${day}, ${y}`, `${day} ${m} ${y}`, `${m.slice(0, 3)} ${day}, ${y}`, `${d.getMonth() + 1}/${day}/${y}`];
  }
  if (/^-?\d+(\.\d+)?$/.test(value)) {
    const n = Number(value);
    if (field === "liability_cap_multiple") return n === 1 ? ["twelve (12) months", "12 months", "Annual Contract Price"] : [`(${n}) times`, `${n} times`, `${n}x`];
    return [n.toLocaleString("en-US"), String(n)].filter((x, i, a) => a.indexOf(x) === i);
  }
  return [value];
}
const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
function marked(text: string, vs: string[]): ReactNode {
  if (!vs.length) return text;
  const parts = text.split(new RegExp(`(${vs.map(esc).join("|")})`, "g"));
  return parts.map((p, i) => (i % 2 ? <mark key={i} className="rounded bg-amber-200 px-0.5 text-ink dark:bg-amber-600 dark:text-white">{p}</mark> : p));
}

/** POST /api/intake and follow the newline-delimited events it streams back. */
function useIntake() {
  const qc = useQueryClient();
  const [docs, setDocs] = useState<Doc[]>([]);
  const [engine, setEngine] = useState<string | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [t, setT] = useState<{ start: number; end?: number } | null>(null);
  async function run(body: object) {
    setBusy(true); setErr(null); setSummary(null); setEngine(null); setDocs([]); setT({ start: Date.now() });
    try {
      const tok = getToken();
      const r = await fetch(`${API}/api/intake`, { method: "POST", headers: { "Content-Type": "application/json", ...(tok ? { Authorization: `Bearer ${tok}` } : {}) }, body: JSON.stringify(body) });
      if (!r.ok || !r.body) { const tx = await r.text(); let m = tx; try { m = JSON.parse(tx).detail ?? tx; } catch { /* text */ } throw new Error(m || String(r.status)); }
      const reader = r.body.getReader(), dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let nl;
        while ((nl = buf.indexOf("\n")) >= 0) {
          const line = buf.slice(0, nl); buf = buf.slice(nl + 1);
          if (!line.trim()) continue;
          const e = JSON.parse(line);
          if (e.step === "engine") { setEngine(e.engine); setDocs(e.documents.map((n: string) => ({ name: n, status: "queued" }))); continue; }
          if (e.step === "summary") { setSummary(e); continue; }
          if (e.step === "error" && !e.doc) { setErr(e.message); continue; }
          setDocs((ds) => ds.map((d) => {
            if (d.name !== e.doc || e.step === "queued") return d;
            if (e.step === "start") return { ...d, status: "running", started: Date.now() };
            if (e.step === "done") return { ...d, ...e, status: "done", finished: Date.now(), started: d.started ?? Date.now() };
            if (e.step === "error") return { ...d, status: "error", error: e.message, finished: Date.now() };
            return { ...d, status: "running", [e.step]: e };
          }));
        }
      }
      qc.invalidateQueries();
    } catch (e) {
      setErr(String(e instanceof Error ? e.message : e));
    } finally { setBusy(false); setT((x) => (x ? { ...x, end: Date.now() } : x)); }
  }
  return { docs, engine, summary, busy, err, t, run, clear: () => { setDocs([]); setSummary(null); setT(null); } };
}

function useElapsed(t: { start: number; end?: number } | null, busy: boolean): number {
  const [now, setNow] = useState(Date.now());
  useEffect(() => { if (!busy) return; const h = setInterval(() => setNow(Date.now()), 250); return () => clearInterval(h); }, [busy]);
  return t ? ((t.end ?? now) - t.start) / 1000 : 0;
}
const mmss = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

function StepRail({ d }: { d: Doc }) {
  const done = (k: StepKey) => Boolean(d[k]);
  const current = d.status === "running" ? STEPS.find(([k]) => !done(k))?.[0] : undefined;
  const line = (k: StepKey): string => {
    if (k === "read" && d.read) return `${d.read.paged ? `${d.read.pages} page${d.read.pages === 1 ? "" : "s"}` : `${d.read.format}, no fixed pages`} · ${d.read.words.toLocaleString()} words${d.read.scanned ? " · scanned, read by OCR" : ""}`;
    if (k === "structure" && d.structure) return `${d.structure.clauses} clauses · ${d.structure.types.length} kinds recognised`;
    if (k === "extract" && d.extract) return `${d.extract.fields.filter((f) => f.value !== null).length} terms · ${d.extract.engine}`;
    if (k === "index" && d.index) return `${d.index.vectors} vectors × ${d.index.dims} dimensions`;
    if (k === "check" && d.check) return `${d.check.checks} checks · ${d.check.failed_count} to look at`;
    return k === current ? "working…" : "";
  };
  return (
    <ol className="grid grid-cols-2 gap-1.5 sm:grid-cols-5" aria-label="Steps">
      {STEPS.map(([k, label], i) => {
        const state = done(k) ? "done" : k === current ? "now" : "wait";
        return (
          <li key={k} className={`rounded-lg border px-2 py-1.5 text-xs transition-colors ${state === "done" ? "border-emerald-300 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/40" : state === "now" ? "border-indigo-400 bg-indigo-50 dark:border-indigo-500 dark:bg-indigo-950/40" : "border-line bg-white dark:border-slate-700 dark:bg-slate-800"}`}>
            <div className="flex items-center gap-1 font-semibold">
              <span aria-hidden className={state === "now" ? "animate-pulse" : ""}>{state === "done" ? "✓" : state === "now" ? "●" : i + 1}</span>{label}
              <span className="sr-only">{state === "done" ? " done" : state === "now" ? " in progress" : " waiting"}</span>
            </div>
            <div className="mt-0.5 min-h-[1rem] text-ink-mute dark:text-slate-400">{line(k)}</div>
          </li>
        );
      })}
    </ol>
  );
}

/** One document, opened up: its clauses as read (left) and the terms taken from them (right); a term shows the words it came from. */
function DeepView({ d }: { d: Doc }) {
  const q = useQuery({ queryKey: ["contract", d.contract_id], queryFn: () => api<Detail>(`/api/contracts/${d.contract_id}`), enabled: Boolean(d.contract_id) });
  const [sel, setSel] = useState<string | null>(null);
  const refs = useRef<Record<number, HTMLElement | null>>({});
  const src = Object.fromEntries((q.data?.fields ?? []).map((f) => [f.field, f.source_clause_id]));
  const selField = d.extract?.fields.find((f) => f.field === sel);
  // the clause the term was read from; when the rule did not record one (or it does not hold the value), the first clause that states the value
  const vs = selField ? variants(selField.field, selField.value) : [];
  const holds = (id: number | null | undefined) => Boolean(id && vs.length && q.data?.clauses.find((c) => c.id === id && vs.some((v) => c.text.replace(/\*\*/g, "").includes(v))));
  const selClause = !sel ? null : holds(src[sel]) || !vs.length ? src[sel] : (q.data?.clauses.find((c) => vs.some((v) => c.text.replace(/\*\*/g, "").includes(v)))?.id ?? src[sel]);
  useEffect(() => { if (selClause) refs.current[selClause]?.scrollIntoView({ behavior: "smooth", block: "center" }); }, [selClause, sel]);
  const paged = d.read?.paged !== false;
  return (
    <div className="grid gap-4 lg:grid-cols-[1.3fr_1fr]">
      <Card title={`The document as read · ${q.data?.clauses.length ?? d.structure?.clauses ?? 0} clauses`}
        right={d.contract_id && <Link className="text-sm font-medium text-indigo-700 hover:underline dark:text-indigo-300" to={`/contracts/${d.contract_id}`}>Full contract page →</Link>}>
        <div className="max-h-[34rem] space-y-2 overflow-y-auto pr-1">
          {q.data?.clauses.map((c) => {
            const on = c.id === selClause;
            return (
              <section key={c.id} ref={(el) => { refs.current[c.id] = el; }}
                className={`rounded-lg border p-2.5 text-sm transition-colors ${on ? "border-amber-400 bg-amber-50 dark:border-amber-500 dark:bg-amber-950/40" : "border-slate-200 dark:border-slate-700"}`}>
                <div className="mb-1 flex flex-wrap items-center gap-2">
                  <span className="font-medium">{c.heading}</span>
                  {c.clause_type !== "other" && <span className="rounded bg-indigo-50 px-1.5 py-0.5 text-[11px] font-medium text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200">{human(c.clause_type)}</span>}
                  {paged && <span className="text-[11px] text-ink-mute">p.{c.page}</span>}
                </div>
                <p className="whitespace-pre-line text-ink-soft dark:text-slate-300">{marked(c.text.replace(/\*\*/g, "").slice(0, on ? 4000 : 420) + (!on && c.text.length > 420 ? "…" : ""), on && selField ? variants(selField.field, selField.value) : [])}</p>
              </section>);
          })}
          {!q.data && <p className="text-sm text-ink-mute">Loading the clauses…</p>}
        </div>
      </Card>
      <div className="space-y-4">
        <Card title={`Terms extracted · ${d.extract?.engine ?? ""}`} right={<span className="text-xs text-ink-mute">click a term to see where it came from</span>}>
          <table className="w-full text-sm">
            <tbody>
              {d.extract?.fields.map((f) => (
                <tr key={f.field} onClick={() => setSel(f.field)} className={`cursor-pointer border-t border-slate-100 dark:border-slate-700 ${sel === f.field ? "bg-amber-50 dark:bg-amber-950/40" : "hover:bg-slate-50 dark:hover:bg-slate-700/40"}`}>
                  <td className="py-1 pr-2 text-ink-mute dark:text-slate-400">{f.label}</td>
                  <td className="py-1 pr-2 font-medium tabular-nums">{fmtValue(f)}</td>
                  <td className="py-1 pr-1 text-xs text-ink-mute">{f.value !== null && f.page && paged ? `p.${f.page}` : ""}</td>
                  <td className="py-1 text-right">{f.value !== null && <ConfidenceBadge v={f.confidence} />}</td>
                </tr>))}
            </tbody>
          </table>
        </Card>
        {d.check && (
          <Card title="Checked against your standards">
            {d.check.act_by && <p className="mb-2 text-sm"><span className="text-ink-mute">{d.check.auto_renew ? "Last day to stop renewal" : "Ends"}:</span> <b>{fmtDate(d.check.act_by)}</b></p>}
            <ul className="space-y-1">{d.check.failed.slice(0, 6).map((f) => <li key={f.name} className="flex items-start justify-between gap-2 text-sm"><span>{f.name}</span><SeverityChip sev={f.severity} /></li>)}</ul>
            <p className="mt-2 text-xs text-ink-mute dark:text-slate-400">{d.check.checks} checks · {d.check.obligations} obligations created · {d.check.deviations} redline items · {d.index?.vectors} clause vectors indexed</p>
          </Card>)}
      </div>
    </div>
  );
}

function OneDocument({ samples }: { samples: Sample[] }) {
  const s = useIntake();
  const [pick, setPick] = useState("prairie_waste_services.pdf");
  const [file, setFile] = useState<File | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const d = s.docs[0];
  const toB64 = (f: File) => new Promise<string>((res, rej) => { const r = new FileReader(); r.onload = () => res(String(r.result).split(",")[1] ?? ""); r.onerror = rej; r.readAsDataURL(f); });
  const go = async () => s.run(file ? { files: [{ filename: file.name, content_b64: await toB64(file) }] } : { samples: [pick] });
  const chosen = samples.find((x) => x.file === pick);
  return (
    <div className="space-y-4">
      <Card title="Pick one document">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex min-w-[18rem] flex-1 flex-col gap-1 text-sm">
            <span className="font-medium">Sample contract</span>
            <select className="rounded border border-slate-300 bg-white px-2 py-1.5 dark:border-slate-600 dark:bg-slate-800" value={pick} disabled={s.busy || Boolean(file)} onChange={(e) => setPick(e.target.value)}>
              {samples.map((x) => <option key={x.file} value={x.file}>{x.what} ({x.format})</option>)}
            </select>
          </label>
          {chosen && !file && <a className="pb-1.5 text-sm text-indigo-700 hover:underline dark:text-indigo-300" href={authUrl(`/api/intake/samples/${encodeURIComponent(chosen.file)}`)} target="_blank" rel="noreferrer">Open original</a>}
          <span className="pb-1.5 text-sm text-ink-mute">or</span>
          <Btn kind="ghost" onClick={() => input.current?.click()} disabled={s.busy}>{file ? `Your file: ${file.name}` : "Use your own file…"}</Btn>
          {file && <button className="pb-1.5 text-xs text-ink-mute hover:underline" onClick={() => setFile(null)}>clear</button>}
          <input ref={input} type="file" accept=".pdf,.docx,.md,.txt,.html,.htm" className="hidden" onChange={(e) => { setFile(e.target.files?.[0] ?? null); e.target.value = ""; }} />
          <Btn onClick={go} disabled={s.busy}>{s.busy ? "Reading…" : "Read this document"}</Btn>
        </div>
        {chosen?.contract_id && !file && !s.busy && !d && <p className="mt-2 text-xs text-ink-mute">Already in the portfolio: reading it again replaces its data with a fresh read.</p>}
      </Card>
      {s.err && <p className="text-sm text-red-700 dark:text-red-300">{s.err}</p>}
      {d && (
        <section className="space-y-3">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <div>
              <div className="font-medium">{d.structure?.title ?? d.name}</div>
              <div className="text-xs text-ink-mute dark:text-slate-400">{d.structure ? `${d.structure.vendor} · ${d.structure.type} · ${d.structure.category}${d.structure.property ? " · " + d.structure.property : ""}` : "Reading…"}{s.engine ? ` · engine: ${s.engine}` : ""}</div>
            </div>
            {d.status === "error" && <span className="text-sm text-red-700 dark:text-red-300">Could not be read: {d.error}</span>}
          </div>
          <StepRail d={d} />
          {d.status === "done" && d.contract_id && d.extract && <DeepView d={d} />}
        </section>)}
    </div>
  );
}

function FolderView({ files }: { files: FolderFile[] }) {
  const s = useIntake();
  const elapsed = useElapsed(s.t, s.busy);
  const docs: Doc[] = s.docs.length ? s.docs : files.map((f) => ({ name: f.name.replace(/[^A-Za-z0-9._-]+/g, "_"), status: "queued" }));
  const label = Object.fromEntries(files.map((f) => [f.name.replace(/[^A-Za-z0-9._-]+/g, "_"), f]));
  const sum = (fn: (d: Doc) => number) => s.docs.reduce((a, d) => a + fn(d), 0);
  const finished = s.docs.filter((d) => d.status === "done" || d.status === "error").length;
  const ran = s.docs.length > 0;
  const counters: [string, string][] = [
    ["Documents", `${finished}/${docs.length}`],
    ["Pages read", `${sum((d) => (d.read?.paged ? d.read.pages : 0))}${s.docs.some((d) => d.read && !d.read.paged) ? " + Word" : ""}`],
    ["Clauses indexed", `${sum((d) => d.index?.vectors ?? 0)}`],
    ["Terms extracted", `${sum((d) => d.extract?.fields.filter((f) => f.value !== null).length ?? 0)}`],
    ["Linked to a parent", `${s.docs.filter((d) => d.parent && d.action !== "unchanged" && d.action !== "duplicate").length}`],
    ["Duplicates caught", `${s.docs.filter((d) => d.action === "duplicate").length}`],
    ["Already read, skipped", `${s.docs.filter((d) => d.action === "unchanged").length}`],
    ["Elapsed", mmss(elapsed)],
  ];
  const status = (d: Doc): ReactNode => {
    if (d.status === "queued") return <span className="text-ink-mute">waiting</span>;
    if (d.status === "running") return <span className="font-medium text-indigo-700 dark:text-indigo-300"><span className="animate-pulse" aria-hidden>● </span>{STEPS.find(([k]) => !d[k])?.[1] ?? "Linking"}…</span>;
    if (d.status === "error") return <span className="font-medium text-red-700 dark:text-red-300">✗ failed</span>;
    if (d.action === "duplicate") return <span className="font-medium text-violet-700 dark:text-violet-300">⧉ duplicate</span>;
    if (d.action === "unchanged") return <span className="text-ink-mute" title={d.reason}>= already read</span>;
    return <span className="font-medium text-emerald-700 dark:text-emerald-300">✓ {d.action === "updated" ? "updated" : "new"}</span>;
  };
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Btn onClick={() => s.run({ folder: true })} disabled={s.busy}>{s.busy ? "Reading the folder…" : ran ? "Read the folder again" : `Read the folder (${files.length} files)`}</Btn>
        {s.engine && <span className="text-sm text-ink-mute dark:text-slate-400">Engine: <b>{s.engine}</b></span>}
        {ran && !s.busy && <span className="text-sm text-ink-mute dark:text-slate-400">Run it again: unchanged files are recognised by size, time and content hash and skipped.</span>}
        {s.err && <span className="text-sm text-red-700 dark:text-red-300">{s.err}</span>}
      </div>
      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-8" aria-live="polite">
        {counters.map(([k, v]) => <div key={k} className="rounded-lg border border-line bg-white p-2.5 dark:border-slate-700 dark:bg-slate-800"><dt className="text-[11px] uppercase tracking-wider text-ink-mute">{k}</dt><dd className="mt-0.5 text-xl font-semibold tabular-nums">{v}</dd></div>)}
      </dl>
      <div className="overflow-x-auto rounded-xl border border-line bg-white dark:border-slate-700 dark:bg-slate-800">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500 dark:bg-slate-900 dark:text-slate-400">
            <tr><th className="px-3 py-2">File</th><th className="px-3 py-2">Status</th><th className="px-3 py-2 text-right">Pages</th><th className="px-3 py-2 text-right">Clauses</th><th className="px-3 py-2 text-right">Terms</th><th className="px-3 py-2">Read as</th><th className="px-3 py-2">Linked</th><th className="px-3 py-2 text-right">Time</th></tr>
          </thead>
          <tbody>
            {docs.map((d) => {
              const f = label[d.name];
              return (
                <tr key={d.name} className={`border-t border-slate-100 dark:border-slate-700 ${d.status === "running" ? "bg-indigo-50/60 dark:bg-indigo-950/30" : ""}`}>
                  <td className="px-3 py-2"><div className="font-medium">{f?.name ?? d.name}</div><div className="text-xs text-ink-mute dark:text-slate-400">{f ? `${f.format} · ${Math.round(f.size / 1024)} KB` : ""}{d.read?.scanned ? " · scan, OCR" : ""}</div></td>
                  <td className="whitespace-nowrap px-3 py-2">{status(d)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{d.read ? (d.read.paged ? d.read.pages : "Word") : ""}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{d.structure?.clauses ?? ""}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{d.extract ? d.extract.fields.filter((x) => x.value !== null).length : ""}</td>
                  <td className="px-3 py-2">{d.type || d.structure ? <><span className="font-medium">{d.type ?? d.structure?.type}</span> · {shortVendor(d.vendor ?? d.structure?.vendor)}</> : ""}
                    {d.action === "duplicate" && <div className="text-xs text-ink-mute">same bytes as an earlier file: not stored twice</div>}</td>
                  <td className="px-3 py-2 text-xs">{d.parent ? <>under <Link className="text-indigo-700 hover:underline dark:text-indigo-300" to={`/contracts/${d.parent_id ?? d.contract_id}`}>{d.parent.replace(/ – .*$/, "")}</Link>{d.overrides?.length ? <div>changes its {d.overrides.map((o) => OVERRIDE_LABEL[o] ?? human(o)).join(" and ")}</div> : null}</> : ""}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-ink-mute">{d.started && d.finished ? `${((d.finished - d.started) / 1000).toFixed(1)}s` : ""}</td>
                </tr>);
            })}
          </tbody>
        </table>
      </div>
      {s.summary && (s.summary.processed ?? 0) > 0 && <SummaryCard s={s.summary} docs={s.docs} />}
      {s.summary && (s.summary.processed ?? 0) === 0 && <Card title="Nothing new"><p className="text-sm">All {s.summary.files} files were seen before: nothing to read again, nothing stored twice. Finished in {elapsed.toFixed(1)} seconds.</p></Card>}
    </div>
  );
}

function SummaryCard({ s, docs }: { s: Summary; docs: Doc[] }) {
  const id = (v: string) => docs.find((d) => (d.structure?.vendor ?? d.vendor ?? "").startsWith(v))?.contract_id;
  const scoped = [["Prairie", "What happens if we end this contract early?"], ["Adirondack", "How fast must they respond to an emergency?"], ["Keystone", "Who pays if a guest's car is damaged?"]]
    .map(([v, q]) => ({ v, q, cid: id(v) })).filter((x) => x.cid);
  const portfolio = ["Which auto-renewing contracts have already passed their notice deadline?", "Which contracts have a notice deadline in the next 30 days?", "Which vendors have uncapped liability?", "Who are the top 5 vendors by annual value?"];
  const tile = (label: string, value: string, to?: string) => (
    <div className="rounded-lg border border-line p-3 dark:border-slate-700">
      <div className="text-xs uppercase tracking-wider text-ink-mute">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{to ? <Link className="hover:underline" to={to}>{value}</Link> : value}</div>
    </div>);
  return (
    <Card title="Now part of the portfolio">
      <div className="grid grid-cols-2 gap-2 md:grid-cols-6">
        {tile("Contracts added", `${s.contracts}`, "/contracts")}
        {tile("Annual value", usd(s.annual))}
        {tile("Clauses indexed", `${s.clauses}`, "/clauses")}
        {tile("No liability cap", `${s.uncapped}`)}
        {tile("Guest personal data", `${s.personal}`)}
        {tile("Serious check failures", `${s.serious_failures}`, "/redline")}
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <div>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-ink-mute">Act on next</h3>
          <ul className="space-y-1 text-sm">
            {s.deadlines.slice(0, 7).map((d) => (
              <li key={d.contract_id} className="flex justify-between gap-2">
                <Link className="truncate hover:underline" to={`/contracts/${d.contract_id}`}>{shortVendor(d.vendor)}</Link>
                <span className={`shrink-0 tabular-nums ${d.days_to_notice !== null && d.days_to_notice < 0 ? "font-semibold text-red-700 dark:text-red-300" : d.days_to_notice !== null && d.days_to_notice <= 30 ? "font-semibold text-orange-700 dark:text-orange-300" : "text-ink-mute"}`}>
                  {d.days_to_notice === null ? "" : d.days_to_notice < 0 ? `passed ${-d.days_to_notice}d ago` : `${fmtDate(d.notice_deadline)} · ${d.days_to_notice}d`}
                </span>
              </li>))}
          </ul>
          <Link className="mt-2 inline-block text-sm font-medium text-indigo-700 hover:underline dark:text-indigo-300" to="/renewals">See them on Renewals →</Link>
        </div>
        <div>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-ink-mute">Ask the whole portfolio ({s.portfolio_total} contracts)</h3>
          <ul className="space-y-1 text-sm">{portfolio.map((q) => <li key={q}><Link className="text-indigo-700 hover:underline dark:text-indigo-300" to={`/ask?q=${encodeURIComponent(q)}`}>{q}</Link></li>)}</ul>
        </div>
        <div>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-ink-mute">Ask one contract (answers cite the clause)</h3>
          <ul className="space-y-1 text-sm">{scoped.map((x) => <li key={x.q}><Link className="text-indigo-700 hover:underline dark:text-indigo-300" to={`/ask?doc=${x.cid}&q=${encodeURIComponent(x.q)}`}>{x.v}: {x.q}</Link></li>)}</ul>
        </div>
      </div>
    </Card>
  );
}

/** Add contracts: one document opened up step by step, then a folder read at scale. The first part of the demo (see DEMO.md). */
export default function Intake() {
  const qc = useQueryClient();
  const samples = useQuery({ queryKey: ["intake-samples"], queryFn: () => api<Sample[]>("/api/intake/samples") });
  const folder = useQuery({ queryKey: ["intake-folder"], queryFn: () => api<FolderFile[]>("/api/intake/folder") });
  const [tab, setTab] = useState<"one" | "folder">(() => { try { return localStorage.getItem("intake_tab") === "folder" ? "folder" : "one"; } catch { return "one"; } });
  const [gen, setGen] = useState(0);
  const pickTab = (t: "one" | "folder") => { setTab(t); try { localStorage.setItem("intake_tab", t); } catch { /* private mode */ } };
  const loaded = (samples.data ?? []).filter((x) => x.contract_id).length;
  async function reset() {
    if (!window.confirm("Remove every contract added on this screen (samples, the folder and any uploads), so the demo can start again?")) return;
    await api("/api/intake", { method: "DELETE" });
    setGen((g) => g + 1);
    qc.invalidateQueries();
  }
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-serif text-3xl md:text-4xl">Add contracts</h1>
          <div className="max-w-3xl text-sm text-ink-mute dark:text-slate-400">Signed contracts in, data out. Each document is read, split into clauses, its terms extracted with the clause and page they come from,
            indexed for search by meaning, and checked against your standards.</div>
        </div>
        <div className="flex items-center gap-3">
          {loaded > 0 && <span className="text-xs text-ink-mute">{loaded} sample{loaded === 1 ? "" : "s"} in the portfolio</span>}
          <Btn kind="ghost" onClick={reset}>Reset demo</Btn>
        </div>
      </div>
      <ol className="grid gap-2 md:grid-cols-5" aria-label="What happens to each document">
        {STEPS.map(([k, label, what], i) => (
          <li key={k} className="rounded-xl border border-line bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
            <div className="text-xs font-semibold uppercase tracking-wider text-indigo-700 dark:text-indigo-300">{i + 1} · {label}</div>
            <div className="mt-1 text-sm text-ink-mute dark:text-slate-300">{what}</div>
          </li>))}
      </ol>
      <div role="tablist" aria-label="How many documents" className="inline-flex rounded-lg border border-line bg-white p-1 dark:border-slate-700 dark:bg-slate-800">
        {([["one", "One document"], ["folder", "A folder of documents"]] as const).map(([k, l]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => pickTab(k)}
            className={`rounded-md px-4 py-1.5 text-sm font-medium ${tab === k ? "bg-ink text-white dark:bg-slate-200 dark:text-ink" : "text-ink-mute hover:text-ink dark:text-slate-300"}`}>{l}</button>))}
      </div>
      {tab === "one" && samples.data && <OneDocument key={`one${gen}`} samples={samples.data} />}
      {tab === "folder" && folder.data && <FolderView key={`folder${gen}`} files={folder.data} />}
    </div>
  );
}
