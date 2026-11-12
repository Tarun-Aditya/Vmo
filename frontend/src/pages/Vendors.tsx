import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, daysLabel, fmtDate, usd } from "../lib";
import { Card, Loading, Sev, SeverityChip, Td, Th } from "../ui";

export type Vendor = {
  vendor: string; categories: string[]; contracts: number; documents: number; annual_value: number; work_order_value: number;
  auto_renewals: number; unsigned: number; next_expiry: string | null; next_expiry_days: number | null; deviations: number; dev_critical: number; dev_high: number;
  risk: Sev; flags: { key: string; severity: Sev; label: string }[];
};

export default function Vendors() {
  const q = useQuery({ queryKey: ["vendors"], queryFn: () => api<Vendor[]>("/api/vendors") });
  if (!q.data) return <Loading q={q} />;
  const v = q.data, total = v.reduce((a, x) => a + x.annual_value, 0), max = Math.max(...v.map((x) => x.annual_value), 1);
  const critical = v.filter((x) => x.risk === "critical").length;
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Vendors</h1>
        <p className="text-sm text-slate-500">Each vendor’s whole relationship in one place: contracts, spend, upcoming dates and risk. Open a vendor for its MSA → SOW → Work Order tree and key-clause coverage.</p>
      </div>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {[["Vendors", String(v.length)], ["Annual value", usd(total)], ["Vendors with critical flags", String(critical)], ["Contracts & work orders", String(v.reduce((a, x) => a + x.contracts, 0))]].map(([l, x]) => (
          <Card key={l}><div className="text-xs font-semibold uppercase tracking-wide text-slate-500">{l}</div><div className="mt-1 text-3xl font-semibold tabular-nums">{x}</div></Card>
        ))}
      </div>
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr><Th>Vendor</Th><Th>Risk</Th><Th className="text-right">Contracts</Th><Th className="w-56">Annual value</Th><Th>Next end date</Th><Th>Deviations</Th><Th>Flags</Th></tr></thead>
            <tbody>
              {v.map((x) => (
                <tr key={x.vendor} className="border-t border-slate-100 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-700/40">
                  <Td>
                    <Link to={`/vendors/${encodeURIComponent(x.vendor)}`} className="font-semibold text-indigo-600 hover:underline dark:text-indigo-400">{x.vendor}</Link>
                    <div className="text-xs text-slate-500">{x.categories.join(" · ")}</div>
                  </Td>
                  <Td><SeverityChip sev={x.risk} label={x.risk === "low" ? "ok" : x.risk} /></Td>
                  <Td className="text-right tabular-nums">{x.contracts}<div className="text-[11px] text-slate-500">{x.documents} {x.documents === 1 ? "doc" : "docs"}</div></Td>
                  <Td>
                    <div className="font-medium tabular-nums">{x.annual_value ? usd(x.annual_value) : "—"}{x.work_order_value > 0 && <span className="ml-1 text-[11px] font-normal text-slate-500">+ {usd(x.work_order_value)} WOs</span>}</div>
                    <div className="mt-1 h-1.5 rounded bg-slate-200 dark:bg-slate-700" role="img" aria-label={`${Math.round((x.annual_value / total) * 100)}% of annual value`}><div className="h-1.5 rounded bg-indigo-500" style={{ width: `${(x.annual_value / max) * 100}%` }} /></div>
                  </Td>
                  <Td className="whitespace-nowrap tabular-nums">{fmtDate(x.next_expiry)}<div className="text-xs text-slate-500">{x.next_expiry_days !== null ? daysLabel(x.next_expiry_days) : ""}</div></Td>
                  <Td className="tabular-nums">{x.deviations}{(x.dev_critical + x.dev_high) > 0 && <div className="text-[11px] text-red-600">{x.dev_critical + x.dev_high} high/critical</div>}</Td>
                  <Td><div className="flex max-w-xs flex-wrap gap-1">{x.flags.slice(0, 3).map((f) => <SeverityChip key={f.key} sev={f.severity} label={f.label} />)}{x.flags.length > 3 && <span className="text-xs text-slate-500">+{x.flags.length - 3}</span>}</div></Td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
