import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, fmtDate, inr } from "../lib";
import { Card, Loading, SeverityChip, Td, Th } from "../ui";

type Row = { id: number; title: string; vendor: string; category: string; type: string; owner: string; status: string; parent_id: number | null;
  expiry_date: string | null; annual_value: number | null; auto_renew: boolean; liability_uncapped: boolean; deviation_count: number };
const FILTERS = ["vendor", "category", "type", "owner", "status"] as const;

export default function Contracts() {
  const [f, setF] = useState<Record<string, string>>({});
  const [search, setSearch] = useState("");
  const filters = useQuery({ queryKey: ["filters"], queryFn: () => api<Record<string, string[]>>("/api/contracts/filters") });
  const qs = new URLSearchParams({ ...Object.fromEntries(Object.entries(f).filter(([, v]) => v)), ...(search ? { search } : {}) }).toString();
  const q = useQuery({ queryKey: ["contracts", qs], queryFn: () => api<Row[]>(`/api/contracts?${qs}`) });
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Contract repository</h1>
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
          <span className="ml-auto text-slate-500">{q.data?.length ?? 0} contracts</span>
        </div>
      </Card>
      <Loading q={q} />
      {q.data && (
        <Card>
          <div className="overflow-x-auto"><table className="w-full text-sm">
            <thead><tr><Th>Contract</Th><Th>Type</Th><Th>Category</Th><Th>Owner</Th><Th>Status</Th><Th>Expiry (effective)</Th><Th className="text-right">Annual value</Th><Th>Flags</Th></tr></thead>
            <tbody>
              {q.data.map((c) => (
                <tr key={c.id} className="border-t border-slate-100 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-700/40">
                  <Td><Link to={`/contracts/${c.id}`} className={`font-medium text-indigo-600 hover:underline dark:text-indigo-400 ${c.parent_id ? "pl-4" : ""}`}>{c.parent_id ? "↳ " : ""}{c.title}</Link><div className="text-xs text-slate-500">{c.vendor}</div></Td>
                  <Td>{c.type}</Td><Td>{c.category}</Td><Td>{c.owner}</Td><Td className="capitalize">{c.status}</Td>
                  <Td className="whitespace-nowrap tabular-nums">{fmtDate(c.expiry_date)}</Td>
                  <Td className="text-right tabular-nums">{inr(c.annual_value)}</Td>
                  <Td><div className="flex flex-wrap gap-1">
                    {c.liability_uncapped && <SeverityChip sev="critical" label="uncapped" />}
                    {c.auto_renew && <span className="rounded border border-slate-400 px-1 text-xs">auto-renew</span>}
                    {c.deviation_count > 0 && <span className="rounded border border-slate-400 px-1 text-xs">{c.deviation_count} deviations</span>}
                  </div></Td>
                </tr>
              ))}
            </tbody>
          </table></div>
        </Card>
      )}
    </div>
  );
}
