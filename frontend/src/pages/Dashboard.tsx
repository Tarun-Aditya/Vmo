import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, daysLabel, fmtDate, usd } from "../lib";
import { Card, Loading, Sev, SeverityChip, sevStripe } from "../ui";

type Item = { id: number; title: string; vendor: string; category: string; type: string; owner: string; annual_value: number | null; auto_renew: boolean;
  expiry_date: string; notice_deadline: string; days_left: number; notice_days_left: number; notice_passed: boolean; liability_uncapped: boolean; fully_executed: boolean };
type Lane = { label: string; severity: Sev; count: number; value: number; items: Item[] };
type Dash = { kpis: Record<string, number>; lanes: Record<string, Lane>; monthly: { month: string; label: string; count: number; value: number }[];
  risks: Record<string, { id: number; title: string; vendor: string }[]> };

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
  const q = useQuery({ queryKey: ["dash"], queryFn: () => api<Dash>("/api/dashboard"), refetchInterval: 30000 });
  if (!q.data) return <Loading q={q} />;
  const { kpis: k, lanes, monthly, risks } = q.data;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <Kpi label="Contracts" value={k.contracts} sub="incl. SOWs, work orders & amendments" />
        <Kpi label="Annual value" value={usd(k.annual_value)} sub="active, amendment-adjusted" />
        <Kpi label="Expiring in 90 days" value={k.expiring_90} sub={`${usd(k.expiring_90_value)} at stake`} sev="high" />
        <Kpi label="Auto-renew, notice due" value={k.autorenew_notice_soon} sub={`${k.autorenew_notice_passed} already passed`} sev="critical" />
        <Kpi label="Uncapped liability" value={k.uncapped} sub="vendors with unlimited exposure" sev="critical" />
      </div>

      <div>
        <h2 className="mb-2 text-lg font-semibold">Contract expiry — next 30 / 60 / 90 days</h2>
        <div className="grid gap-4 lg:grid-cols-3">
          {(["30", "60", "90"] as const).map((key) => {
            const lane = lanes[key];
            return (
              <section key={key} className={`rounded-lg border border-slate-200 bg-slate-100/60 dark:border-slate-700 dark:bg-slate-800/40 ${sevStripe(lane.severity)}`} aria-label={lane.label}>
                <header className="flex items-start justify-between gap-2 p-3">
                  <div>
                    <div className="font-semibold">{lane.label}</div>
                    <div className="text-sm text-slate-500"><b className="text-slate-900 dark:text-slate-100">{lane.count}</b> contract{lane.count !== 1 ? "s" : ""} · {usd(lane.value)} annual value</div>
                  </div>
                  <SeverityChip sev={lane.severity} label={`≤${key}d`} />
                </header>
                <div className="space-y-2 p-3 pt-0">
                  {lane.items.length === 0 && <p className="py-4 text-center text-sm text-slate-500">Nothing expiring in this window</p>}
                  {lane.items.map((i) => (
                    <article key={i.id} className="rounded-md border border-slate-200 bg-white p-3 text-sm shadow-sm dark:border-slate-700 dark:bg-slate-800">
                      <div className="flex items-start justify-between gap-2">
                        <Link to={`/contracts/${i.id}`} className="font-medium text-indigo-600 hover:underline dark:text-indigo-400">{i.title}</Link>
                        <span className="shrink-0 rounded bg-slate-200 px-1.5 py-0.5 text-[10px] font-semibold dark:bg-slate-700">{i.type}</span>
                      </div>
                      <div className="text-xs text-slate-500"><Link to={`/vendors/${encodeURIComponent(i.vendor)}`} className="hover:underline">{i.vendor}</Link> · {i.owner}</div>
                      <div className="mt-2 flex items-end justify-between">
                        <div><div className="text-[11px] uppercase text-slate-500">End date</div><div className="font-semibold tabular-nums">{fmtDate(i.expiry_date)}</div><div className="text-xs text-slate-500">{daysLabel(i.days_left)}</div></div>
                        <div className="text-right"><div className="text-[11px] uppercase text-slate-500">Annual value</div><div className="font-semibold tabular-nums">{usd(i.annual_value)}</div></div>
                      </div>
                      <div className="mt-2 flex flex-wrap gap-1">
                        {i.auto_renew && <span className="rounded border border-slate-400 px-1 text-[11px]">auto-renews · notice {fmtDate(i.notice_deadline)}</span>}
                        {i.notice_passed && <SeverityChip sev="critical" label="notice deadline passed" />}
                        {!i.notice_passed && i.auto_renew && i.notice_days_left <= 30 && <SeverityChip sev="high" label={`notice in ${i.notice_days_left}d`} />}
                        {i.liability_uncapped && <SeverityChip sev="critical" label="uncapped" />}
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      </div>

      <Card title="Expiries over the next 12 months (contracts per month)">
        <div className="h-56">
          <ResponsiveContainer>
            <BarChart data={monthly} margin={{ left: 0, right: 8 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="label" fontSize={11} />
              <YAxis allowDecimals={false} fontSize={11} width={28} />
              <Tooltip formatter={(v: number, n: string, p) => n === "count" ? [`${v} contracts (${usd((p.payload as { value: number }).value)})`, "Expiring"] : [v, n]} />
              <Bar dataKey="count" fill="#4f46e5" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
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
