import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../lib";
import { Tile } from "../components/vmo";
import { Card, Loading } from "../ui";

type Cell = { present: boolean; expected: boolean; heading: string; page: number | null; text: string | null; note: string | null };
type Row = { id: number; title: string; vendor: string; type: string; kind: "contract" | "draft"; cells: Record<string, Cell>; present_count: number; gap_count: number };
type M = { columns: { key: string; label: string }[]; groups: { name: string; rows: Row[] }[]; totals: Record<string, number>; executed_count: number };

export function ClauseMatrix({ vendor }: { vendor?: string }) {
  const q = useQuery({ queryKey: ["matrix", vendor ?? ""], queryFn: () => api<M>(`/api/clause-matrix${vendor ? `?vendor=${encodeURIComponent(vendor)}` : ""}`) });
  const [tip, setTip] = useState<{ row: Row; col: string; x: number; y: number } | null>(null);
  const [onlyGaps, setOnlyGaps] = useState(false);
  const nav = useNavigate();
  if (!q.data) return <Loading q={q} />;
  const m = q.data;
  const label = (k: string) => m.columns.find((c) => c.key === k)!.label;
  const cell = tip ? tip.row.cells[tip.col] : null;
  const execRows = m.groups.filter((g) => g.rows.some((r) => r.kind === "contract")).flatMap((g) => g.rows.filter((r) => r.kind === "contract"));
  const expected = execRows.reduce((a, r) => a + Object.values(r.cells).filter((c) => c.expected).length, 0);
  const present = execRows.reduce((a, r) => a + Object.values(r.cells).filter((c) => c.expected && c.present).length, 0);
  const gaps = execRows.reduce((a, r) => a + r.gap_count, 0), gapDocs = execRows.filter((r) => r.gap_count > 0).length;
  return (
    <div className="space-y-4">
      {!vendor && (
        <div className="grid gap-3 sm:grid-cols-3">
          <Tile l="Coverage" v={expected ? `${Math.round((present / expected) * 100)}%` : "—"} sub="of required clauses present" />
          <Tile l="Gaps to fix" v={gaps} tone={gaps ? "red" : undefined} sub={`across ${gapDocs} contract${gapDocs === 1 ? "" : "s"}`} />
          <Tile l="Clauses tracked" v={m.columns.length} sub="columns; add more in Admin" />
        </div>)}
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          {vendor ? <h2 className="text-lg font-semibold">Key clauses in {vendor}&rsquo;s documents</h2> : <h1>Key contract clauses across all documents</h1>}
          <p className="text-sm text-slate-500">One row per document, one column per key clause. Hover a mark to see the citation (or why it is absent); click it to open the contract. Clauses you add in Admin appear as new columns, tagged by heading, keyword or (with Claude) by meaning.</p>
        </div>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={onlyGaps} onChange={(e) => setOnlyGaps(e.target.checked)} /> Highlight gaps only</label>
      </div>
      <Card>
        <div className="mb-3 flex flex-wrap items-center gap-4 text-sm">
          <span><b className="text-lg text-emerald-600">✓</b> present</span>
          <span><b className="text-lg text-red-600">✗</b> absent</span>
          <span className="rounded bg-red-100 px-1.5 text-red-900 ring-1 ring-red-400 dark:bg-red-950 dark:text-red-200">boxed ✗ = a gap: the standard template requires it</span>
          <span className="text-slate-500">plain ✗ = not part of that document type</span>
        </div>
        <div className="overflow-x-auto">
          <table className="border-separate border-spacing-0 text-sm">
            <thead>
              <tr>
                <th className="sticky left-0 z-10 min-w-[19rem] bg-white p-2 text-left align-bottom dark:bg-slate-800">Document</th>
                {m.columns.map((c) => <th key={c.key} className="h-36 w-9 align-bottom"><div className="w-9 origin-bottom-left -rotate-[60deg] whitespace-nowrap pb-1 text-left text-xs font-medium">{c.label}</div></th>)}
                <th className="p-2 text-left align-bottom text-xs">Present</th>
              </tr>
            </thead>
            {m.groups.filter((g) => g.rows.length > 0).map((g) => (
              <tbody key={g.name}>
                <tr><td colSpan={m.columns.length + 2} className="bg-slate-100 p-2 text-xs font-semibold uppercase tracking-wide text-slate-600 dark:bg-slate-900 dark:text-slate-300">{g.name} ({g.rows.length})</td></tr>
                {g.rows.map((r) => (
                  <tr key={r.kind + r.id} className="group hover:bg-indigo-50/60 dark:hover:bg-slate-700/40">
                    <td className="sticky left-0 z-10 border-t border-slate-100 bg-white p-2 dark:border-slate-700 dark:bg-slate-800">
                      {r.kind === "contract"
                        ? <Link to={`/contracts/${r.id}`} className="font-medium text-indigo-600 hover:underline dark:text-indigo-400">{r.title}</Link>
                        : <Link to="/redline" className="font-medium text-indigo-600 hover:underline dark:text-indigo-400">{r.title}</Link>}
                      <div className="text-xs text-slate-500"><span className="mr-1 rounded bg-slate-200 px-1 text-[10px] dark:bg-slate-700">{r.type}</span>{r.vendor}</div>
                    </td>
                    {m.columns.map((c) => {
                      const ce = r.cells[c.key];
                      const gap = !ce.present && ce.expected && !(r.kind === "draft" && c.key === "execution");
                      return (
                        <td key={c.key} className="border-t border-slate-100 p-0.5 text-center dark:border-slate-700"
                          onMouseEnter={(e) => { const b = (e.currentTarget as HTMLElement).getBoundingClientRect(); setTip({ row: r, col: c.key, x: b.left + b.width / 2, y: b.top }); }}
                          onMouseLeave={() => setTip(null)}>
                          <button type="button" onClick={() => r.kind === "contract" && nav(`/contracts/${r.id}`)} aria-label={`${r.title}: ${c.label} ${ce.present ? "present" : "absent"}`}
                            onFocus={(e) => { const b = e.currentTarget.getBoundingClientRect(); setTip({ row: r, col: c.key, x: b.left + b.width / 2, y: b.top }); }} onBlur={() => setTip(null)}
                            className={`h-7 w-8 rounded text-base font-bold ${ce.present ? "text-emerald-600" : gap ? "bg-red-100 text-red-700 ring-1 ring-red-400 dark:bg-red-950 dark:text-red-300" : "text-red-400"} ${onlyGaps && !gap ? "opacity-20" : ""}`}>
                            {ce.present ? "✓" : "✗"}
                          </button>
                        </td>
                      );
                    })}
                    <td className="border-t border-slate-100 p-2 text-xs tabular-nums dark:border-slate-700">{r.present_count}/{m.columns.length}{r.gap_count > 0 && <span className="ml-1 font-semibold text-red-600">· {r.gap_count} gap{r.gap_count > 1 ? "s" : ""}</span>}</td>
                  </tr>
                ))}
              </tbody>
            ))}
            <tfoot><tr><td className="sticky left-0 bg-white p-2 text-xs font-semibold dark:bg-slate-800">Present in executed contracts</td>
              {m.columns.map((c) => <td key={c.key} className="p-0.5 text-center text-[11px] tabular-nums text-slate-500">{m.totals[c.key]}/{m.executed_count}</td>)}<td /></tr></tfoot>
          </table>
        </div>
      </Card>
      {!vendor && gaps > 0 && (
        <Card title={`Gaps to fix (${gaps})`}>
          <ul className="divide-y divide-slate-100 text-sm dark:divide-slate-700">
            {execRows.flatMap((r) => Object.entries(r.cells).filter(([, c]) => c.expected && !c.present).map(([k, c]) => ({ r, k, c }))).slice(0, 8).map(({ r, k, c }) => (
              <li key={`${r.id}-${k}`} className="flex flex-wrap items-center gap-3 py-2">
                <span className="rounded bg-red-100 px-1.5 text-xs font-semibold text-red-900 ring-1 ring-red-300">◆ Gap</span>
                <span className="min-w-0 flex-1"><b>{r.title}</b> · {label(k)}<span className="block text-xs text-slate-500">{c.note ?? "Required by the standard template, not found in the document."}</span></span>
                <Link className="text-indigo-600 hover:underline" to={`/contracts/${r.id}`}>Open contract</Link>
              </li>))}
          </ul>
          {gaps > 8 && <p className="mt-2 text-xs text-slate-500">Showing 8 of {gaps}. Tick “Highlight gaps only” to scan the matrix.</p>}
        </Card>)}
      {tip && cell && (
        <div role="tooltip" className="pointer-events-none fixed z-50 w-96 max-w-[90vw] -translate-x-1/2 -translate-y-full rounded-lg border border-slate-300 bg-white p-3 text-sm shadow-xl dark:border-slate-600 dark:bg-slate-900"
          style={{ left: Math.min(Math.max(tip.x, 200), window.innerWidth - 200), top: tip.y - 8 }}>
          <div className="flex items-center gap-2"><b className={cell.present ? "text-emerald-600" : "text-red-600"}>{cell.present ? "✓ Present" : "✗ Absent"}</b><span className="font-semibold">{label(tip.col)}</span></div>
          <div className="text-xs text-slate-500">{tip.row.title}</div>
          {cell.text && <p className="mt-2 border-l-2 border-indigo-400 pl-2 text-slate-700 dark:text-slate-300">“{cell.text}”</p>}
          {cell.page && <div className="mt-1 text-xs text-slate-500">Citation: {cell.heading} · page {cell.page}</div>}
          {cell.note && <p className="mt-2 text-slate-700 dark:text-slate-300">{cell.note}</p>}
        </div>
      )}
    </div>
  );
}

export default function Clauses() {
  return <ClauseMatrix />;
}
