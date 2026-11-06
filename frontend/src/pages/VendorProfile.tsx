import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, daysLabel, fmtDate, usd } from "../lib";
import { Card, Loading, Sev, SeverityChip, Td, Th } from "../ui";
import { Hierarchy } from "./Contracts";
import { ClauseMatrix } from "./Clauses";
import type { Vendor } from "./Vendors";

type Doc = Parameters<typeof Hierarchy>[0]["rows"][number];
type Profile = {
  summary: Vendor; documents: Doc[];
  deviations: { contract_id: number; title: string; type: string; heading: string; severity: Sev; deviation_summary: string }[];
  upcoming: { id: number; title: string; type: string; expiry_date: string; notice_deadline: string; auto_renew: boolean; days_left: number; notice_days_left: number }[];
};

const Tile = ({ l, v, sub, sev }: { l: string; v: string | number; sub?: string; sev?: Sev }) => (
  <Card className={sev ? "border-l-4 border-l-red-500" : ""}><div className="text-xs font-semibold uppercase tracking-wide text-slate-500">{l}</div><div className="mt-1 text-2xl font-semibold tabular-nums">{v}</div>{sub && <div className="text-xs text-slate-500">{sub}</div>}</Card>
);

export default function VendorProfile() {
  const { name } = useParams();
  const vendor = decodeURIComponent(name ?? "");
  const q = useQuery({ queryKey: ["vendor", vendor], queryFn: () => api<Profile>(`/api/vendors/${encodeURIComponent(vendor)}`) });
  if (!q.data) return <Loading q={q} />;
  const { summary: s, documents, deviations, upcoming } = q.data;
  const short = vendor.split(" ")[0];
  const asks = [`Show all ${short} contracts with start date, end date and annual value`, `Which ${short} contracts are not fully signed?`, `Show the key clauses in the ${short} MSA`];
  return (
    <div className="space-y-6">
      <div>
        <Link to="/vendors" className="text-sm text-slate-500 hover:underline">← Vendors</Link>
        <div className="flex flex-wrap items-center gap-3"><h1 className="text-2xl font-semibold">{vendor}</h1><SeverityChip sev={s.risk} label={s.risk === "low" ? "no flags" : `${s.risk} risk`} /></div>
        <p className="text-sm text-slate-500">{s.categories.join(" · ")}</p>
        <div className="mt-2 flex flex-wrap gap-1">{s.flags.map((f) => <SeverityChip key={f.key} sev={f.severity} label={f.label} />)}</div>
      </div>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <Tile l="Documents" v={s.documents} sub={`${s.contracts} contracts & work orders`} />
        <Tile l="Annual value" v={s.annual_value ? usd(s.annual_value) : "—"} sub={s.work_order_value ? `+ ${usd(s.work_order_value)} fixed-fee work orders` : undefined} />
        <Tile l="Next end date" v={fmtDate(s.next_expiry)} sub={s.next_expiry_days !== null ? daysLabel(s.next_expiry_days) : undefined} />
        <Tile l="Deviations" v={s.deviations} sub={`${s.dev_critical} critical · ${s.dev_high} high`} sev={s.dev_critical ? "critical" : undefined} />
        <Tile l="Not fully signed" v={s.unsigned} sub={s.unsigned ? "needs countersignature" : "all signed"} sev={s.unsigned ? "high" : undefined} />
      </div>

      <section><h2 className="mb-2 text-lg font-semibold">Contracts &amp; hierarchy</h2><Hierarchy rows={documents} /></section>

      <Card title="Key dates">
        <table className="w-full text-sm"><thead><tr><Th>Document</Th><Th>End date</Th><Th>Notice deadline</Th></tr></thead><tbody>
          {upcoming.map((u) => (
            <tr key={u.id} className="border-t border-slate-100 dark:border-slate-700">
              <Td><Link className="text-indigo-600 hover:underline dark:text-indigo-400" to={`/contracts/${u.id}`}>{u.title}</Link></Td>
              <Td className="whitespace-nowrap tabular-nums">{fmtDate(u.expiry_date)} <span className="text-xs text-slate-500">{daysLabel(u.days_left)}</span></Td>
              <Td className="whitespace-nowrap tabular-nums">{u.auto_renew ? <>{fmtDate(u.notice_deadline)} <span className={`text-xs ${u.notice_days_left < 0 ? "font-semibold text-red-600" : "text-slate-500"}`}>{daysLabel(u.notice_days_left)}</span></> : <span className="text-slate-400">no auto-renewal</span>}</Td>
            </tr>))}
        </tbody></table>
      </Card>

      <Card title={`Deviations from the standard templates (${deviations.length})`}>
        {deviations.length === 0 ? <p className="text-sm text-slate-500">None — every clause matches the standard.</p> : (
          <table className="w-full text-sm"><thead><tr><Th>Severity</Th><Th>Document</Th><Th>Clause</Th><Th>What differs</Th></tr></thead><tbody>
            {deviations.map((d, i) => (
              <tr key={i} className="border-t border-slate-100 dark:border-slate-700"><Td><SeverityChip sev={d.severity} /></Td>
                <Td><Link className="text-indigo-600 hover:underline dark:text-indigo-400" to={`/contracts/${d.contract_id}`}>{d.title}</Link></Td><Td>{d.heading}</Td><Td>{d.deviation_summary}</Td></tr>))}
          </tbody></table>)}
      </Card>

      <ClauseMatrix vendor={vendor} />

      <Card title="Ask about this vendor">
        <div className="flex flex-wrap gap-2">{asks.map((a) => <Link key={a} to={`/ask?q=${encodeURIComponent(a)}`} className="rounded-full border border-slate-300 px-3 py-1 text-xs hover:bg-indigo-50 dark:border-slate-600 dark:hover:bg-slate-700">{a}</Link>)}</div>
      </Card>
    </div>
  );
}
