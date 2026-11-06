import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, fmtDate, inr } from "../lib";
import { Card, Loading, SeverityChip, Td, Th } from "../ui";

type Row = { id: number; title: string; vendor: string; category: string; type: string; owner: string; status: string; parent_id: number | null;
  effective_date: string | null; expiry_date: string | null; annual_value: number | null; total_value: number | null; auto_renew: boolean;
  liability_uncapped: boolean; deviation_count: number; fully_executed: boolean; customer_signatory: string | null; supplier_signatory: string | null };
const FILTERS = ["vendor", "category", "type", "owner", "status"] as const;
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
        <span className="hidden w-24 shrink-0 text-right tabular-nums lg:block">{n.annual_value ? inr(n.annual_value) : n.total_value ? `${inr(n.total_value)} fixed` : "—"}</span>
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

export default function Contracts() {
  const [f, setF] = useState<Record<string, string>>({});
  const [search, setSearch] = useState("");
  const [view, setView] = useState<"table" | "tree">("table");
  const filters = useQuery({ queryKey: ["filters"], queryFn: () => api<Record<string, string[]>>("/api/contracts/filters") });
  const qs = new URLSearchParams({ ...Object.fromEntries(Object.entries(f).filter(([, v]) => v)), ...(search ? { search } : {}) }).toString();
  const q = useQuery({ queryKey: ["contracts", qs], queryFn: () => api<Row[]>(`/api/contracts?${qs}`) });
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Contract repository</h1>
        <div className="inline-flex overflow-hidden rounded border border-slate-300 text-sm dark:border-slate-600" role="tablist">
          {(["table", "tree"] as const).map((v) => (
            <button key={v} role="tab" aria-selected={view === v} onClick={() => setView(v)} className={`px-3 py-1.5 ${view === v ? "bg-indigo-600 text-white" : "bg-white dark:bg-slate-800"}`}>{v === "table" ? "Table" : "Hierarchy"}</button>
          ))}
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
          <span className="ml-auto text-slate-500">{q.data?.length ?? 0} documents</span>
        </div>
      </Card>
      <Loading q={q} />
      {q.data && view === "tree" && <Hierarchy rows={q.data} />}
      {q.data && view === "table" && (
        <Card>
          <div className="overflow-x-auto"><table className="w-full text-sm">
            <thead><tr><Th>Contract</Th><Th>Type</Th><Th>Category</Th><Th>Owner</Th><Th>Start date</Th><Th>End date</Th><Th className="text-right">Value</Th><Th>Signatures</Th><Th>Flags</Th></tr></thead>
            <tbody>
              {q.data.map((c) => (
                <tr key={c.id} className="border-t border-slate-100 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-700/40">
                  <Td><Link to={`/contracts/${c.id}`} className={`font-medium text-indigo-600 hover:underline dark:text-indigo-400 ${c.parent_id ? "pl-4" : ""}`}>{c.parent_id ? "↳ " : ""}{c.title}</Link><Link to={`/vendors/${encodeURIComponent(c.vendor)}`} className="block text-xs text-slate-500 hover:underline">{c.vendor}</Link></Td>
                  <Td><TypeBadge t={c.type} /></Td><Td>{c.category}</Td><Td>{c.owner}</Td>
                  <Td className="whitespace-nowrap tabular-nums">{fmtDate(c.effective_date)}</Td>
                  <Td className="whitespace-nowrap tabular-nums">{fmtDate(c.expiry_date)}</Td>
                  <Td className="text-right tabular-nums">{c.annual_value ? inr(c.annual_value) : c.total_value ? <span title="fixed fee">{inr(c.total_value)}*</span> : "—"}</Td>
                  <Td><Signed c={c} /></Td>
                  <Td><Flags c={c} /></Td>
                </tr>
              ))}
            </tbody>
          </table></div>
          <p className="mt-2 text-xs text-slate-500">* fixed fee (Work Orders carry a total fee, not an annual value)</p>
        </Card>
      )}
    </div>
  );
}
