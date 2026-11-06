import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../lib";
import { Card, Loading, Sev, SeverityChip, sevStripe } from "../ui";

type Item = { clause_type: string; heading: string; status: "changed" | "missing"; draft_text: string; standard_position: string; deviation: string;
  severity: Sev; suggested_text: string; diff: [string, string][]; page: number | null };
type Draft = { id: number; title: string; vendor: string; template_type: string; deviations: number; counts: Record<Sev, number> };
type Red = { id: number; title: string; template: { name: string }; items: Item[]; counts: Record<Sev, number>; source: string; elapsed_ms?: number };

function Diff({ ops }: { ops: [string, string][] }) {
  return (
    <p className="leading-relaxed">
      {ops.map(([op, t], i) => op === "del" ? <del key={i} className="mr-1 rounded bg-red-100 px-0.5 text-red-800 dark:bg-red-950 dark:text-red-300">{t}</del>
        : op === "ins" ? <ins key={i} className="mr-1 rounded bg-emerald-100 px-0.5 text-emerald-800 no-underline dark:bg-emerald-950 dark:text-emerald-300" style={{ textDecoration: "underline" }}>{t}</ins>
        : <span key={i} className="mr-1">{t}</span>)}
    </p>
  );
}

export default function Redline() {
  const qc = useQueryClient();
  const drafts = useQuery({ queryKey: ["drafts"], queryFn: () => api<Draft[]>("/api/drafts") });
  const [sel, setSel] = useState<number | null>(null);
  const id = sel ?? drafts.data?.[0]?.id;
  const red = useQuery({ queryKey: ["redline", id], enabled: !!id, queryFn: () => api<Red>(`/api/drafts/${id}/redline`) });
  const rerun = useMutation({
    mutationFn: () => api<Red>(`/api/drafts/${id}/redline/rerun`, { method: "POST" }),
    onSuccess: (d) => { qc.setQueryData(["redline", id], d); qc.invalidateQueries({ queryKey: ["drafts"] }); },
  });
  const r = red.data;
  return (
    <div className="grid gap-4 lg:grid-cols-4">
      <div className="space-y-2 lg:col-span-1">
        <h1 className="text-xl font-semibold">Vendor drafts</h1>
        {drafts.data?.map((d) => (
          <button key={d.id} onClick={() => setSel(d.id)} className={`block w-full rounded-lg border p-3 text-left ${d.id === id ? "border-indigo-600 bg-indigo-50 dark:bg-slate-700" : "border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-800"}`}>
            <div className="text-sm font-medium">{d.title}</div>
            <div className="mt-1 flex flex-wrap items-center gap-1 text-xs text-slate-500">{d.template_type} template ·
              {d.deviations === 0 ? <span className="rounded bg-emerald-100 px-1 text-emerald-900">✓ no deviations</span>
                : (["critical", "high", "medium", "low"] as Sev[]).filter((s) => d.counts[s]).map((s) => <SeverityChip key={s} sev={s} label={String(d.counts[s])} />)}
            </div>
          </button>))}
      </div>
      <div className="space-y-4 lg:col-span-3">
        <Loading q={red} />
        {r && (
          <>
            <Card title={r.title} right={
              <div className="flex items-center gap-3 text-xs text-slate-500">
                <span>{r.source === "cached" ? "Cached result" : `Live (${r.source})${r.elapsed_ms ? ` · ${(r.elapsed_ms / 1000).toFixed(1)}s` : ""}`}</span>
                <button onClick={() => rerun.mutate()} disabled={rerun.isPending} className="rounded bg-indigo-600 px-3 py-1 text-sm font-medium text-white disabled:opacity-50">{rerun.isPending ? "Analysing…" : "Re-run live"}</button>
              </div>}>
              <p className="text-sm">Compared against <b>{r.template.name}</b> and the negotiation playbook.{" "}
                {r.items.length === 0 ? <b className="text-emerald-700 dark:text-emerald-400">No deviations found — this draft matches the standard.</b>
                  : <b>{r.items.length} deviations: {(["critical", "high", "medium", "low"] as Sev[]).filter((s) => r.counts[s]).map((s) => `${r.counts[s]} ${s}`).join(", ")}.</b>}</p>
            </Card>
            {r.items.map((i) => (
              <div key={i.clause_type} className={`rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800 ${sevStripe(i.severity)}`}>
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <h3 className="font-semibold">{i.heading}</h3><SeverityChip sev={i.severity} />
                  {i.status === "missing" && <span className="rounded border border-red-500 px-1 text-xs text-red-700 dark:text-red-300">MISSING CLAUSE</span>}
                  {i.page && <span className="text-xs text-slate-500">draft p.{i.page}</span>}
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
