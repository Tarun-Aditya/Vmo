import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Col, Step, Table, api, fmtDate, inr, useSetting } from "../lib";
import { Card, Td, Th } from "../ui";

type Res = {
  question: string; answer: string; tiles: { label: string; kind: string; value: number | null }[]; tables: Table[]; thinking: Step[];
  source: string; cached_from?: string; elapsed_ms: number;
};

export function Cell({ col, v }: { col: Col; v: unknown }) {
  if (v === null || v === undefined || v === "") return <span className="text-slate-400">—</span>;
  switch (col.kind) {
    case "bool": return v ? <span className="font-bold text-emerald-600" aria-label="yes">✓</span> : <span className="font-bold text-red-600" aria-label="no">✗</span>;
    case "date": return <span className="whitespace-nowrap tabular-nums">{fmtDate(String(v))}</span>;
    case "money": return <span className="whitespace-nowrap tabular-nums">{inr(v as number)}</span>;
    case "score": return <span className="tabular-nums text-slate-500">{Math.round(Number(v) * 100)}%</span>;
    case "quote": return <span className="text-slate-700 dark:text-slate-300">“{String(v)}”</span>;
    default: return <span>{String(v)}</span>;
  }
}

export function DataTable({ t }: { t: Table }) {
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
                    {c.key === "title" && r._cid ? <Link to={`/contracts/${r._cid}`} className="font-medium text-indigo-600 hover:underline dark:text-indigo-400">{String(r.title)}</Link> : <Cell col={c} v={r[c.key]} />}
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
        <span aria-hidden>{open ? "▾" : "▸"}</span>
        <span className="font-medium">Thinking</span>
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

export default function Ask() {
  const [demo] = useSetting("demo", true);
  const [question, setQuestion] = useState("");
  const [showAll, setShowAll] = useState(false);
  const sugg = useQuery({ queryKey: ["sugg"], queryFn: () => api<string[]>("/api/ask/suggestions") });
  const m = useMutation({ mutationFn: (qn: string) => api<Res>("/api/ask", { method: "POST", body: JSON.stringify({ question: qn, demo_mode: demo }) }) });
  const go = (qn: string) => { setQuestion(qn); if (qn.trim()) m.mutate(qn); };
  const r = m.data;
  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <h1 className="text-xl font-semibold">Ask your vendor portfolio</h1>
      <p className="-mt-2 text-sm text-slate-500">Ask about any field — dates, signatures, clauses, values — across all documents or one. Answers come back as tables.</p>
      <form onSubmit={(e) => { e.preventDefault(); go(question); }} className="flex gap-2">
        <input className="flex-1 rounded border bg-white px-3 py-2 dark:bg-slate-800" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="e.g. Show start date, end date and signatures for all contracts" />
        <button className="rounded bg-indigo-600 px-4 py-2 font-medium text-white disabled:opacity-50" disabled={m.isPending}>{m.isPending ? "Working…" : "Ask"}</button>
      </form>
      <div className="flex flex-wrap items-center gap-2">
        {(showAll ? sugg.data : sugg.data?.slice(0, 8))?.map((s) => <button key={s} onClick={() => go(s)} className="rounded-full border border-slate-300 px-3 py-1 text-xs hover:bg-indigo-50 dark:border-slate-600 dark:hover:bg-slate-700">{s}</button>)}
        {(sugg.data?.length ?? 0) > 8 && <button onClick={() => setShowAll(!showAll)} className="text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400">{showAll ? "Show fewer" : `More examples (${(sugg.data?.length ?? 8) - 8})`}</button>}
      </div>
      {m.error && <p className="text-red-600">{String(m.error)}</p>}
      {r && (
        <div className="space-y-4">
          <Card title="Answer">
            <div className="space-y-4">
              {r.tiles.length > 0 && (
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  {r.tiles.map((t) => (
                    <div key={t.label} className="rounded-lg border border-indigo-200 bg-indigo-50 p-4 dark:border-indigo-900 dark:bg-indigo-950/50">
                      <div className="text-xs font-semibold uppercase tracking-wide text-indigo-700 dark:text-indigo-300">{t.label}</div>
                      <div className="mt-1 text-3xl font-semibold tabular-nums">{t.kind === "money" ? inr(t.value) : String(t.value ?? "—")}</div>
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
  );
}
