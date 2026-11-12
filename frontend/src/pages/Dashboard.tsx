import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, daysLabel, fmtDate, Status, usd } from "../lib";
import { Card, Loading, Sev, SeverityChip, Td, Th } from "../ui";
import type { Vendor } from "./Vendors";

type Item = { id: number; title: string; vendor: string; category: string; type: string; owner: string; property?: string | null; annual_value: number | null; auto_renew: boolean;
  expiry_date: string; notice_deadline: string; days_left: number; notice_days_left: number; notice_passed: boolean; liability_uncapped: boolean; fully_executed: boolean };
type Lane = { label: string; severity: Sev; count: number; value: number; items: Item[] };
type Dash = { kpis: Record<string, number>; lanes: Record<string, Lane>; monthly: { month: string; label: string; count: number; value: number }[];
  risks: Record<string, { id: number; title: string; vendor: string }[]> };

const TONE: Record<string, string> = { crit: "border-red-300", warn: "border-orange-300", info: "border-indigo-300" };
function Kpi({ label, value, sub, tone, to }: { label: string; value: string | number; sub?: string; tone?: "crit" | "warn" | "info"; to?: string }) {
  const body = (
    <div className={`rounded-lg border bg-white p-3.5 dark:bg-slate-800 ${tone ? TONE[tone] : "border-line dark:border-slate-700"}`}>
      <div className="text-[11.5px] font-semibold uppercase tracking-wider text-ink-mute dark:text-slate-400">{label}</div>
      <div className="num mt-0.5 text-[28px] font-semibold leading-tight tracking-tight">{value}</div>
      {sub && <div className="text-[12.5px] text-ink-mute dark:text-slate-400">{sub}</div>}
    </div>);
  return to ? <Link to={to} className="block hover:shadow-sm">{body}</Link> : body;
}

/** What to do with a contract whose deadline is near: the action a VMO would take. */
function act(i: Item): { label: string; sev: Sev; why: string; primary: boolean } {
  if (i.notice_passed) return { label: "Negotiate exit", sev: "critical", why: `Notice passed ${daysLabel(i.notice_days_left).replace(" overdue", "")} ago`, primary: true };
  if (i.auto_renew && i.notice_days_left <= 30) return { label: "Send notice", sev: i.notice_days_left <= 14 ? "critical" : "high", why: `Last day to cancel ${fmtDate(i.notice_deadline)}`, primary: true };
  if (i.days_left <= 30) return { label: "Plan renewal", sev: "critical", why: `Ends ${fmtDate(i.expiry_date)} · ${daysLabel(i.days_left)}`, primary: true };
  return { label: "Plan renewal", sev: i.days_left <= 60 ? "high" : "medium", why: `Ends ${fmtDate(i.expiry_date)} · ${daysLabel(i.days_left)}`, primary: false };
}

export default function Dashboard() {
  const q = useQuery({ queryKey: ["dash"], queryFn: () => api<Dash>("/api/dashboard"), refetchInterval: 30000 });
  const meta = useQuery({ queryKey: ["meta"], queryFn: () => api<{ today: string; customer?: string; llm_label: string; demo_mode: boolean }>("/api/meta") });
  const ven = useQuery({ queryKey: ["vendors"], queryFn: () => api<Vendor[]>("/api/vendors") });
  const sp = useQuery({ queryKey: ["spend-summary"], queryFn: () => api<{ exceptions: number; at_risk: number }>("/api/spend/summary") });
  const sla = useQuery({ queryKey: ["sla"], queryFn: () => api<{ summary: { breach_months: number; credit_usd: number } }>("/api/sla") });
  const st = useQuery({ queryKey: ["status"], queryFn: () => api<Status>("/api/status") });
  if (!q.data) return <Loading q={q} />;
  const { kpis: k, lanes, risks } = q.data;
  const all = (["30", "60", "90"] as const).flatMap((key) => lanes[key].items);
  const queue = [...all].sort((a, b) => (a.auto_renew && !b.auto_renew ? -1 : !a.auto_renew && b.auto_renew ? 1 : 0) || (a.auto_renew ? a.notice_days_left - b.notice_days_left : a.days_left - b.days_left)).slice(0, 8);
  const top = [...(ven.data ?? [])].sort((a, b) => b.annual_value - a.annual_value).slice(0, 6), max = Math.max(...top.map((v) => v.annual_value), 1);
  const day = meta.data?.today ? new Date(meta.data.today + "T00:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) : "";
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h1>Overview</h1><div className="text-sm text-ink-mute dark:text-slate-400">{meta.data?.customer ?? ""} · {k.contracts} contracts · {ven.data?.length ?? "…"} vendors · today {day}</div></div>
        <div className="flex flex-wrap gap-2"><Link to="/new" className="inline-flex min-h-[36px] items-center rounded-md border border-indigo-600 bg-indigo-600 px-3.5 text-[13px] font-semibold text-white hover:bg-indigo-700">New contract</Link><Link to="/renewals" className="inline-flex min-h-[36px] items-center rounded-md border border-slate-300 bg-white px-3.5 text-[13px] font-semibold hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-800">Renewals</Link>
          <Link to="/map" className="inline-flex min-h-[36px] items-center rounded-md border border-slate-300 bg-white px-3.5 text-[13px] font-semibold hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-800">Portfolio map</Link></div>
      </div>

      <section className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6" aria-label="Key figures">
        <Kpi label="Annual value" value={usd(k.annual_value)} sub="active, amendment-adjusted" to="/vendors" />
        <Kpi label="Ending in 90 days" value={k.expiring_90} sub={`${usd(k.expiring_90_value)} at stake`} tone="warn" to="/renewals" />
        <Kpi label="Notice deadlines due" value={k.autorenew_notice_soon} sub={`${k.autorenew_notice_passed} already passed`} tone="crit" to="/renewals" />
        <Kpi label="Uncapped liability" value={k.uncapped} sub="unlimited exposure" tone="crit" to="/contracts" />
        <Kpi label="Spend exceptions" value={sp.data?.exceptions ?? "…"} sub={sp.data ? `${usd(sp.data.at_risk)} to review` : ""} tone="warn" to="/spend" />
        <Kpi label="SLA breaches" value={sla.data?.summary.breach_months ?? "…"} sub={sla.data ? `${usd(sla.data.summary.credit_usd)} credits` : ""} to="/obligations" />
      </section>

      <div className="flex flex-wrap items-start gap-4">
        <div className="flex min-w-0 flex-[999_1_700px] flex-col gap-4">
          <Card title="Act now" right={<span className="text-xs text-ink-mute">sorted by last day to act</span>} className="overflow-hidden">
            <div className="-mx-4 -mb-4 overflow-x-auto"><table className="w-full text-[13px]">
              <thead className="bg-slate-50 dark:bg-slate-900"><tr><Th>Why</Th><Th>Contract</Th><Th>Vendor</Th><Th className="text-right">Annual value</Th><Th /></tr></thead>
              <tbody>
                {queue.map((i) => { const a = act(i); return (
                  <tr key={i.id} className="border-t border-slate-100 dark:border-slate-700">
                    <Td><SeverityChip sev={a.sev} label={a.why} /></Td>
                    <Td><Link to={`/contracts/${i.id}`} className="font-semibold text-indigo-600 hover:underline dark:text-indigo-300">{i.title}</Link><div className="text-xs text-ink-mute">{i.type} · {i.auto_renew ? "auto-renews" : "no auto-renew"}</div></Td>
                    <Td><Link to={`/vendors/${encodeURIComponent(i.vendor)}`} className="hover:underline">{i.vendor}</Link>{i.property && <div className="text-[11px] text-ink-mute">{i.property}</div>}</Td>
                    <Td className="num text-right">{usd(i.annual_value)}</Td>
                    <Td className="text-right"><Link to={`/contracts/${i.id}`} className={`inline-flex min-h-[30px] items-center rounded-md border px-2.5 text-[12.5px] font-semibold ${a.primary ? "border-indigo-600 bg-indigo-600 text-white hover:bg-indigo-700" : "border-slate-300 bg-white hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-800"}`}>{a.label}</Link></Td>
                  </tr>); })}
                {!queue.length && <tr><td className="py-6 text-center text-ink-mute" colSpan={5}>Nothing needs a decision in the next 90 days.</td></tr>}
              </tbody>
            </table></div>
          </Card>
          <Card title="Renewal exposure by window">
            <div className="grid grid-cols-3 gap-4">{(["30", "60", "90"] as const).map((key) => (
              <div key={key}><div className="flex items-center gap-2"><SeverityChip sev={lanes[key].severity} label={`≤${key} days`} /></div><div className="num mt-1 text-2xl font-semibold">{lanes[key].count}</div><div className="text-[12.5px] text-ink-mute">{usd(lanes[key].value)} a year</div></div>))}</div>
          </Card>
        </div>
        <aside className="flex min-w-0 flex-[1_1_340px] flex-col gap-4">
          <Card title="Annual value by vendor" right={<Link to="/vendors" className="text-xs font-semibold text-indigo-600">All vendors</Link>}>
            <div className="space-y-2">{top.map((v) => (
              <div key={v.vendor} className="grid grid-cols-[130px_1fr_64px] items-center gap-2 text-[13px]"><Link to={`/vendors/${encodeURIComponent(v.vendor)}`} className="truncate hover:underline">{v.vendor.replace(/ (Inc|LLC|LLP|Ltd|Pte Ltd)\.?$/, "")}</Link>
                <span className="h-2.5 rounded bg-slate-200 dark:bg-slate-700"><span className="block h-2.5 rounded bg-indigo-600" style={{ width: `${(v.annual_value / max) * 100}%` }} /></span><span className="num text-right">{usd(v.annual_value)}</span></div>))}</div>
          </Card>
          <Card title="Needs attention">
            <div className="space-y-3 text-[13px]">
              {([["uncapped", "Uncapped liability", "critical"], ["pd_without_dpa", "Personal data, no DPA", "critical"], ["no_tfc", "No termination for convenience", "high"]] as [string, string, Sev][]).map(([key, label, sev]) => (
                <div key={key}><div className="mb-1 flex items-center gap-2 font-semibold">{label} <SeverityChip sev={sev} label={String(risks[key].length)} /></div>
                  <ul className="space-y-0.5">{risks[key].slice(0, 3).map((r) => <li key={r.id}><Link className="text-indigo-600 hover:underline dark:text-indigo-300" to={`/contracts/${r.id}`}>{r.title}</Link></li>)}{!risks[key].length && <li className="text-ink-mute">None</li>}</ul></div>))}
            </div>
          </Card>
          <Card title="Engine and data">
            <dl className="space-y-1.5 text-[13px]">
              <div className="flex justify-between gap-2"><dt>Mode</dt><dd>{meta.data?.demo_mode ? "Demo · no Claude" : `Live · ${meta.data?.llm_label ?? ""}`}</dd></div>
              <div className="flex justify-between gap-2"><dt>Last run</dt><dd className="num text-right">{st.data?.last_run ? `${st.data.last_run.new_docs} new · ${st.data.last_run.updated} changed · ${st.data.last_run.failed} failed` : "—"}</dd></div>
            </dl>
          </Card>
        </aside>
      </div>
    </div>
  );
}
