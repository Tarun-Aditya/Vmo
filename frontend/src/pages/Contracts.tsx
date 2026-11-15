import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Link } from "react-router-dom";
import { api, fmtDate, usd } from "../lib";
import { Card, Loading, SeverityChip, Td, Th, useCurrentProperty } from "../ui";

type Row = { id: number; title: string; vendor: string; category: string; type: string; owner: string; property?: string | null; status: string; parent_id: number | null;
  effective_date: string | null; expiry_date: string | null; annual_value: number | null; total_value: number | null; auto_renew: boolean;
  liability_uncapped: boolean; deviation_count: number; fully_executed: boolean; customer_signatory: string | null; supplier_signatory: string | null;
  notice_period_days?: number | null; payment_terms_days?: number | null; liability_cap_multiple?: number | null; liability_cap_text?: string | null;
  termination_for_convenience?: boolean | null; governing_law?: string | null; act_by?: string | null };
const FILTERS = ["vendor", "category", "type", "owner", "property", "status"] as const;
const RANK: Record<string, number> = { MSA: 0, SaaS: 0, SOW: 1, "Work Order": 2, Amendment: 3, NDA: 4, DPA: 5 };
const TYPE_STYLE: Record<string, string> = {
  MSA: "bg-indigo-600 text-white", SaaS: "bg-indigo-600 text-white", SOW: "bg-sky-600 text-white", "Work Order": "bg-teal-600 text-white",
  Amendment: "bg-amber-500 text-black", NDA: "bg-slate-500 text-white", DPA: "bg-slate-500 text-white",
};

const TypeBadge = ({ t }: { t: string }) => <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${TYPE_STYLE[t] ?? "bg-slate-300"}`}>{t}</span>;
const Signed = ({ c }: { c: Row }) => c.fully_executed
  ? <span className="font-bold text-emerald-600" title={`Signed by ${c.customer_signatory} and ${c.supplier_signatory}`}>✓ signed</span>
  : <span className="font-bold text-red-600" title={`Awaiting ${c.supplier_signatory ? "Arcadia" : "Supplier"} signature`}>✗ pending</span>;
const Flags = ({ c }: { c: Row }) => (
  <div className="flex flex-wrap gap-1">
    {c.liability_uncapped && <SeverityChip sev="critical" label="uncapped" />}
    {c.auto_renew && <span className="rounded border border-slate-400 px-1 text-xs">auto-renew</span>}
    {c.deviation_count > 0 && <span className="rounded border border-slate-400 px-1 text-xs">{c.deviation_count} deviations</span>}
  </div>
);

type Node = Row & { children: Node[] };

function TreeNode({ n, depth }: { n: Node; depth: number }) {
  const [open, setOpen] = useState(true);
  return (
    <div>
      <div className="flex items-center gap-3 border-t border-slate-100 py-1.5 text-sm hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-700/40" style={{ paddingLeft: depth * 24 + 8 }}>
        <button onClick={() => setOpen(!open)} className="w-4 text-slate-400" aria-label={open ? "collapse" : "expand"} disabled={!n.children.length}>{n.children.length ? (open ? "▾" : "▸") : "·"}</button>
        <TypeBadge t={n.type} />
        <Link to={`/contracts/${n.id}`} className="min-w-0 flex-1 truncate font-medium text-indigo-600 hover:underline dark:text-indigo-400">{n.title}</Link>
        <span className="hidden w-52 shrink-0 text-xs tabular-nums text-slate-500 md:block">{fmtDate(n.effective_date)} → {fmtDate(n.expiry_date)}</span>
        <span className="hidden w-24 shrink-0 text-right tabular-nums lg:block">{n.annual_value ? usd(n.annual_value) : n.total_value ? `${usd(n.total_value)} fixed` : "—"}</span>
        <span className="hidden w-24 shrink-0 text-xs sm:block"><Signed c={n} /></span>
        <span className="hidden w-48 shrink-0 xl:block"><Flags c={n} /></span>
      </div>
      {open && n.children.map((c) => <TreeNode key={c.id} n={c} depth={depth + 1} />)}
    </div>
  );
}

export function Hierarchy({ rows }: { rows: Row[] }) {
  const forest = useMemo(() => {
    const byId = new Map<number, Node>(rows.map((r) => [r.id, { ...r, children: [] }]));
    const roots: Node[] = [];
    byId.forEach((n) => { const p = n.parent_id ? byId.get(n.parent_id) : undefined; (p ? p.children : roots).push(n); });
    const sort = (a: Node, b: Node) => (RANK[a.type] ?? 9) - (RANK[b.type] ?? 9) || a.title.localeCompare(b.title);
    byId.forEach((n) => n.children.sort(sort));
    const groups = new Map<string, Node[]>();
    roots.sort(sort).forEach((r) => groups.set(r.vendor, [...(groups.get(r.vendor) ?? []), r]));
    return [...groups.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [rows]);
  return (
    <div className="space-y-4">
      <p className="text-xs text-slate-500">MSA → SOW → Work Order · amendments, NDAs and DPAs sit under the agreement they belong to. Dates show start → end (effective, after amendments).</p>
      {forest.map(([vendor, nodes]) => (
        <Card key={vendor} title={<Link to={`/vendors/${encodeURIComponent(vendor)}`} className="hover:underline">{vendor}</Link>}>{nodes.map((n) => <TreeNode key={n.id} n={n} depth={0} />)}</Card>
      ))}
    </div>
  );
}

type Insp = { contract: { id: number; title: string; vendor: string; type: string; status: string }; fields: { field: string; value: string | null; confidence: number | null; source_page: number | null }[];
  checks: { rule_key: string; name: string; status: string; severity: string }[] };
const SHOW: [string, string][] = [["effective_date", "Effective"], ["expiry_date", "Expires"], ["liability_cap_text", "Liability"], ["termination_for_convenience", "Termination for convenience"], ["payment_terms_days", "Payment terms (days)"], ["governing_law", "Governing law"], ["auto_renew", "Auto-renew"]];

/** Right-hand panel for the selected row: the fields a VMO scans for, with their confidence. */
function Inspector({ id }: { id: number | null }) {
  const q = useQuery({ queryKey: ["contract", String(id)], enabled: id !== null, queryFn: () => api<Insp>(`/api/contracts/${id}`) });
  if (id === null) return <aside className="flex-[1_1_320px] rounded-lg border border-dashed border-line p-6 text-sm text-ink-mute dark:border-slate-700">Select a contract to see its key terms here.</aside>;
  if (!q.data) return <aside className="flex-[1_1_320px] p-4 text-sm text-ink-mute">Loading…</aside>;
  const d = q.data, fail = d.checks.filter((c) => c.status === "fail").length;
  const val = (f: string, v: string | null) => (v === null || v === "null" ? "—" : f.endsWith("_date") ? fmtDate(v) : v === "True" || v === "true" ? "Yes" : v === "False" || v === "false" ? "No" : v);
  return (
    <aside className="min-w-0 flex-[1_1_320px] rounded-lg border border-line bg-white dark:border-slate-700 dark:bg-slate-800" aria-label="Inspector">
      <div className="border-b border-line p-4 dark:border-slate-700"><div className="text-[11.5px] font-semibold uppercase tracking-wider text-ink-mute">Selected</div><div className="font-semibold">{d.contract.title}</div><div className="text-sm text-ink-mute">{d.contract.vendor} · {d.contract.type}</div></div>
      <dl className="space-y-2 p-4 text-[13px]">
        {SHOW.map(([f, l]) => { const x = d.fields.find((y) => y.field === f); return x ? <div key={f} className="flex justify-between gap-3"><dt className="text-ink-mute">{l}</dt><dd className="num text-right">{val(f, x.value)}{x.confidence !== null && x.confidence < 0.7 && <span className="ml-1 rounded bg-amber-100 px-1 text-[10px] font-semibold text-amber-900" title="Low confidence">check</span>}</dd></div> : null; })}
        <div className="flex justify-between gap-3"><dt className="text-ink-mute">Checklist</dt><dd>{fail ? <span className="font-semibold text-red-700">{fail} failing</span> : <span className="font-semibold text-indigo-700">all passing</span>}</dd></div>
      </dl>
      <div className="flex gap-2 border-t border-line p-4 dark:border-slate-700"><Link to={`/contracts/${id}`} className="inline-flex min-h-[32px] items-center rounded-md border border-indigo-600 bg-indigo-600 px-3 text-[12.5px] font-semibold text-white">Open workspace</Link>
        <Link to={`/ask?doc=${id}`} className="inline-flex min-h-[32px] items-center rounded-md border border-slate-300 px-3 text-[12.5px] font-semibold dark:border-slate-600">Ask about it</Link></div>
    </aside>
  );
}

/** The repository: each agreement with what hangs off it (schedules, work orders, amendments, NDAs, DPAs) beneath it, and the terms a VMO scans for. */
function flatten(rows: Row[], collapsed: Set<number>): { r: Row; depth: number; kids: number }[] {
  const ids = new Set(rows.map((r) => r.id));
  const kids = new Map<number, Row[]>();
  const roots: Row[] = [];
  rows.forEach((r) => (r.parent_id && ids.has(r.parent_id) ? kids.set(r.parent_id, [...(kids.get(r.parent_id) ?? []), r]) : roots.push(r)));
  const sort = (a: Row, b: Row) => (RANK[a.type] ?? 9) - (RANK[b.type] ?? 9) || a.title.localeCompare(b.title);
  roots.sort((a, b) => a.vendor.localeCompare(b.vendor) || sort(a, b));
  const out: { r: Row; depth: number; kids: number }[] = [];
  const walk = (r: Row, depth: number) => {
    const ch = (kids.get(r.id) ?? []).sort(sort);
    out.push({ r, depth, kids: ch.length });
    if (!collapsed.has(r.id)) ch.forEach((c) => walk(c, depth + 1));
  };
  roots.forEach((r) => walk(r, 0));
  return out;
}

const cap = (c: Row) => c.liability_uncapped || c.liability_cap_text === "Unlimited" ? <SeverityChip sev="critical" label="uncapped" />
  : c.liability_cap_multiple ? <span className="tabular-nums">{Number(c.liability_cap_multiple)}× fees</span>
  : c.liability_cap_text ? <span className="text-xs text-slate-500">{c.liability_cap_text}</span> : <span className="text-slate-400">—</span>;
const actBy = (c: Row) => {
  if (!c.act_by) return <span className="text-slate-400">—</span>;
  const days = Math.round((new Date(c.act_by + "T00:00:00").getTime() - Date.now()) / 864e5);
  const cls = c.auto_renew && days < 0 && c.expiry_date && new Date(c.expiry_date) > new Date() ? "font-semibold text-red-700 dark:text-red-300" : days >= 0 && days <= 30 ? "font-semibold text-orange-700 dark:text-orange-300" : "";
  return <span className={`whitespace-nowrap tabular-nums ${cls}`} title={c.auto_renew ? `Notice to stop the renewal: ${c.notice_period_days} days before the end` : "Ends; no automatic renewal"}>{fmtDate(c.act_by)}{c.auto_renew ? " ↻" : ""}</span>;
};

export default function Contracts() {
  const [sp] = useSearchParams();
  const [f, setF] = useState<Record<string, string>>(() => Object.fromEntries(FILTERS.filter((k) => sp.get(k)).map((k) => [k, sp.get(k) as string])));
  const [search, setSearch] = useState("");
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());
  const [saved, setSaved] = useState<"all" | "expiring" | "flagged" | "unsigned">("all");
  const [sel, setSel] = useState<number | null>(null);
  const filters = useQuery({ queryKey: ["filters"], queryFn: () => api<Record<string, string[]>>("/api/contracts/filters") });
  const prop = useCurrentProperty();
  const qs = new URLSearchParams({ ...(prop ? { property: prop } : {}), ...Object.fromEntries(Object.entries(f).filter(([, v]) => v)), ...(search ? { search } : {}) }).toString();
  const q = useQuery({ queryKey: ["contracts", qs], queryFn: () => api<Row[]>(`/api/contracts?${qs}`) });
  const now = Date.now();
  const shown = (q.data ?? []).filter((c) => saved === "all" || (saved === "expiring" && !!c.expiry_date && new Date(c.expiry_date).getTime() - now < 90 * 864e5 && new Date(c.expiry_date).getTime() > now) || (saved === "flagged" && (c.liability_uncapped || (c.deviation_count ?? 0) > 5)) || (saved === "unsigned" && !c.fully_executed));
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1>Contract repository</h1>
        <div className="inline-flex overflow-hidden rounded-md border border-slate-300 bg-white text-[12.5px] font-semibold dark:border-slate-600 dark:bg-slate-800" role="group" aria-label="Saved views">
          {([["all", "All"], ["expiring", "Expiring"], ["flagged", "Flagged"], ["unsigned", "Unsigned"]] as const).map(([k, t]) => <button key={k} className={`min-h-[32px] px-3 ${saved === k ? "bg-ink text-white" : "text-ink-mute"}`} onClick={() => setSaved(k)}>{t}</button>)}</div>
        <div className="flex gap-2 text-sm">
          <button className="rounded border border-slate-300 px-2 py-1 dark:border-slate-600" onClick={() => setCollapsed(new Set())}>Expand all</button>
          <button className="rounded border border-slate-300 px-2 py-1 dark:border-slate-600" onClick={() => setCollapsed(new Set((q.data ?? []).filter((c) => (q.data ?? []).some((x) => x.parent_id === c.id)).map((c) => c.id)))}>Collapse all</button>
        </div>
      </div>
      <Card>
        <div className="flex flex-wrap items-end gap-3 text-sm">
          <label className="flex flex-col gap-1">Search<input className="rounded border bg-transparent px-2 py-1" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="title or vendor" /></label>
          {FILTERS.map((k) => (
            <label key={k} className="flex flex-col gap-1 capitalize">{k}
              <select className="rounded border bg-transparent px-2 py-1 dark:bg-slate-800" value={f[k] ?? ""} onChange={(e) => setF({ ...f, [k]: e.target.value })}>
                <option value="">All</option>{filters.data?.[k]?.map((v) => <option key={v}>{v}</option>)}
              </select>
            </label>
          ))}
          <button className="rounded border px-2 py-1" onClick={() => { setF({}); setSearch(""); }}>Reset</button>
          <span className="ml-auto text-slate-500">{shown.length} of {q.data?.length ?? 0} documents</span>
        </div>
      </Card>
      <Loading q={q} />
      {q.data && (
        <div className="flex flex-wrap items-start gap-4"><Card className="min-w-0 flex-[999_1_900px]">
          <div className="overflow-x-auto"><table className="w-full text-sm">
            <thead><tr><Th className="min-w-[19rem]">Contract</Th><Th>Type</Th><Th>Property</Th><Th>Start</Th><Th>End</Th><Th>Last day to act</Th><Th className="text-right">Value</Th><Th className="text-right">Payment</Th><Th>Liability</Th><Th>Exit</Th><Th>Signed</Th><Th>Flags</Th></tr></thead>
            <tbody>
              {flatten(shown, collapsed).map(({ r: c, depth, kids }) => (
                <tr key={c.id} onClick={() => setSel(c.id)} className={`cursor-pointer border-t border-slate-100 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-700/40 ${sel === c.id ? "bg-indigo-50 dark:bg-slate-700" : depth === 0 ? "" : "bg-slate-50/40 dark:bg-slate-800/40"}`}>
                  <Td>
                    <div className="flex items-start gap-1" style={{ paddingLeft: depth * 20 }}>
                      <button className="w-4 shrink-0 text-slate-400" aria-label={kids ? (collapsed.has(c.id) ? `Expand ${c.title}` : `Collapse ${c.title}`) : undefined} disabled={!kids}
                        onClick={(e) => { e.stopPropagation(); const n = new Set(collapsed); if (n.has(c.id)) n.delete(c.id); else n.add(c.id); setCollapsed(n); }}>{kids ? (collapsed.has(c.id) ? "▸" : "▾") : depth ? "↳" : ""}</button>
                      <div className="min-w-0"><Link to={`/contracts/${c.id}`} onClick={(e) => e.stopPropagation()} className="font-medium text-indigo-600 hover:underline dark:text-indigo-400">{c.title}</Link>
                        {depth === 0 && <Link to={`/vendors/${encodeURIComponent(c.vendor)}`} onClick={(e) => e.stopPropagation()} className="block text-xs text-slate-500 hover:underline">{c.vendor}{kids ? ` · ${kids} under it` : ""}</Link>}</div>
                    </div>
                  </Td>
                  <Td><TypeBadge t={c.type} /></Td><Td>{c.property ?? <span className="text-ink-mute">Group</span>}</Td>
                  <Td className="whitespace-nowrap tabular-nums">{fmtDate(c.effective_date)}</Td>
                  <Td className="whitespace-nowrap tabular-nums">{fmtDate(c.expiry_date)}</Td>
                  <Td>{c.type === "Amendment" ? <span className="text-slate-400">—</span> : actBy(c)}</Td>
                  <Td className="text-right tabular-nums">{c.annual_value ? usd(c.annual_value) : c.total_value ? <span title="fixed fee">{usd(c.total_value)}*</span> : "—"}</Td>
                  <Td className="text-right tabular-nums">{c.payment_terms_days ? `${c.payment_terms_days}d` : "—"}</Td>
                  <Td>{["NDA", "Amendment"].includes(c.type) ? <span className="text-slate-400">—</span> : cap(c)}</Td>
                  <Td>{c.termination_for_convenience === true ? "Yes" : c.termination_for_convenience === false ? <span className="font-medium text-amber-700 dark:text-amber-300">No</span> : "—"}</Td>
                  <Td><Signed c={c} /></Td>
                  <Td><Flags c={c} /></Td>
                </tr>
              ))}
            </tbody>
          </table></div>
          <p className="mt-2 text-xs text-slate-500">Each agreement with its schedules, work orders, amendments, NDAs and DPAs beneath it; values are the current ones after amendments. Last day to act = end date, or the last day to give notice when it renews automatically (↻). * fixed fee · click a row to inspect it</p>
        </Card>
        {sel !== null && <Inspector id={sel} />}
        </div>
      )}
    </div>
  );
}
