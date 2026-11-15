import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { API, api, authUrl, fmtDate, getToken, usd } from "../lib";
import { Btn } from "../forms";
import { Card, ConfidenceBadge, Sev, SeverityChip } from "../ui";

type Sample = { file: string; what: string; category: string | null; property: string | null; format: string; size: number; contract_id: number | null };
type Field = { field: string; label: string; value: string | null; page: number | null; confidence: number | null };
type Doc = {
  name: string; status: "queued" | "running" | "done" | "error"; error?: string; contract_id?: number;
  read?: { pages: number; paged: boolean; words: number; format: string; scanned: boolean; seconds: number };
  structure?: { clauses: number; types: [string, number][]; other: number; title: string; vendor: string; type: string; property: string | null; category: string };
  extract?: { engine: string; seconds: number; vendor: string; fields: Field[] };
  index?: { vectors: number; dims: number; model: string; seconds: number };
  check?: { checks: number; failed: { name: string; severity: Sev; actual: string | null }[]; failed_count: number; deviations: number; obligations: number; act_by: string | null; auto_renew: boolean };
};
type Summary = { contracts: number; annual: number; uncapped: number; personal: number; auto_renew: number; no_exit: number; vendors: number; serious_failures: number; clauses: number; portfolio_total: number;
  deadlines: { contract_id: number; title: string; vendor: string; notice_deadline: string | null; expiry_date: string | null; days_to_notice: number | null }[] };

const STEPS = [
  ["read", "Read", "Text and page numbers from the PDF or Word file (scans go through OCR)"],
  ["structure", "Structure", "Split into clauses and recognise each one: renewal, liability, payment, insurance…"],
  ["extract", "Extract", "The terms that matter, each tied to the page it was read from, with a confidence"],
  ["index", "Index", "Every clause turned into a vector, so it can be found by meaning, not just keywords"],
  ["check", "Check", "Compared with your standards: missing clauses, risky terms, deadlines to act on"],
] as const;
type StepKey = (typeof STEPS)[number][0];

const human = (k: string) => k.replace(/_/g, " ").replace(/\b(sla|dpa|ip|pci)\b/g, (m) => m.toUpperCase());
function fmtValue(f: Field): string {
  if (f.value === null || f.value === "") {
    if (f.field === "liability_cap_multiple") return "No cap stated (uncapped)";
    return "—";
  }
  if (f.value === "True") return "Yes";
  if (f.value === "False") return "No";
  if (/date$/.test(f.field)) return fmtDate(f.value);
  if (/value$/.test(f.field)) return usd(f.value);
  if (f.field === "liability_cap_multiple") return `${Number(f.value)}× annual fees`;
  return f.value;
}

function StepRail({ d }: { d: Doc }) {
  const done = (k: StepKey) => Boolean(d[k]);
  const current = d.status === "running" ? STEPS.find(([k]) => !done(k))?.[0] : undefined;
  const line = (k: StepKey): string => {
    if (k === "read" && d.read) return `${d.read.paged ? `${d.read.pages} page${d.read.pages === 1 ? "" : "s"}` : `${d.read.format}, no fixed pages`} · ${d.read.words.toLocaleString()} words${d.read.scanned ? " · OCR" : ""}`;
    if (k === "structure" && d.structure) return `${d.structure.clauses} clauses · ${d.structure.types.length} kinds recognised`;
    if (k === "extract" && d.extract) return `${d.extract.fields.filter((f) => f.value !== null).length} terms · ${d.extract.engine}`;
    if (k === "index" && d.index) return `${d.index.vectors} vectors × ${d.index.dims}`;
    if (k === "check" && d.check) return `${d.check.checks} checks · ${d.check.failed_count} to look at`;
    return k === current ? "working…" : "";
  };
  return (
    <ol className="grid grid-cols-5 gap-1.5" aria-label="Steps">
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

function DocCard({ d }: { d: Doc }) {
  const s = d.structure;
  return (
    <section className="rounded-xl border border-line bg-white p-4 dark:border-slate-700 dark:bg-slate-800" aria-live="polite">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <div className="font-medium">{s?.title ?? d.name}</div>
          <div className="text-xs text-ink-mute dark:text-slate-400">{s ? `${s.vendor} · ${s.type} · ${s.category}${s.property ? " · " + s.property : " · all properties"}` : d.name}</div>
        </div>
        {d.status === "done" && d.contract_id && <Link className="text-sm font-medium text-indigo-700 hover:underline dark:text-indigo-300" to={`/contracts/${d.contract_id}`}>Open with sources →</Link>}
        {d.status === "error" && <span className="text-sm text-red-700 dark:text-red-300">Could not be read: {d.error}</span>}
        {d.status === "queued" && <span className="text-sm text-ink-mute">Waiting</span>}
      </div>
      <StepRail d={d} />
      {(s || d.extract || d.check) && (
        <div className="mt-3 grid gap-3 lg:grid-cols-[1fr_1.4fr_1fr]">
          <div>
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-ink-mute">Clauses recognised</h3>
            <div className="flex flex-wrap gap-1">
              {s?.types.map(([k, n]) => <span key={k} className="rounded bg-slate-100 px-1.5 py-0.5 text-xs dark:bg-slate-700">{human(k)}{n > 1 ? ` ×${n}` : ""}</span>)}
              {s && s.other > 0 && <span className="rounded px-1.5 py-0.5 text-xs text-ink-mute">+{s.other} other</span>}
            </div>
            {d.index && <p className="mt-2 text-xs text-ink-mute dark:text-slate-400">Indexed for search: {d.index.vectors} clause vectors ({d.index.model}, {d.index.seconds}s).</p>}
          </div>
          <div>
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-ink-mute">Terms extracted {d.extract && <span className="normal-case tracking-normal">· {d.extract.engine}</span>}</h3>
            {d.extract ? (
              <table className="w-full text-sm">
                <tbody>
                  {d.extract.fields.map((f) => (
                    <tr key={f.field} className="border-t border-slate-100 dark:border-slate-700">
                      <td className="py-0.5 pr-2 text-ink-mute dark:text-slate-400">{f.label}</td>
                      <td className="py-0.5 pr-2 font-medium tabular-nums">{fmtValue(f)}</td>
                      <td className="py-0.5 pr-1 text-xs text-ink-mute">{f.value !== null && f.page && d.read?.paged !== false ? `p.${f.page}` : ""}</td>
                      <td className="py-0.5 text-right">{f.value !== null && <ConfidenceBadge v={f.confidence} />}</td>
                    </tr>))}
                </tbody>
              </table>
            ) : <p className="text-xs text-ink-mute">…</p>}
          </div>
          <div>
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-ink-mute">Checked</h3>
            {d.check ? (
              <>
                {d.check.act_by && <p className="mb-2 text-sm"><span className="text-ink-mute">{d.check.auto_renew ? "Last day to stop renewal" : "Ends"}:</span> <b>{fmtDate(d.check.act_by)}</b></p>}
                <ul className="space-y-1">
                  {d.check.failed.slice(0, 5).map((f) => <li key={f.name} className="flex items-start justify-between gap-2 text-sm"><span>{f.name}</span><SeverityChip sev={f.severity} /></li>)}
                </ul>
                {d.check.failed_count > 5 && <p className="mt-1 text-xs text-ink-mute">+{d.check.failed_count - 5} more</p>}
                <p className="mt-2 text-xs text-ink-mute dark:text-slate-400">{d.check.obligations} obligations created · {d.check.deviations} redline items</p>
              </>
            ) : <p className="text-xs text-ink-mute">…</p>}
          </div>
        </div>
      )}
    </section>
  );
}

function SummaryCard({ s, docs }: { s: Summary; docs: Doc[] }) {
  const id = (v: string) => docs.find((d) => d.structure?.vendor.startsWith(v))?.contract_id;
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
            {s.deadlines.map((d) => (
              <li key={d.contract_id} className="flex justify-between gap-2">
                <Link className="truncate hover:underline" to={`/contracts/${d.contract_id}`}>{d.vendor.replace(/,? (Inc|LLC|Co)\.?$/, "")}</Link>
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

/** Add contracts and watch each one being read, structured, extracted, indexed and checked. The first act of the demo. */
export default function Intake() {
  const qc = useQueryClient();
  const samples = useQuery({ queryKey: ["intake-samples"], queryFn: () => api<Sample[]>("/api/intake/samples") });
  const [picked, setPicked] = useState<string[] | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [engine, setEngine] = useState<string | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const notLoaded = (samples.data ?? []).filter((x) => !x.contract_id).map((x) => x.file);
  const chosen = picked ?? notLoaded;

  const toB64 = (f: File) => new Promise<string>((res, rej) => { const r = new FileReader(); r.onload = () => res(String(r.result).split(",")[1] ?? ""); r.onerror = rej; r.readAsDataURL(f); });

  async function run() {
    setBusy(true); setErr(null); setSummary(null); setEngine(null);
    try {
      const body = { samples: chosen, files: await Promise.all(files.map(async (f) => ({ filename: f.name, content_b64: await toB64(f) }))) };
      const tok = getToken();
      const r = await fetch(`${API}/api/intake`, { method: "POST", headers: { "Content-Type": "application/json", ...(tok ? { Authorization: `Bearer ${tok}` } : {}) }, body: JSON.stringify(body) });
      if (!r.ok || !r.body) { const t = await r.text(); let m = t; try { m = JSON.parse(t).detail ?? t; } catch { /* text */ } throw new Error(m || String(r.status)); }
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
            if (d.name !== e.doc) return d;
            if (e.step === "queued") return d;
            if (e.step === "start") return { ...d, status: "running" };
            if (e.step === "done") return { ...d, status: "done", contract_id: e.contract_id };
            if (e.step === "error") return { ...d, status: "error", error: e.message };
            return { ...d, status: "running", [e.step]: e };
          }));
        }
      }
      setFiles([]); setPicked(null);
      qc.invalidateQueries();
    } catch (e) {
      setErr(String(e instanceof Error ? e.message : e));
    } finally { setBusy(false); }
  }

  async function reset() {
    if (!window.confirm("Remove every contract added on this screen (the five samples and any uploads), so the demo can start again?")) return;
    await api("/api/intake", { method: "DELETE" });
    setDocs([]); setSummary(null); setPicked(null);
    qc.invalidateQueries();
  }

  const addFiles = (fl: FileList | null) => fl && setFiles((cur) => [...cur, ...Array.from(fl).filter((f) => /\.(pdf|docx|md|txt|html?)$/i.test(f.name))]);
  const loadedCount = (samples.data ?? []).filter((x) => x.contract_id).length;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-serif text-3xl md:text-4xl">Add contracts</h1>
          <div className="max-w-3xl text-sm text-ink-mute dark:text-slate-400">Signed contracts in, data out. Each document is read, split into clauses, its terms extracted with the page they come from,
            indexed for search by meaning, and checked against your standards. Then it is part of every screen: renewals, obligations, risk, Ask.</div>
        </div>
        {(loadedCount > 0 || docs.length > 0) && <Btn kind="ghost" onClick={reset} disabled={busy}>Reset demo</Btn>}
      </div>

      <ol className="grid gap-2 md:grid-cols-5" aria-label="What happens to each document">
        {STEPS.map(([k, label, what], i) => (
          <li key={k} className="rounded-xl border border-line bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
            <div className="text-xs font-semibold uppercase tracking-wider text-indigo-700 dark:text-indigo-300">{i + 1} · {label}</div>
            <div className="mt-1 text-sm text-ink-mute dark:text-slate-300">{what}</div>
          </li>))}
      </ol>

      <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
        <Card title="Sample contracts" right={<span className="text-xs text-ink-mute">fictional US hotel supplier paper</span>}>
          <ul className="divide-y divide-slate-100 dark:divide-slate-700">
            {samples.data?.map((x) => (
              <li key={x.file} className="flex items-start gap-3 py-2">
                <input type="checkbox" className="mt-1" aria-label={`Include ${x.file}`} disabled={busy || Boolean(x.contract_id)} checked={!x.contract_id && chosen.includes(x.file)}
                  onChange={(e) => setPicked(e.target.checked ? [...chosen, x.file] : chosen.filter((f) => f !== x.file))} />
                <div className="min-w-0 flex-1">
                  <div className="text-sm">{x.what}</div>
                  <div className="text-xs text-ink-mute dark:text-slate-400">{x.format} · {Math.round(x.size / 1024)} KB · {x.property ?? "all properties"}</div>
                </div>
                <a className="shrink-0 text-sm text-indigo-700 hover:underline dark:text-indigo-300" href={authUrl(`/api/intake/samples/${encodeURIComponent(x.file)}`)} target="_blank" rel="noreferrer">Open original</a>
                {x.contract_id && <Link className="shrink-0 text-sm text-emerald-700 hover:underline dark:text-emerald-300" to={`/contracts/${x.contract_id}`}>✓ in portfolio</Link>}
              </li>))}
          </ul>
        </Card>
        <Card title="Or your own files">
          <div role="button" tabIndex={0} aria-label="Drop PDF or Word files here, or choose files"
            onClick={() => input.current?.click()} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") input.current?.click(); }}
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); addFiles(e.dataTransfer.files); }}
            className={`flex h-36 cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed text-sm ${drag ? "border-indigo-500 bg-indigo-50 dark:bg-indigo-950/40" : "border-slate-300 dark:border-slate-600"}`}>
            <span className="font-medium">Drop PDF or Word contracts here</span>
            <span className="text-xs text-ink-mute">or click to choose · scanned PDFs are read with OCR · up to 15 MB each</span>
          </div>
          <input ref={input} type="file" multiple accept=".pdf,.docx,.md,.txt,.html,.htm" className="hidden" onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }} />
          {files.length > 0 && <ul className="mt-2 space-y-1 text-sm">{files.map((f, i) => <li key={f.name + i} className="flex justify-between gap-2"><span className="truncate">{f.name}</span><button className="text-xs text-ink-mute hover:underline" onClick={() => setFiles(files.filter((_, j) => j !== i))}>remove</button></li>)}</ul>}
        </Card>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Btn onClick={run} disabled={busy || (chosen.length + files.length === 0)}>{busy ? "Reading…" : `Read ${chosen.length + files.length} document${chosen.length + files.length === 1 ? "" : "s"}`}</Btn>
        {engine && <span className="text-sm text-ink-mute dark:text-slate-400">Engine: <b>{engine}</b></span>}
        {err && <span className="text-sm text-red-700 dark:text-red-300">{err}</span>}
        {!busy && chosen.length + files.length === 0 && loadedCount > 0 && <span className="text-sm text-ink-mute">All samples are in the portfolio. Reset to run it again.</span>}
      </div>

      {summary && summary.contracts > 0 && <SummaryCard s={summary} docs={docs} />}
      <div className="space-y-3">{docs.map((d) => <DocCard key={d.name} d={d} />)}</div>
    </div>
  );
}
