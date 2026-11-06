import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, inr, useSetting } from "../lib";
import { Card } from "../ui";

type Call = { name: string; input: Record<string, unknown>; output: { columns?: string[]; rows?: unknown[][]; row_count?: number; error?: string; hits?: { title: string; heading: string; page: number; score: number }[] } };
type Res = { question: string; answer: string; tool_calls: Call[]; citations: { contract_id: number; title: string; heading: string; page: number; text: string; score: number }[]; source: string; cached_from?: string; elapsed_ms: number };

function SqlBlock({ call }: { call: Call }) {
  const o = call.output;
  return (
    <div className="space-y-2">
      <pre className="overflow-x-auto rounded bg-slate-900 p-3 text-xs text-emerald-200">{String(call.input.query).trim()}</pre>
      {o.error && <p className="text-sm text-red-600">Error: {o.error}</p>}
      {o.columns && (
        <div className="overflow-x-auto"><table className="w-full text-xs">
          <thead><tr>{o.columns.map((c) => <th key={c} className="px-2 py-1 text-left font-semibold text-slate-500">{c}</th>)}</tr></thead>
          <tbody>{o.rows!.map((r, i) => <tr key={i} className="border-t border-slate-100 dark:border-slate-700">{r.map((v, j) => <td key={j} className="px-2 py-1 tabular-nums">{v === null ? "—" : String(v)}</td>)}</tr>)}</tbody>
        </table><p className="mt-1 text-[11px] text-slate-500">{o.row_count} row(s)</p></div>
      )}
    </div>
  );
}

/** Headline numbers: the first single-row, numeric SQL result (e.g. COUNT / SUM) becomes tiles. */
function Tiles({ calls }: { calls: Call[] }) {
  const c = calls.find((x) => x.name === "run_sql" && x.output.rows?.length === 1 && x.output.columns!.length <= 4
    && x.output.rows[0].every((v) => typeof v === "number" || v === null));
  if (!c) return null;
  const cols = c.output.columns!, row = c.output.rows![0];
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
      {cols.map((col, i) => {
        const money = /value|spend/.test(col);
        return (
          <div key={col} className="rounded-lg border border-indigo-200 bg-indigo-50 p-4 dark:border-indigo-900 dark:bg-indigo-950/50">
            <div className="text-xs font-semibold uppercase tracking-wide text-indigo-700 dark:text-indigo-300">{col.replace(/_/g, " ")}</div>
            <div className="mt-1 text-3xl font-semibold tabular-nums">{money ? inr(row[i] as number) : String(row[i] ?? "—")}</div>
          </div>
        );
      })}
    </div>
  );
}

export default function Ask() {
  const [demo] = useSetting("demo", true);
  const [question, setQuestion] = useState("");
  const [open, setOpen] = useState(true);
  const sugg = useQuery({ queryKey: ["sugg"], queryFn: () => api<string[]>("/api/ask/suggestions") });
  const m = useMutation({ mutationFn: (qn: string) => api<Res>("/api/ask", { method: "POST", body: JSON.stringify({ question: qn, demo_mode: demo }) }) });
  const go = (qn: string) => { setQuestion(qn); if (qn.trim()) m.mutate(qn); };
  const r = m.data;
  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <h1 className="text-xl font-semibold">Ask your vendor portfolio</h1>
      <form onSubmit={(e) => { e.preventDefault(); go(question); }} className="flex gap-2">
        <input className="flex-1 rounded border bg-white px-3 py-2 dark:bg-slate-800" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="e.g. Which vendors have uncapped liability?" />
        <button className="rounded bg-indigo-600 px-4 py-2 font-medium text-white disabled:opacity-50" disabled={m.isPending}>{m.isPending ? "Thinking…" : "Ask"}</button>
      </form>
      <div className="flex flex-wrap gap-2">
        {sugg.data?.map((s) => <button key={s} onClick={() => go(s)} className="rounded-full border border-slate-300 px-3 py-1 text-xs hover:bg-indigo-50 dark:border-slate-600 dark:hover:bg-slate-700">{s}</button>)}
      </div>
      {m.error && <p className="text-red-600">{String(m.error)}</p>}
      {r && (
        <>
          <Card title="Answer" right={<span className="text-xs text-slate-500">{r.source === "cache" ? `cached (${r.cached_from})` : r.source} · {r.elapsed_ms} ms</span>}>
            <div className="space-y-4"><Tiles calls={r.tool_calls} /><p className="whitespace-pre-line text-base leading-relaxed">{r.answer}</p></div>
          </Card>
          <Card title="How I got this" right={<button className="text-xs text-indigo-600" onClick={() => setOpen(!open)}>{open ? "Hide" : "Show"}</button>}>
            {open && (
              <div className="space-y-4">
                {r.tool_calls.map((c, i) => (
                  <div key={i}>
                    <div className="mb-1 text-xs font-semibold uppercase text-slate-500">Step {i + 1} · {c.name === "run_sql" ? "SQL query" : c.name === "search_clauses" ? `Clause search — “${c.input.query}”${c.input.clause_type ? ` [${c.input.clause_type}]` : ""}` : c.name}</div>
                    {c.name === "run_sql" ? <SqlBlock call={c} /> : c.name === "search_clauses" ? <p className="text-xs text-slate-500">{c.output.hits?.length} clauses retrieved (cosine similarity)</p> : <pre className="text-xs">{JSON.stringify(c.input)}</pre>}
                  </div>
                ))}
                {r.citations.length > 0 && (
                  <div>
                    <div className="mb-1 text-xs font-semibold uppercase text-slate-500">Cited clauses</div>
                    <ul className="space-y-2">
                      {r.citations.map((c, i) => (
                        <li key={i} className="rounded border border-slate-200 p-2 text-sm dark:border-slate-700">
                          <Link to={`/contracts/${c.contract_id}`} className="font-medium text-indigo-600 hover:underline dark:text-indigo-400">{c.title}</Link>
                          <span className="text-slate-500"> · {c.heading} · p.{c.page} · similarity {c.score}</span>
                          <p className="mt-1 text-slate-700 dark:text-slate-300">“{c.text}”</p>
                        </li>))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
