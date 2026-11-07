import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { mdToHtml } from "../components/mdhtml";
import { Btn, inputCls } from "../forms";
import { api, authUrl, when } from "../lib";
import { Card, Loading, Sev, SeverityChip, sevStripe } from "../ui";

type RStatus = "pending" | "in_review" | "changes_requested" | "approved";
type Doc = { id: number; title: string; vendor: string; type: string; status: string; origin: string; deviations: number; counts: Record<Sev, number>; checks_failed: number; check_counts: Record<Sev, number>; review_status: RStatus; assignee?: string | null; due_date?: string | null };
type Item = { clause_type: string; heading: string; status: "changed" | "missing"; draft_text: string; standard_position: string; deviation: string; severity: Sev; suggested_text: string; diff: [string, string][]; page: number | null };
type Check = { rule_key: string; name: string; description: string | null; status: "pass" | "fail" | "na"; severity: Sev; actual: string | null; expected: string | null; page: number | null; excerpt: string | null; suggested_text: string | null };
type Red = { id: number; title: string; vendor: string; type: string; status: string; body_md: string; template: { name: string } | null; items: Item[]; counts: Record<Sev, number>; source: string; elapsed_ms?: number;
  checklist: Check[]; checklist_summary: { pass: number; fail: number; na: number }; checklist_fail_counts: Record<Sev, number>;
  review: { status: RStatus; note: string | null; reviewer: string | null; assignee: string | null; due_date: string | null; updated_at: string | null }; decisions: Record<string, "accepted" | "rejected"> };

const ORDER: Sev[] = ["critical", "high", "medium", "low"];
const STATUS: Record<RStatus, { label: string; cls: string }> = {
  pending: { label: "To review", cls: "bg-slate-200 text-slate-800 dark:bg-slate-600 dark:text-slate-100" },
  in_review: { label: "In review", cls: "bg-sky-100 text-sky-900" },
  changes_requested: { label: "Changes requested", cls: "bg-amber-100 text-amber-900" },
  approved: { label: "Approved", cls: "bg-emerald-100 text-emerald-900" },
};
const chips = (c: Record<Sev, number>) => ORDER.filter((s) => c[s]).map((s) => <SeverityChip key={s} sev={s} label={String(c[s])} />);
const esc = (t: string) => t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

/** The document as a Word-style page with the redline shown as tracked changes in place. */
function trackedHtml(md: string, items: Item[], dec: Record<string, string>): string {
  let body = md;
  const repl: string[] = [];
  const missing: Item[] = [];
  items.forEach((it) => {
    if (it.status === "missing") { missing.push(it); return; }
    let idx = body.indexOf(it.draft_text);
    let len = it.draft_text.length;
    if (idx < 0) {                                           // tolerate whitespace differences
      const re = new RegExp(it.draft_text.trim().split(/\s+/).map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("\\s+"));
      const m = re.exec(body);
      if (!m) return;
      idx = m.index; len = m[0].length;
    }
    const token = `\u0001${repl.length}\u0001`;
    const d = dec[it.clause_type];
    const inner = d === "accepted" ? `<ins class="tc">${esc(it.suggested_text)}</ins>`
      : d === "rejected" ? esc(it.draft_text)
      : it.diff.map(([op, t]) => op === "del" ? `<del class="tc">${esc(t)}</del>` : op === "ins" ? `<ins class="tc">${esc(t)}</ins>` : esc(t)).join(" ");
    repl.push(`<span class="rl-block ${d === "accepted" ? "rl-accepted" : d === "rejected" ? "rl-rejected" : "rl-open"}" data-ct="${it.clause_type}">${inner}</span>`);
    body = body.slice(0, idx) + token + body.slice(idx + len);
  });
  let html = mdToHtml(body);
  repl.forEach((r, i) => { html = html.replace(`\u0001${i}\u0001`, r); });
  missing.forEach((it) => {
    const d = dec[it.clause_type];
    if (d === "rejected") return;
    html += `<h2><ins class="tc">${esc(it.heading)} (new clause)</ins></h2><p><span class="rl-block ${d === "accepted" ? "rl-accepted" : "rl-open"}" data-ct="${it.clause_type}"><ins class="tc">${esc(it.suggested_text)}</ins></span></p>`;
  });
  return html;
}

function CheckRow({ c }: { c: Check }) {
  const [open, setOpen] = useState(false);
  const mark = c.status === "pass" ? <b className="text-emerald-600" aria-label="pass">✓</b> : c.status === "fail" ? <b className="text-red-600" aria-label="fail">✗</b> : <b className="text-slate-400" aria-label="not applicable">–</b>;
  return (
    <li className={`rounded border border-slate-200 dark:border-slate-700 ${c.status === "fail" ? sevStripe(c.severity) : ""}`}>
      <button className="flex w-full items-center gap-3 px-3 py-2 text-left text-sm" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="w-5 text-center text-base">{mark}</span>
        <span className="min-w-0 flex-1"><span className={c.status === "na" ? "text-slate-400" : "font-medium"}>{c.name}</span></span>
        <span className="hidden w-56 shrink-0 text-xs text-slate-600 sm:block dark:text-slate-300">{c.actual && <b className="tabular-nums">{c.actual}</b>}{c.expected && <span className="text-slate-400"> · limit {c.expected}</span>}</span>
        {c.status === "fail" && <SeverityChip sev={c.severity} />}
        <span className="text-slate-400" aria-hidden>{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="space-y-2 border-t border-slate-100 px-3 py-2 text-sm dark:border-slate-700">
          {c.description && <p className="text-slate-600 dark:text-slate-300">{c.description}</p>}
          {c.excerpt && <p className="border-l-2 border-indigo-400 pl-2 text-slate-700 dark:text-slate-300">“{c.excerpt}” {c.page && <span className="text-xs text-slate-500">— page {c.page}</span>}</p>}
          {c.status === "fail" && c.suggested_text && <div className="rounded bg-emerald-50 p-2 dark:bg-emerald-950/40"><div className="text-[11px] font-semibold uppercase text-emerald-800 dark:text-emerald-300">Suggested wording</div><p>{c.suggested_text}</p></div>}
          {c.status === "na" && <p className="text-xs text-slate-500">Not applicable: the value or clause this rule needs is not in this document.</p>}
        </div>)}
    </li>
  );
}


function Upload({ onDone }: { onDone: (id: number | null) => void }) {
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const up = useMutation({
    mutationFn: async (f: File) => {
      const buf = new Uint8Array(await f.arrayBuffer());
      let bin = "";
      buf.forEach((b) => { bin += String.fromCharCode(b); });
      return api<{ contract_id: number | null }>("/api/redline/upload", { method: "POST", body: JSON.stringify({ filename: f.name, content_b64: btoa(bin) }) });
    },
    onSuccess: (r) => { qc.invalidateQueries(); onDone(r.contract_id); },
  });
  return (
    <div>
      <input ref={input} type="file" accept=".md,.txt,.docx,.html,.htm" className="hidden" aria-label="Upload a document to redline" onChange={(e) => { const f = e.target.files?.[0]; if (f) up.mutate(f); e.target.value = ""; }} />
      <button onClick={() => input.current?.click()} disabled={up.isPending} className="w-full rounded border border-dashed border-indigo-400 px-3 py-2 text-center text-sm font-medium text-indigo-700 hover:bg-indigo-50 dark:text-indigo-300 dark:hover:bg-slate-800">
        {up.isPending ? "Uploading & analysing…" : "⬆ Upload a document to redline (.docx, .md, .txt)"}</button>
      {up.error && <p className="mt-1 text-xs text-red-600">{String(up.error)}</p>}
    </div>
  );
}

export default function Redline() {
  const { id: idParam } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const [showExec, setShowExec] = useState(false);
  const [filter, setFilter] = useState<"all" | RStatus>("all");
  const [active, setActive] = useState<string | null>(null);
  const [tab, setTab] = useState<"doc" | "checklist">("doc");
  const [note, setNote] = useState("");
  const docs = useQuery({ queryKey: ["redline-docs"], queryFn: () => api<Doc[]>("/api/redline/documents") });
  const all = (docs.data ?? []).filter((d) => showExec || d.status === "draft");
  const list = all.filter((d) => filter === "all" || d.review_status === filter);
  const id = idParam ? Number(idParam) : list[0]?.id;
  useEffect(() => { if (!idParam && list[0]) nav(`/redline/${list[0].id}`, { replace: true }); }, [idParam, list[0]?.id]);   // eslint-disable-line react-hooks/exhaustive-deps
  const red = useQuery({ queryKey: ["redline", id], enabled: !!id, queryFn: () => api<Red>(`/api/redline/${id}`) });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["redline", id] }); qc.invalidateQueries({ queryKey: ["redline-docs"] }); };
  const rerun = useMutation({ mutationFn: () => api<Red>(`/api/redline/${id}/rerun`, { method: "POST" }), onSuccess: (d) => { qc.setQueryData(["redline", id], d); qc.invalidateQueries({ queryKey: ["redline-docs"] }); } });
  const decide = useMutation({ mutationFn: (v: { clause_type: string; decision: string | null }) => api(`/api/redline/${id}/decision`, { method: "PUT", body: JSON.stringify(v) }), onSuccess: refresh });
  const review = useMutation({ mutationFn: (status: RStatus) => api(`/api/redline/${id}/review`, { method: "PUT", body: JSON.stringify({ status, note: note || null }) }), onSuccess: refresh });
  const assign = useMutation({ mutationFn: (v: { assignee?: string; due_date?: string }) => api(`/api/redline/${id}/review`, { method: "PUT", body: JSON.stringify({ status: r?.review.status ?? "pending", ...v }) }), onSuccess: refresh });
  const apply = useMutation({ mutationFn: () => api<{ applied: number; version: number }>(`/api/redline/${id}/apply`, { method: "POST" }), onSuccess: () => { qc.invalidateQueries(); } });
  const [onlyFail, setOnlyFail] = useState(false);
  const r = red.data;
  const html = useMemo(() => (r ? trackedHtml(r.body_md, r.items, r.decisions) : ""), [r]);
  const counts = (["pending", "in_review", "changes_requested", "approved"] as RStatus[]).map((s) => [s, all.filter((d) => d.review_status === s).length] as const);
  const idx = list.findIndex((d) => d.id === id);
  const go = (d: number) => list[idx + d] && nav(`/redline/${list[idx + d].id}`);
  const accepted = r ? Object.values(r.decisions).filter((v) => v === "accepted").length : 0;
  return (
    <div className="grid gap-4 lg:grid-cols-4">
      <div className="space-y-2 lg:col-span-1">
        <h1 className="text-xl font-semibold">Review queue</h1>
        <p className="text-xs text-slate-500">Drafts dropped in the drafts folder are redlined automatically and wait here, one by one, for your review.</p>
        <div className="flex flex-wrap gap-1 text-xs" role="tablist" aria-label="Queue filter">
          <button role="tab" aria-selected={filter === "all"} onClick={() => setFilter("all")} className={`rounded px-2 py-0.5 ${filter === "all" ? "bg-indigo-600 text-white" : "bg-slate-200 dark:bg-slate-700"}`}>All {all.length}</button>
          {counts.map(([s, n]) => <button key={s} role="tab" aria-selected={filter === s} onClick={() => setFilter(s)} className={`rounded px-2 py-0.5 ${filter === s ? "bg-indigo-600 text-white" : STATUS[s].cls}`}>{STATUS[s].label} {n}</button>)}
        </div>
        <Upload onDone={(cid) => cid && nav(`/redline/${cid}`)} />
        <Link to="/new" className="block rounded border border-dashed border-slate-400 px-3 py-1.5 text-center text-sm text-slate-700 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-slate-800">+ New contract from a template</Link>
        <label className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300"><input type="checkbox" checked={showExec} onChange={(e) => setShowExec(e.target.checked)} /> Include executed contracts</label>
        {list.map((d) => (
          <button key={d.id} onClick={() => nav(`/redline/${d.id}`)} className={`block w-full rounded-lg border p-3 text-left ${d.id === id ? "border-indigo-600 bg-indigo-50 dark:bg-slate-700" : "border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-800"}`}>
            <div className="text-sm font-medium leading-snug">{d.title}</div>
            <div className="mt-1 flex flex-wrap items-center gap-1 text-xs text-slate-500">
              <span className="rounded bg-slate-200 px-1 font-semibold uppercase dark:bg-slate-700">{d.type}</span>
              <span className={`rounded px-1 font-medium ${STATUS[d.review_status].cls}`}>{STATUS[d.review_status].label}</span>
              {d.assignee && <span title={d.due_date ? `due ${d.due_date}` : undefined}>→ {d.assignee}{d.due_date ? ` · ${d.due_date}` : ""}</span>}
              {d.origin === "generated" && <span className="rounded border border-indigo-400 px-1 text-indigo-700 dark:text-indigo-300">from template</span>}
              {d.origin === "upload" && <span className="rounded border border-slate-400 px-1">uploaded</span>}
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-1 text-xs">
              {d.checks_failed === 0 && d.deviations === 0 ? <span className="rounded bg-emerald-100 px-1 text-emerald-900">✓ passes checklist, matches standard</span>
                : <>{d.checks_failed > 0 && <><span className="text-slate-500">checklist:</span>{chips(d.check_counts)}</>}{d.deviations > 0 && <><span className="ml-1 text-slate-500">changes:</span>{chips(d.counts)}</>}</>}
            </div>
          </button>))}
        {docs.data && list.length === 0 && <p className="text-sm text-slate-500">Nothing in this view. Upload a document, drop one in the drafts folder, or create a new contract.</p>}
      </div>

      <div className="space-y-4 lg:col-span-3">
        <Loading q={red} />
        {r && (
          <>
            <Card title={r.title} right={
              <div className="flex items-center gap-3 text-xs text-slate-500">
                <button className="rounded border border-slate-300 px-2 py-0.5 disabled:opacity-40 dark:border-slate-600" disabled={idx <= 0} onClick={() => go(-1)} aria-label="Previous document">← Prev</button>
                <span>{idx + 1} / {list.length}</span>
                <button className="rounded border border-slate-300 px-2 py-0.5 disabled:opacity-40 dark:border-slate-600" disabled={idx < 0 || idx >= list.length - 1} onClick={() => go(1)} aria-label="Next document">Next →</button>
                <button onClick={() => rerun.mutate()} disabled={rerun.isPending} className="rounded bg-indigo-600 px-3 py-1 text-sm font-medium text-white disabled:opacity-50">{rerun.isPending ? "Analysing…" : "Re-run live"}</button>
              </div>}>
              <p className="text-sm">
                {r.status === "draft" ? "Draft" : "Executed"} {r.type} · compared against <b>{r.template?.name ?? "the standard template"}</b> and the checklist.{" "}
                {r.checklist_summary.fail === 0 && r.items.length === 0 ? <b className="text-emerald-700 dark:text-emerald-400">Ready to sign: every applicable checklist rule passes and nothing differs from the standard.</b>
                  : <b>{r.checklist_summary.fail} checklist rule{r.checklist_summary.fail !== 1 ? "s" : ""} failed, {r.items.length} change{r.items.length !== 1 ? "s" : ""} from the standard{r.items.length ? `: ${ORDER.filter((s) => r.counts[s]).map((s) => `${r.counts[s]} ${s}`).join(", ")}` : ""}.</b>}
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3 dark:border-slate-700">
                <span className={`rounded px-2 py-0.5 text-xs font-semibold ${STATUS[r.review.status].cls}`} aria-label="Review status">{STATUS[r.review.status].label}</span>
                <input className={`${inputCls} max-w-xs`} aria-label="Review note" placeholder="Reviewer note (optional)" defaultValue={r.review.note ?? ""} key={`${r.id}-${r.review.updated_at}`} onChange={(e) => setNote(e.target.value)} />
                <Btn onClick={() => review.mutate("approved")} disabled={review.isPending}>✓ Approve</Btn>
                <Btn kind="ghost" onClick={() => review.mutate("changes_requested")} disabled={review.isPending}>Request changes</Btn>
                <Btn kind="ghost" onClick={() => review.mutate("pending")} disabled={review.isPending}>Reset</Btn>
                <input className={`${inputCls} w-32`} aria-label="Assignee" placeholder="Assign to…" defaultValue={r.review.assignee ?? ""} key={`a${r.id}-${r.review.assignee}`} onBlur={(e) => e.target.value !== (r.review.assignee ?? "") && assign.mutate({ assignee: e.target.value })} />
                <input className={`${inputCls} w-36`} type="date" aria-label="Review due date" defaultValue={r.review.due_date ?? ""} key={`d${r.id}-${r.review.due_date}`} onChange={(e) => e.target.value && assign.mutate({ due_date: e.target.value })} />
                {r.review.updated_at && <span className="text-xs text-slate-500">updated {when(r.review.updated_at)}</span>}
              </div>
            </Card>

            <div className="flex items-center gap-2" role="tablist">
              <button role="tab" aria-selected={tab === "doc"} onClick={() => setTab("doc")} className={`rounded-t px-3 py-1.5 text-sm font-medium ${tab === "doc" ? "bg-indigo-600 text-white" : "bg-slate-200 dark:bg-slate-700"}`}>Document with tracked changes ({r.items.length})</button>
              <button role="tab" aria-selected={tab === "checklist"} onClick={() => setTab("checklist")} className={`rounded-t px-3 py-1.5 text-sm font-medium ${tab === "checklist" ? "bg-indigo-600 text-white" : "bg-slate-200 dark:bg-slate-700"}`}>Pre-signature checklist ({r.checklist_summary.fail} failing)</button>
              <span className="ml-auto flex items-center gap-3 text-sm">
                {r.status === "draft" && <Link className="font-medium text-indigo-600 hover:underline" to={`/documents/${r.id}/edit`}>Edit in document editor</Link>}
                <a className="text-indigo-600 hover:underline" href={authUrl(`/api/redline/${r.id}/export.docx`)} download>⬇ Download with tracked changes (.docx)</a>
                <Link className="text-indigo-600 hover:underline" to={`/ask?doc=${r.id}`}>Ask about it</Link>
              </span>
            </div>

            {tab === "doc" && (
              <div className="grid gap-3 xl:grid-cols-3">
                <div className="overflow-hidden rounded-lg border border-slate-300 bg-slate-200 xl:col-span-2 dark:border-slate-600 dark:bg-slate-900">
                  <div className="flex items-center gap-2 border-b border-slate-300 bg-white px-3 py-1.5 text-sm dark:border-slate-600 dark:bg-slate-800">
                    <span className="grid h-6 w-6 place-items-center rounded bg-blue-600 text-xs font-bold text-white" aria-hidden>W</span><span className="font-medium">{r.title}</span>
                    <span className="ml-auto text-xs text-slate-500">Reviewing · <del className="tc text-red-700">removed</del> <ins className="tc text-emerald-700">added</ins> · click a change to see the comment</span>
                  </div>
                  <div className="max-h-[75vh] overflow-auto px-2 py-6 sm:px-6">
                    <div className="docpage mx-auto" aria-label="Document with tracked changes" role="document"
                      onClick={(e) => { const el = (e.target as HTMLElement).closest("[data-ct]"); if (el) { const ct = el.getAttribute("data-ct"); setActive(ct); document.getElementById(`cmt-${ct}`)?.scrollIntoView({ block: "nearest", behavior: "smooth" }); } }}
                      dangerouslySetInnerHTML={{ __html: html }} />
                  </div>
                </div>
                <div className="space-y-2">
                  <div className="flex items-center justify-between"><h2 className="text-sm font-semibold">Comments & changes</h2>
                    {r.status === "draft" && <Btn onClick={() => apply.mutate()} disabled={!accepted || apply.isPending}>{apply.isPending ? "Applying…" : `Apply ${accepted} accepted → new version`}</Btn>}</div>
                  {apply.error && <p className="text-xs text-red-600">{String(apply.error)}</p>}
                  {apply.data && <p className="text-xs text-emerald-700">✓ {apply.data.applied} change(s) written to the document as version {apply.data.version}; re-checked.</p>}
                  {r.items.length === 0 && <p className="rounded border border-emerald-300 bg-emerald-50 p-3 text-sm text-emerald-900">No deviations — this document matches the standard.</p>}
                  {r.items.map((i) => {
                    const d = r.decisions[i.clause_type];
                    return (
                      <div key={i.clause_type} id={`cmt-${i.clause_type}`} className={`rounded-lg border bg-white p-3 text-sm dark:bg-slate-800 ${active === i.clause_type ? "border-indigo-500 ring-1 ring-indigo-500" : "border-slate-200 dark:border-slate-700"} ${sevStripe(i.severity)}`}>
                        <div className="flex flex-wrap items-center gap-2"><b>{i.heading}</b><SeverityChip sev={i.severity} />
                          {i.status === "missing" && <span className="rounded border border-red-500 px-1 text-xs text-red-700 dark:text-red-300">MISSING</span>}
                          {i.page && <span className="text-xs text-slate-500">p.{i.page}</span>}</div>
                        <p className="mt-1">{i.deviation}</p>
                        <p className="mt-1 text-xs text-slate-500"><b>Our standard:</b> {i.standard_position}</p>
                        <div className="mt-2 flex items-center gap-2">
                          <button onClick={() => decide.mutate({ clause_type: i.clause_type, decision: d === "accepted" ? null : "accepted" })} aria-pressed={d === "accepted"} className={`rounded px-2 py-0.5 text-xs font-medium ${d === "accepted" ? "bg-emerald-600 text-white" : "border border-emerald-600 text-emerald-700"}`}>✓ Accept</button>
                          <button onClick={() => decide.mutate({ clause_type: i.clause_type, decision: d === "rejected" ? null : "rejected" })} aria-pressed={d === "rejected"} className={`rounded px-2 py-0.5 text-xs font-medium ${d === "rejected" ? "bg-slate-600 text-white" : "border border-slate-400 text-slate-700 dark:text-slate-300"}`}>✗ Reject</button>
                          {d && <span className="text-xs text-slate-500">{d}</span>}
                        </div>
                      </div>);
                  })}
                </div>
              </div>)}

            {tab === "checklist" && (
              <Card title={`Pre-signature checklist — ${r.checklist_summary.pass} pass · ${r.checklist_summary.fail} fail · ${r.checklist_summary.na} n/a`}
                right={<label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={onlyFail} onChange={(e) => setOnlyFail(e.target.checked)} /> Failures only</label>}>
                <ul className="space-y-1.5">
                  {r.checklist.filter((c) => !onlyFail || c.status === "fail").map((c) => <CheckRow key={c.rule_key} c={c} />)}
                  {r.checklist.length === 0 && <li className="text-sm text-slate-500">No checklist rules apply to this document type.</li>}
                </ul>
              </Card>)}
          </>
        )}
      </div>
    </div>
  );
}
