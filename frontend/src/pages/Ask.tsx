import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { API, Col, Step, Table, ago, api, fmtDate, usd, useSetting } from "../lib";
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

type Msg =
  | { role: "user"; text: string; scope: number }
  | { role: "assistant"; steps: Step[]; reasoning: string; answer: string; result?: Res; running: boolean; error?: string };
type Conv = { id: number; title: string; updated_at: string; questions: number; last_answer: string | null };
type Stored = { id: number; title: string; scope: number[] | null; messages: { id: number; role: "user" | "assistant"; content: string; payload: (Res & { scope?: number[] }) | null }[] };

function Thinking({ steps, reasoning, running, ms, source }: { steps: Step[]; reasoning: string; running: boolean; ms?: number; source?: string }) {
  const [open, setOpen] = useState(running);
  const wasRunning = useRef(running);
  useEffect(() => { if (running) setOpen(true); else if (wasRunning.current) setOpen(false); wasRunning.current = running; }, [running]);
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-white/60 dark:border-slate-600 dark:bg-slate-800/60" data-thinking={running ? "live" : "done"}>
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-slate-600 dark:text-slate-300" aria-expanded={open}>
        <span aria-hidden>{open ? "▾" : "▸"}</span><span className="font-medium">Thinking{running ? "…" : ""}</span>
        <span className="text-xs text-slate-500">· {steps.length} step{steps.length !== 1 ? "s" : ""}{!running && ms !== undefined ? ` · ${ms} ms · ${source === "cache" ? "cached" : source}` : ""}</span>
        {running && <span className="ml-1 inline-block h-2 w-2 animate-pulse rounded-full bg-indigo-500" aria-hidden />}
      </button>
      {open && (
        <div className="space-y-3 border-t border-dashed border-slate-300 px-4 py-3 text-sm dark:border-slate-600">
          {reasoning && <div className="max-h-48 overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-2 text-xs italic text-slate-600 dark:bg-slate-900 dark:text-slate-400" aria-label="Model reasoning">{reasoning}</div>}
          <ol className="space-y-3">
            {steps.map((st, i) => (
              <li key={i} className="flex gap-3">
                <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-[11px] font-semibold text-indigo-700 dark:bg-indigo-900 dark:text-indigo-200">{running && i === steps.length - 1 ? "…" : i + 1}</span>
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="font-medium">{st.title}</div>
                  {st.detail && <div className="text-slate-600 dark:text-slate-400">{st.detail}</div>}
                  {st.sql && <pre className="overflow-x-auto whitespace-pre-wrap rounded bg-slate-900 p-2 text-xs text-emerald-200">{st.sql.trim()}</pre>}
                  {st.error && <div className="text-red-600">Error: {st.error}</div>}
                  {st.columns && st.rows && st.rows.length > 0 && (
                    <div className="overflow-x-auto"><table className="text-xs"><thead><tr>{st.columns.map((c) => <th key={c} className="pr-4 text-left font-semibold text-slate-500">{c}</th>)}</tr></thead>
                      <tbody>{st.rows.slice(0, 5).map((r, j) => <tr key={j}>{r.map((v, k) => <td key={k} className="pr-4 tabular-nums">{v === null ? "—" : String(v)}</td>)}</tr>)}</tbody></table>
                      {(st.row_count ?? 0) > 5 && <div className="text-[11px] text-slate-500">first 5 of {st.row_count} rows</div>}</div>)}
                </div>
              </li>))}
            {steps.length === 0 && <li className="text-slate-500">Starting…</li>}
          </ol>
        </div>)}
    </div>
  );
}

const DOC_SUGGESTIONS = ["Tell me about this contract", "What are the payment terms, liability cap and governing law?", "Who signed and when?", "What does the indemnity clause say?", "Which checklist rules does it fail?", "Can the supplier terminate for convenience?"];

function Answer({ m }: { m: Extract<Msg, { role: "assistant" }> }) {
  const r = m.result;
  return (
    <div className="space-y-3" data-msg="assistant" {...(m.running ? { "data-streaming": "1" } : {})}>
      <Thinking steps={r?.thinking ?? m.steps} reasoning={m.reasoning} running={m.running} ms={r?.elapsed_ms} source={r?.source} />
      {m.error && <p className="text-sm text-red-600">{m.error}</p>}
      {(m.answer || r) && (
        <Card title="Answer" right={r && <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600 dark:bg-slate-700 dark:text-slate-200">{r.scoped ? `Scope: ${r.scoped} selected document${r.scoped > 1 ? "s" : ""}` : "Scope: whole portfolio"}</span>}>
          <div className="space-y-4">
            {r && r.tiles.length > 0 && (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {r.tiles.map((t) => (
                  <div key={t.label} className="rounded-lg border border-indigo-200 bg-indigo-50 p-4 dark:border-indigo-900 dark:bg-indigo-950/50">
                    <div className="text-xs font-semibold uppercase tracking-wide text-indigo-700 dark:text-indigo-300">{t.label}</div>
                    <div className="mt-1 text-3xl font-semibold tabular-nums">{t.kind === "money" ? usd(t.value) : String(t.value ?? "—")}</div>
                  </div>))}
              </div>)}
            <p className="text-base leading-relaxed">{r?.answer ?? m.answer}{m.running && <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-indigo-500 align-middle" aria-hidden />}</p>
            {r?.tables.map((t, i) => <DataTable key={i} t={t} />)}
          </div>
        </Card>)}
    </div>
  );
}

export default function Ask() {
  const [demo] = useSetting("demo", true);
  const qc = useQueryClient();
  const [params] = useSearchParams();
  const [question, setQuestion] = useState("");
  const [showAll, setShowAll] = useState(false);
  const [mode, setMode] = useState<"all" | "selected">("all");
  const [sel, setSel] = useState<number[]>([]);
  const [find, setFind] = useState("");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [convId, setConvId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [histQ, setHistQ] = useState("");
  const abort = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const sugg = useQuery({ queryKey: ["sugg"], queryFn: () => api<string[]>("/api/ask/suggestions") });
  const docs = useQuery({ queryKey: ["documents"], queryFn: () => api<Doc[]>("/api/documents") });
  const hist = useQuery({ queryKey: ["conversations", histQ], queryFn: () => api<Conv[]>(`/api/conversations${histQ ? `?q=${encodeURIComponent(histQ)}` : ""}`) });
  const scope = mode === "selected" ? sel : [];
  useEffect(() => { endRef.current?.scrollIntoView({ block: "end", behavior: "smooth" }); }, [msgs]);

  const patchLast = (f: (m: Extract<Msg, { role: "assistant" }>) => Partial<Extract<Msg, { role: "assistant" }>>) =>
    setMsgs((all) => all.map((m, i) => (i === all.length - 1 && m.role === "assistant" ? { ...m, ...f(m) } : m)));

  const send = async (qn: string) => {
    if (!qn.trim() || busy || (mode === "selected" && sel.length === 0)) return;
    setQuestion("");
    setBusy(true);
    setMsgs((all) => [...all, { role: "user", text: qn, scope: scope.length }, { role: "assistant", steps: [], reasoning: "", answer: "", running: true }]);
    const ac = new AbortController();
    abort.current = ac;
    try {
      const resp = await fetch(`${API}/api/chat/stream`, { method: "POST", signal: ac.signal, headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: qn, conversation_id: convId, demo_mode: demo, contract_ids: scope.length ? scope : null }) });
      if (!resp.ok || !resp.body) throw new Error(await resp.text());
      const reader = resp.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let i: number;
        while ((i = buf.indexOf("\n\n")) >= 0) {
          const chunk = buf.slice(0, i).trim();
          buf = buf.slice(i + 2);
          if (!chunk.startsWith("data:")) continue;
          const ev = JSON.parse(chunk.slice(5));
          if (ev.type === "meta") setConvId(ev.conversation_id);
          else if (ev.type === "step") patchLast((m) => ({ steps: [...m.steps, ev.step] }));
          else if (ev.type === "reasoning") patchLast((m) => ({ reasoning: m.reasoning + ev.text }));
          else if (ev.type === "token") patchLast((m) => ({ answer: m.answer + ev.text }));
          else if (ev.type === "result") patchLast(() => ({ result: ev.result, answer: ev.result.answer }));
          else if (ev.type === "error") patchLast(() => ({ error: ev.message }));
        }
      }
    } catch (e) {
      if ((e as Error).name !== "AbortError") patchLast(() => ({ error: String(e) }));
      else patchLast((m) => ({ error: m.answer ? undefined : "Stopped." }));
    } finally {
      patchLast(() => ({ running: false }));
      setBusy(false);
      abort.current = null;
      qc.invalidateQueries({ queryKey: ["conversations"] });
    }
  };

  const open = async (id: number) => {
    if (busy) return;
    const c = await api<Stored>(`/api/conversations/${id}`);
    setConvId(c.id);
    setMsgs(c.messages.map((m): Msg => m.role === "user"
      ? { role: "user", text: m.content, scope: m.payload?.scope?.length ?? 0 }
      : { role: "assistant", steps: m.payload?.thinking ?? [], reasoning: "", answer: m.content, result: m.payload ?? undefined, running: false }));
    const last = [...c.messages].reverse().find((m) => m.role === "user")?.payload?.scope;
    if (last?.length) { setSel(last); setMode("selected"); } else setMode("all");
  };
  const fresh = () => { if (busy) return; setConvId(null); setMsgs([]); setQuestion(""); };
  const rename = async (c: Conv) => { const t = window.prompt("Rename conversation", c.title); if (t && t.trim()) { await api(`/api/conversations/${c.id}`, { method: "PATCH", body: JSON.stringify({ title: t }) }); qc.invalidateQueries({ queryKey: ["conversations"] }); } };
  const remove = async (c: Conv) => { if (!window.confirm(`Delete “${c.title}”?`)) return; await api(`/api/conversations/${c.id}`, { method: "DELETE" }); if (c.id === convId) fresh(); qc.invalidateQueries({ queryKey: ["conversations"] }); };

  useEffect(() => {
    const ids = params.getAll("doc").map(Number).filter(Boolean);
    if (ids.length) { setSel(ids); setMode("selected"); }
    const qp = params.get("q");
    if (qp) { if (!ids.length) void send(qp); else setQuestion(qp); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);
  useEffect(() => { const qp = params.get("q"); if (qp && sel.length && mode === "selected" && msgs.length === 0 && !busy) void send(qp); /* eslint-disable-next-line */ }, [sel, mode]);
  const shown = useMemo(() => (docs.data ?? []).filter((d) => !find || (d.title + d.vendor + d.type + d.status).toLowerCase().includes(find.toLowerCase())), [docs.data, find]);
  const toggle = (id: number) => setSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const chips = mode === "selected" ? DOC_SUGGESTIONS : (showAll ? sugg.data : sugg.data?.slice(0, 8));
  return (
    <div className="grid gap-5 lg:grid-cols-[14rem_minmax(0,1fr)_20rem]">
      <aside className="space-y-2 lg:sticky lg:top-16 lg:max-h-[calc(100vh-5rem)] lg:self-start lg:overflow-auto" aria-label="Conversation history">
        <button onClick={fresh} disabled={busy} className="w-full rounded bg-indigo-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-50">+ New chat</button>
        <input className="w-full rounded border bg-white px-2 py-1.5 text-sm dark:bg-slate-800" placeholder="Search conversations…" aria-label="Search conversations" value={histQ} onChange={(e) => setHistQ(e.target.value)} />
        <ul className="space-y-1">
          {hist.data?.map((c) => (
            <li key={c.id} className={`group rounded border px-2 py-1.5 text-sm ${c.id === convId ? "border-indigo-500 bg-indigo-50 dark:bg-slate-700" : "border-transparent hover:bg-slate-100 dark:hover:bg-slate-800"}`}>
              <button className="block w-full text-left" onClick={() => open(c.id)}>
                <span className="line-clamp-2 leading-snug">{c.title}</span>
                <span className="text-[11px] text-slate-500">{ago(c.updated_at)} · {c.questions} question{c.questions !== 1 ? "s" : ""}</span>
              </button>
              <span className="mt-0.5 hidden gap-2 text-[11px] group-hover:flex"><button className="text-indigo-600 hover:underline" onClick={() => rename(c)} aria-label={`Rename ${c.title}`}>Rename</button><button className="text-red-600 hover:underline" onClick={() => remove(c)} aria-label={`Delete ${c.title}`}>Delete</button></span>
            </li>))}
          {hist.data && hist.data.length === 0 && <li className="px-1 text-xs text-slate-500">{histQ ? "No conversations match." : "Your conversations will appear here."}</li>}
        </ul>
      </aside>

      <div className="flex min-h-[70vh] min-w-0 flex-col">
        <div className="flex-1 space-y-4 pb-4">
          <h1 className="text-xl font-semibold">Ask your vendor portfolio</h1>
          <p className="-mt-2 text-sm text-slate-500">Analytical questions across all documents, or questions about the specific documents you pick on the right. Follow-ups stay in the same conversation.</p>
          {msgs.length === 0 && (
            <div className="flex flex-wrap items-center gap-2">
              {chips?.map((s) => <button key={s} onClick={() => send(s)} className="rounded-full border border-slate-300 px-3 py-1 text-xs hover:bg-indigo-50 dark:border-slate-600 dark:hover:bg-slate-700">{s}</button>)}
              {mode === "all" && (sugg.data?.length ?? 0) > 8 && <button onClick={() => setShowAll(!showAll)} className="text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400">{showAll ? "Show fewer" : `More examples (${(sugg.data?.length ?? 8) - 8})`}</button>}
            </div>)}
          {msgs.map((m, i) => m.role === "user"
            ? <div key={i} className="flex justify-end" data-msg="user"><div className="max-w-[85%] rounded-2xl rounded-br-sm bg-indigo-600 px-4 py-2 text-white">{m.text}{m.scope > 0 && <div className="text-[11px] opacity-80">{m.scope} selected document{m.scope > 1 ? "s" : ""}</div>}</div></div>
            : <Answer key={i} m={m} />)}
          <div ref={endRef} />
        </div>
        <div className="sticky bottom-0 space-y-2 bg-slate-50 pb-2 pt-2 dark:bg-slate-900">
          {mode === "selected" && sel.length === 0 && <p className="text-sm text-amber-700 dark:text-amber-400">Select at least one document on the right to ask about it.</p>}
          {msgs.length > 0 && mode === "selected" && <div className="flex flex-wrap gap-2">{DOC_SUGGESTIONS.slice(0, 4).map((s) => <button key={s} onClick={() => send(s)} disabled={busy} className="rounded-full border border-slate-300 px-3 py-1 text-xs hover:bg-indigo-50 disabled:opacity-50 dark:border-slate-600 dark:hover:bg-slate-700">{s}</button>)}</div>}
          <form onSubmit={(e) => { e.preventDefault(); void send(question); }} className="flex gap-2">
            <input className="flex-1 rounded border bg-white px-3 py-2 dark:bg-slate-800" aria-label="Your question" value={question} onChange={(e) => setQuestion(e.target.value)}
              placeholder={msgs.length ? "Ask a follow-up…" : mode === "selected" ? "Ask about the selected documents…" : "e.g. Show start date, end date and signatures for all contracts"} />
            {busy
              ? <button type="button" onClick={() => abort.current?.abort()} className="rounded border border-red-500 px-4 py-2 font-medium text-red-600">■ Stop</button>
              : <button className="rounded bg-indigo-600 px-4 py-2 font-medium text-white disabled:opacity-50" disabled={mode === "selected" && sel.length === 0}>Ask</button>}
          </form>
        </div>
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
