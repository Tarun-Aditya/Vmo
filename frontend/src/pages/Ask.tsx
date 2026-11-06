import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Col, Step, Table, api, fmtDate, usd, useSetting } from "../lib";
import { Card, Sev, SeverityChip, Td, Th } from "../ui";

type Res = {
  question: string; answer: string; tiles: { label: string; kind: string; value: number | null }[]; tables: Table[]; thinking: Step[];
  source: string; cached_from?: string; elapsed_ms: number; scoped?: number;
};
type Doc = { id: number; title: string; vendor: string; type: string; status: string };

export function Cell({ kind, v }: { kind: Col["kind"]; v: unknown }) {
  if (v === null || v === undefined || v === "") return <span className="text-slate-400">—</span>;
  switch (kind) {
    case "bool": return v ? <span className="font-bold text-emerald-600" aria-label="yes">✓</span> : <span className="font-bold text-red-600" aria-label="no">✗</span>;
    case "date": return <span className="whitespace-nowrap tabular-nums">{fmtDate(String(v))}</span>;
    case "money": return <span className="whitespace-nowrap tabular-nums">{usd(v as number)}</span>;
    case "score": return <span className="tabular-nums text-slate-500">{Math.round(Number(v) * 100)}%</span>;
    case "severity": return <SeverityChip sev={String(v) as Sev} />;
    case "quote": return <span className="text-slate-700 dark:text-slate-300">“{String(v)}”</span>;
    case "number": return <span className="tabular-nums">{typeof v === "number" ? v.toLocaleString("en-US", { maximumFractionDigits: 2 }) : String(v)}</span>;
    default: return <span>{String(v)}</span>;
  }
}

export function DataTable({ t }: { t: Table }) {
  if (t.kv) {
    return (
      <div>
        {t.title && <h3 className="mb-1 text-sm font-semibold">{t.title}</h3>}
        <div className="overflow-hidden rounded border border-slate-200 dark:border-slate-700">
          <table className="w-full text-sm"><tbody>
            {t.rows.map((r, i) => (
              <tr key={i} className="border-t border-slate-100 first:border-t-0 dark:border-slate-700">
                <Td className="w-2/5 bg-slate-50 font-medium text-slate-600 dark:bg-slate-900/50 dark:text-slate-300">{String(r.field)}</Td>
                <Td><Cell kind={(r.kind as Col["kind"]) ?? "text"} v={r.value} />{r.unit && r.value !== null && r.kind !== "money" ? <span className="ml-1 text-xs text-slate-500">{String(r.unit)}</span> : null}</Td>
              </tr>))}
          </tbody></table>
        </div>
      </div>
    );
  }
  return (
    <div>
      {t.title && <div className="mb-1 flex items-baseline gap-2"><h3 className="text-sm font-semibold">{t.title}</h3><span className="text-xs text-slate-500">{t.row_count} row{t.row_count !== 1 ? "s" : ""}</span></div>}
      <div className="max-h-[28rem] overflow-auto rounded border border-slate-200 dark:border-slate-700">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-slate-100 dark:bg-slate-900"><tr>{t.columns.map((c) => <Th key={c.key} className={c.kind === "money" || c.kind === "number" ? "text-right" : c.kind === "bool" ? "text-center" : ""}>{c.label}</Th>)}</tr></thead>
          <tbody>
            {t.rows.map((r, i) => (
              <tr key={i} className="border-t border-slate-100 dark:border-slate-700">
                {t.columns.map((c) => (
                  <Td key={c.key} className={c.kind === "money" || c.kind === "number" ? "text-right" : c.kind === "bool" ? "text-center text-base" : ""}>
                    {c.key === "title" && r._cid ? <Link to={`/contracts/${r._cid}`} className="font-medium text-indigo-600 hover:underline dark:text-indigo-400">{String(r.title)}</Link> : <Cell kind={c.kind} v={r[c.key]} />}
                  </Td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Thinking({ steps, ms, source }: { steps: Step[]; ms: number; source: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-white/60 dark:border-slate-600 dark:bg-slate-800/60">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-slate-600 dark:text-slate-300">
        <span aria-hidden>{open ? "▾" : "▸"}</span><span className="font-medium">Thinking</span>
        <span className="text-xs text-slate-500">· {steps.length} steps · {ms} ms · {source === "cache" ? "cached" : source}</span>
      </button>
      {open && (
        <ol className="space-y-3 border-t border-dashed border-slate-300 px-4 py-3 text-sm dark:border-slate-600">
          {steps.map((s, i) => (
            <li key={i} className="flex gap-3">
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-[11px] font-semibold text-indigo-700 dark:bg-indigo-900 dark:text-indigo-200">{i + 1}</span>
              <div className="min-w-0 flex-1 space-y-1">
                <div className="font-medium">{s.title}</div>
                {s.detail && <div className="text-slate-600 dark:text-slate-400">{s.detail}</div>}
                {s.sql && <pre className="overflow-x-auto whitespace-pre-wrap rounded bg-slate-900 p-2 text-xs text-emerald-200">{s.sql.trim()}</pre>}
                {s.error && <div className="text-red-600">Error: {s.error}</div>}
                {s.columns && s.rows && s.rows.length > 0 && (
                  <div className="overflow-x-auto"><table className="text-xs"><thead><tr>{s.columns.map((c) => <th key={c} className="pr-4 text-left font-semibold text-slate-500">{c}</th>)}</tr></thead>
                    <tbody>{s.rows.slice(0, 5).map((r, j) => <tr key={j}>{r.map((v, k) => <td key={k} className="pr-4 tabular-nums">{v === null ? "—" : String(v)}</td>)}</tr>)}</tbody></table>
                    {(s.row_count ?? 0) > 5 && <div className="text-[11px] text-slate-500">first 5 of {s.row_count} rows</div>}</div>
                )}
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

const DOC_SUGGESTIONS = ["Tell me about this contract", "What are the payment terms, liability cap and governing law?", "Who signed and when?", "What does the indemnity clause say?", "Which checklist rules does it fail?", "Can the supplier terminate for convenience?"];

export default function Ask() {
  const [demo] = useSetting("demo", true);
  const [params] = useSearchParams();
  const [question, setQuestion] = useState("");
  const [showAll, setShowAll] = useState(false);
  const [mode, setMode] = useState<"all" | "selected">("all");
  const [sel, setSel] = useState<number[]>([]);
  const [find, setFind] = useState("");
  const sugg = useQuery({ queryKey: ["sugg"], queryFn: () => api<string[]>("/api/ask/suggestions") });
  const docs = useQuery({ queryKey: ["documents"], queryFn: () => api<Doc[]>("/api/documents") });
  const scope = mode === "selected" ? sel : [];
  const m = useMutation({
    mutationFn: (qn: string) => api<Res>("/api/ask", { method: "POST", body: JSON.stringify({ question: qn, demo_mode: demo, contract_ids: scope.length ? scope : null }) }),
  });
  const go = (qn: string) => { setQuestion(qn); if (qn.trim() && (mode === "all" || sel.length)) m.mutate(qn); };
  const r = m.data;
  useEffect(() => {
    const ids = params.getAll("doc").map(Number).filter(Boolean);
    if (ids.length) { setSel(ids); setMode("selected"); }
    const qp = params.get("q");
    if (qp) { setQuestion(qp); if (!ids.length) m.mutate(qp); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);
  useEffect(() => { const qp = params.get("q"); if (qp && sel.length && mode === "selected" && !m.data && !m.isPending) m.mutate(qp); /* eslint-disable-next-line */ }, [sel, mode]);
  const shown = useMemo(() => (docs.data ?? []).filter((d) => !find || (d.title + d.vendor + d.type + d.status).toLowerCase().includes(find.toLowerCase())), [docs.data, find]);
  const toggle = (id: number) => setSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const chips = mode === "selected" ? DOC_SUGGESTIONS : (showAll ? sugg.data : sugg.data?.slice(0, 8));
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_21rem]">
      <div className="space-y-4">
        <h1 className="text-xl font-semibold">Ask your vendor portfolio</h1>
        <p className="-mt-2 text-sm text-slate-500">Analytical questions across all documents, or questions about the specific documents you pick on the right. Answers come back as tables.</p>
        <form onSubmit={(e) => { e.preventDefault(); go(question); }} className="flex gap-2">
          <input className="flex-1 rounded border bg-white px-3 py-2 dark:bg-slate-800" value={question} onChange={(e) => setQuestion(e.target.value)}
            placeholder={mode === "selected" ? "Ask about the selected documents…" : "e.g. Show start date, end date and signatures for all contracts"} />
          <button className="rounded bg-indigo-600 px-4 py-2 font-medium text-white disabled:opacity-50" disabled={m.isPending || (mode === "selected" && sel.length === 0)}>{m.isPending ? "Working…" : "Ask"}</button>
        </form>
        {mode === "selected" && sel.length === 0 && <p className="text-sm text-amber-700 dark:text-amber-400">Select at least one document on the right to ask about it.</p>}
        <div className="flex flex-wrap items-center gap-2">
          {chips?.map((s) => <button key={s} onClick={() => go(s)} className="rounded-full border border-slate-300 px-3 py-1 text-xs hover:bg-indigo-50 dark:border-slate-600 dark:hover:bg-slate-700">{s}</button>)}
          {mode === "all" && (sugg.data?.length ?? 0) > 8 && <button onClick={() => setShowAll(!showAll)} className="text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400">{showAll ? "Show fewer" : `More examples (${(sugg.data?.length ?? 8) - 8})`}</button>}
        </div>
        {m.error && <p className="text-red-600">{String(m.error)}</p>}
        {r && (
          <div className="space-y-4">
            <Card title="Answer" right={<span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600 dark:bg-slate-700 dark:text-slate-200">{r.scoped ? `Scope: ${r.scoped} selected document${r.scoped > 1 ? "s" : ""}` : "Scope: whole portfolio"}</span>}>
              <div className="space-y-4">
                {r.tiles.length > 0 && (
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                    {r.tiles.map((t) => (
                      <div key={t.label} className="rounded-lg border border-indigo-200 bg-indigo-50 p-4 dark:border-indigo-900 dark:bg-indigo-950/50">
                        <div className="text-xs font-semibold uppercase tracking-wide text-indigo-700 dark:text-indigo-300">{t.label}</div>
                        <div className="mt-1 text-3xl font-semibold tabular-nums">{t.kind === "money" ? usd(t.value) : String(t.value ?? "—")}</div>
                      </div>
                    ))}
                  </div>
                )}
                <p className="text-base leading-relaxed">{r.answer}</p>
                {r.tables.map((t, i) => <DataTable key={i} t={t} />)}
              </div>
            </Card>
            <Thinking steps={r.thinking} ms={r.elapsed_ms} source={r.source} />
          </div>
        )}
      </div>

      <aside className="lg:sticky lg:top-16 lg:self-start" aria-label="Question scope">
        <Card title="Scope of the question">
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-1 rounded border border-slate-300 p-0.5 text-sm dark:border-slate-600" role="radiogroup" aria-label="Scope mode">
              {([["all", "All documents"], ["selected", "Selected documents"]] as const).map(([v, l]) => (
                <button key={v} role="radio" aria-checked={mode === v} onClick={() => setMode(v)} className={`rounded px-2 py-1.5 ${mode === v ? "bg-indigo-600 font-medium text-white" : "hover:bg-slate-100 dark:hover:bg-slate-700"}`}>{l}</button>
              ))}
            </div>
            <p className="text-xs text-slate-500">{mode === "all" ? "Analytical: counts, totals, dates, risks across the whole portfolio." : "Specific: answers come only from the documents ticked below."}</p>
            <input className="w-full rounded border bg-white px-2 py-1.5 text-sm dark:bg-slate-800" placeholder="Search documents…" aria-label="Search documents" value={find} onChange={(e) => setFind(e.target.value)} />
            <div className="flex items-center justify-between text-xs text-slate-500">
              <span>{sel.length} selected · {shown.length} shown</span>
              <span className="space-x-2"><button className="text-indigo-600 hover:underline" onClick={() => { setMode("selected"); setSel(Array.from(new Set([...sel, ...shown.map((d) => d.id)]))); }}>Select shown</button><button className="text-indigo-600 hover:underline" onClick={() => setSel([])}>Clear</button></span>
            </div>
            <ul className="max-h-[26rem] space-y-0.5 overflow-auto pr-1" aria-label="Documents">
              {shown.map((d) => (
                <li key={d.id}>
                  <label className={`flex cursor-pointer items-start gap-2 rounded px-2 py-1.5 text-sm hover:bg-slate-50 dark:hover:bg-slate-700/50 ${sel.includes(d.id) ? "bg-indigo-50 dark:bg-indigo-950/40" : ""}`}>
                    <input type="checkbox" className="mt-1" checked={sel.includes(d.id)} onChange={() => { setMode("selected"); toggle(d.id); }} />
                    <span className="min-w-0"><span className="block leading-snug">{d.title}</span>
                      <span className="text-[11px] text-slate-500"><span className="mr-1 rounded bg-slate-200 px-1 font-semibold uppercase dark:bg-slate-700">{d.type}</span>{d.vendor}{d.status === "draft" && <span className="ml-1 rounded border border-amber-500 px-1 text-amber-700 dark:text-amber-300">draft</span>}</span></span>
                  </label>
                </li>))}
              {docs.data && shown.length === 0 && <li className="py-3 text-center text-sm text-slate-500">No documents match</li>}
            </ul>
          </div>
        </Card>
      </aside>
    </div>
  );
}
