import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../lib";
import { Card, Loading, Sev, SeverityChip, sevStripe } from "../ui";

type Doc = { id: number; title: string; vendor: string; type: string; status: string; origin: string; deviations: number; counts: Record<Sev, number>; checks_failed: number; check_counts: Record<Sev, number> };
type Item = { clause_type: string; heading: string; status: "changed" | "missing"; draft_text: string; standard_position: string; deviation: string; severity: Sev; suggested_text: string; diff: [string, string][]; page: number | null };
type Check = { rule_key: string; name: string; description: string | null; status: "pass" | "fail" | "na"; severity: Sev; actual: string | null; expected: string | null; page: number | null; excerpt: string | null; suggested_text: string | null };
type Red = { id: number; title: string; vendor: string; type: string; status: string; template: { name: string } | null; items: Item[]; counts: Record<Sev, number>; source: string; elapsed_ms?: number;
  checklist: Check[]; checklist_summary: { pass: number; fail: number; na: number }; checklist_fail_counts: Record<Sev, number> };

const ORDER: Sev[] = ["critical", "high", "medium", "low"];
const chips = (c: Record<Sev, number>) => ORDER.filter((s) => c[s]).map((s) => <SeverityChip key={s} sev={s} label={String(c[s])} />);

function Diff({ ops }: { ops: [string, string][] }) {
  return (
    <p className="leading-relaxed">
      {ops.map(([op, t], i) => op === "del" ? <del key={i} className="mr-1 rounded bg-red-100 px-0.5 text-red-800 dark:bg-red-950 dark:text-red-300">{t}</del>
        : op === "ins" ? <ins key={i} className="mr-1 rounded bg-emerald-100 px-0.5 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300" style={{ textDecoration: "underline" }}>{t}</ins>
        : <span key={i} className="mr-1">{t}</span>)}
    </p>
  );
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

export default function Redline() {
  const { id: idParam } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const [showExec, setShowExec] = useState(false);
  const docs = useQuery({ queryKey: ["redline-docs"], queryFn: () => api<Doc[]>("/api/redline/documents") });
  const list = (docs.data ?? []).filter((d) => showExec || d.status === "draft");
  const id = idParam ? Number(idParam) : list[0]?.id;
  const red = useQuery({ queryKey: ["redline", id], enabled: !!id, queryFn: () => api<Red>(`/api/redline/${id}`) });
  const rerun = useMutation({
    mutationFn: () => api<Red>(`/api/redline/${id}/rerun`, { method: "POST" }),
    onSuccess: (d) => { qc.setQueryData(["redline", id], d); qc.invalidateQueries({ queryKey: ["redline-docs"] }); },
  });
  const [onlyFail, setOnlyFail] = useState(false);
  const r = red.data;
  return (
    <div className="grid gap-4 lg:grid-cols-4">
      <div className="space-y-2 lg:col-span-1">
        <div className="flex items-center justify-between"><h1 className="text-xl font-semibold">Review before signing</h1></div>
        <label className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300"><input type="checkbox" checked={showExec} onChange={(e) => setShowExec(e.target.checked)} /> Include executed contracts</label>
        <Link to="/new" className="block rounded border border-dashed border-indigo-400 px-3 py-2 text-center text-sm font-medium text-indigo-700 hover:bg-indigo-50 dark:text-indigo-300 dark:hover:bg-slate-800">+ New contract from a template</Link>
        {list.map((d) => (
          <button key={d.id} onClick={() => nav(`/redline/${d.id}`)} className={`block w-full rounded-lg border p-3 text-left ${d.id === id ? "border-indigo-600 bg-indigo-50 dark:bg-slate-700" : "border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-800"}`}>
            <div className="text-sm font-medium leading-snug">{d.title}</div>
            <div className="mt-1 flex flex-wrap items-center gap-1 text-xs text-slate-500">
              <span className="rounded bg-slate-200 px-1 font-semibold uppercase dark:bg-slate-700">{d.type}</span>{d.status === "draft" ? "draft" : "executed"}{d.origin === "generated" && <span className="rounded border border-indigo-400 px-1 text-indigo-700 dark:text-indigo-300">from template</span>}
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-1 text-xs">
              {d.checks_failed === 0 && d.deviations === 0 ? <span className="rounded bg-emerald-100 px-1 text-emerald-900">✓ passes checklist, matches standard</span>
                : <>{d.checks_failed > 0 && <><span className="text-slate-500">checklist:</span>{chips(d.check_counts)}</>}{d.deviations > 0 && <><span className="ml-1 text-slate-500">changes:</span>{chips(d.counts)}</>}</>}
            </div>
          </button>))}
        {docs.data && list.length === 0 && <p className="text-sm text-slate-500">No drafts to review. Tick “Include executed contracts” or create a new contract.</p>}
      </div>

      <div className="space-y-4 lg:col-span-3">
        <Loading q={red} />
        {r && (
          <>
            <Card title={r.title} right={
              <div className="flex items-center gap-3 text-xs text-slate-500">
                <Link className="text-indigo-600 hover:underline" to={`/contracts/${r.id}`}>Open document</Link>
                <Link className="text-indigo-600 hover:underline" to={`/ask?doc=${r.id}`}>Ask about it</Link>
                <span>{r.source === "cached" ? "Cached result" : `Live (${r.source})${r.elapsed_ms ? ` · ${(r.elapsed_ms / 1000).toFixed(1)}s` : ""}`}</span>
                <button onClick={() => rerun.mutate()} disabled={rerun.isPending} className="rounded bg-indigo-600 px-3 py-1 text-sm font-medium text-white disabled:opacity-50">{rerun.isPending ? "Analysing…" : "Re-run live"}</button>
              </div>}>
              <p className="text-sm">
                {r.status === "draft" ? "Draft" : "Executed"} {r.type} · compared against <b>{r.template?.name ?? "the standard template"}</b> and the checklist.{" "}
                {r.checklist_summary.fail === 0 && r.items.length === 0 ? <b className="text-emerald-700 dark:text-emerald-400">Ready to sign: every applicable checklist rule passes and nothing differs from the standard.</b>
                  : <b>{r.checklist_summary.fail} checklist rule{r.checklist_summary.fail !== 1 ? "s" : ""} failed, {r.items.length} change{r.items.length !== 1 ? "s" : ""} from the standard{r.items.length ? `: ${ORDER.filter((s) => r.counts[s]).map((s) => `${r.counts[s]} ${s}`).join(", ")}` : ""}.</b>}
              </p>
            </Card>

            <Card title={`Pre-signature checklist — ${r.checklist_summary.pass} pass · ${r.checklist_summary.fail} fail · ${r.checklist_summary.na} n/a`}
              right={<label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={onlyFail} onChange={(e) => setOnlyFail(e.target.checked)} /> Failures only</label>}>
              <ul className="space-y-1.5">
                {r.checklist.filter((c) => !onlyFail || c.status === "fail").map((c) => <CheckRow key={c.rule_key} c={c} />)}
                {r.checklist.length === 0 && <li className="text-sm text-slate-500">No checklist rules apply to this document type.</li>}
              </ul>
            </Card>

            <h2 className="text-lg font-semibold">Changes from the standard template</h2>
            {r.items.length === 0 && <p className="text-sm text-slate-600 dark:text-slate-300">No deviations found — this document matches the standard.</p>}
            {r.items.map((i) => (
              <div key={i.clause_type} className={`rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800 ${sevStripe(i.severity)}`}>
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <h3 className="font-semibold">{i.heading}</h3><SeverityChip sev={i.severity} />
                  {i.status === "missing" && <span className="rounded border border-red-500 px-1 text-xs text-red-700 dark:text-red-300">MISSING CLAUSE</span>}
                  {i.page && <span className="text-xs text-slate-500">page {i.page}</span>}
                </div>
                <p className="mb-2 text-sm">{i.deviation}</p>
                <div className="rounded bg-slate-50 p-3 text-sm dark:bg-slate-900"><div className="mb-1 text-[11px] font-semibold uppercase text-slate-500">Redline — original struck through, suggested wording inserted</div><Diff ops={i.diff} /></div>
                <p className="mt-2 text-xs text-slate-500"><b>Our standard position:</b> {i.standard_position}</p>
              </div>))}
          </>
        )}
      </div>
    </div>
  );
}
