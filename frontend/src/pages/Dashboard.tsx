import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, daysLabel, fmtDate, inr } from "../lib";
import { Card, Loading, Sev, SeverityChip, Td, Th, sevStripe } from "../ui";

type Item = { id: number; title: string; vendor: string; category: string; owner: string; annual_value: number | null; auto_renew: boolean;
  expiry_date: string; notice_deadline: string; action_date: string; action: "notice" | "expiry"; days_left: number; notice_days_left: number;
  bucket: string; severity: Sev };
type Dash = { kpis: Record<string, number>;
  buckets: { bucket: string; severity: Sev; count: number; value: number }[];
  timeline: Item[]; risks: Record<string, { id: number; title: string; vendor: string }[]> };

const BUCKET_LABEL: Record<string, string> = { overdue: "Deadline passed", "30": "Next 30 days", "60": "31–60 days", "90": "61–90 days" };
const COLORS: Record<Sev, string> = { critical: "#dc2626", high: "#f97316", medium: "#d97706", low: "#0ea5e9" };

function Kpi({ label, value, sub, sev }: { label: string; value: string | number; sub?: string; sev?: Sev }) {
  return (
    <div className={`rounded-lg border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-800 ${sev ? sevStripe(sev) : ""}`}>
      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</div>
      <div className="mt-1 text-3xl font-semibold tabular-nums">{value}</div>
      {sub && <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">{sub}</div>}
    </div>
  );
}

export default function Dashboard() {
  const q = useQuery({ queryKey: ["dash"], queryFn: () => api<Dash>("/api/dashboard") });
  if (!q.data) return <Loading q={q} />;
  const { kpis: k, buckets, timeline, risks } = q.data;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <Kpi label="Contracts" value={k.contracts} sub="incl. SOWs & amendments" />
        <Kpi label="Annual value" value={inr(k.annual_value)} sub="active, amendment-adjusted" />
        <Kpi label="Expiring in 90 days" value={k.expiring_90} sub={`${inr(k.expiring_90_value)} at stake`} sev="high" />
        <Kpi label="Auto-renew, notice due" value={k.autorenew_notice_soon} sub={`${k.autorenew_notice_passed} already passed`} sev="critical" />
        <Kpi label="Uncapped liability" value={k.uncapped} sub="vendors with unlimited exposure" sev="critical" />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Value at stake by deadline bucket" className="lg:col-span-1">
          <div className="h-56">
            <ResponsiveContainer>
              <BarChart data={buckets.map((b) => ({ name: BUCKET_LABEL[b.bucket], lakh: b.value / 1e5, sev: b.severity, count: b.count }))} layout="vertical" margin={{ left: 20 }}>
                <XAxis type="number" tickFormatter={(v) => `₹${v}L`} fontSize={11} />
                <YAxis type="category" dataKey="name" width={110} fontSize={11} />
                <Tooltip formatter={(v: number) => [`₹${v.toFixed(1)} lakh`, "Annual value"]} />
                <Bar dataKey="lakh" radius={[0, 4, 4, 0]}>
                  {buckets.map((b) => <Cell key={b.bucket} fill={COLORS[b.severity]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <div className="grid grid-cols-2 gap-4 lg:col-span-2">
          {buckets.map((b) => (
            <div key={b.bucket} className={`rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800 ${sevStripe(b.severity)}`}>
              <div className="flex items-center justify-between"><span className="font-medium">{BUCKET_LABEL[b.bucket]}</span><SeverityChip sev={b.severity} /></div>
              <div className="mt-2 text-2xl font-semibold tabular-nums">{b.count} <span className="text-sm font-normal text-slate-500">contracts</span></div>
              <div className="text-sm text-slate-500">{inr(b.value)} annual value</div>
            </div>
          ))}
        </div>
      </div>

      <Card title="Upcoming action dates (notice deadline for auto-renewals, expiry otherwise)">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr><Th>Severity</Th><Th>Contract</Th><Th>Owner</Th><Th>Action</Th><Th>Due</Th><Th>Expiry</Th><Th className="text-right">Annual value</Th></tr></thead>
            <tbody>
              {timeline.map((i) => (
                <tr key={i.id} className={`border-t border-slate-100 dark:border-slate-700 ${sevStripe(i.severity)}`}>
                  <Td><SeverityChip sev={i.severity} label={i.bucket === "overdue" ? "overdue" : `≤${i.bucket}d`} /></Td>
                  <Td><Link className="font-medium text-indigo-600 hover:underline dark:text-indigo-400" to={`/contracts/${i.id}`}>{i.title}</Link><div className="text-xs text-slate-500">{i.vendor}</div></Td>
                  <Td>{i.owner}</Td>
                  <Td>{i.action === "notice" ? "Give non-renewal notice" : "Contract expires"}{i.auto_renew && <span className="ml-1 rounded bg-slate-200 px-1 text-[10px] dark:bg-slate-700">AUTO-RENEW</span>}</Td>
                  <Td className="whitespace-nowrap tabular-nums"><b>{fmtDate(i.action_date)}</b><div className="text-xs text-slate-500">{daysLabel(i.action === "notice" ? i.notice_days_left : i.days_left)}</div></Td>
                  <Td className="whitespace-nowrap tabular-nums">{fmtDate(i.expiry_date)}</Td>
                  <Td className="text-right tabular-nums">{inr(i.annual_value)}</Td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="grid gap-4 md:grid-cols-3">
        {([["uncapped", "Uncapped liability", "critical"], ["no_tfc", "No termination for convenience", "high"], ["pd_without_dpa", "Personal data, no DPA", "critical"]] as [string, string, Sev][]).map(([key, label, sev]) => (
          <Card key={key} title={<span className="flex items-center gap-2">{label} <SeverityChip sev={sev} label={String(risks[key].length)} /></span>}>
            <ul className="space-y-1 text-sm">
              {risks[key].map((r) => <li key={r.id}><Link className="text-indigo-600 hover:underline dark:text-indigo-400" to={`/contracts/${r.id}`}>{r.title}</Link></li>)}
              {!risks[key].length && <li className="text-slate-500">None</li>}
            </ul>
          </Card>
        ))}
      </div>
    </div>
  );
}
