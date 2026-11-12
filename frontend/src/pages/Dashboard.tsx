import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, daysLabel, fmtDate, usd } from "../lib";
import { Card, Loading, Sev, SeverityChip, sevStripe } from "../ui";
import { Tile, TierChip } from "../components/vmo";

type Item = { id: number; title: string; vendor: string; category: string; type: string; owner: string; property?: string | null; annual_value: number | null; auto_renew: boolean;
  expiry_date: string; notice_deadline: string; days_left: number; notice_days_left: number; notice_passed: boolean; liability_uncapped: boolean; fully_executed: boolean };
type Lane = { label: string; severity: Sev; count: number; value: number; items: Item[] };
type Dash = { kpis: Record<string, number>; lanes: Record<string, Lane>; monthly: { month: string; label: string; count: number; value: number }[];
  risks: Record<string, { id: number; title: string; vendor: string }[]> };

function Kpi({ label, value, sub, sev }: { label: string; value: string | number; sub?: string; sev?: Sev }) {
  return (
    <div className={`rounded-xl border border-line bg-white p-4 dark:border-slate-700 dark:bg-slate-800 ${sev ? sevStripe(sev) : ""}`}>
      <div className="text-xs font-semibold uppercase tracking-wider text-ink-mute dark:text-slate-400">{label}</div>
      <div className="mt-1 font-serif text-4xl tabular-nums">{value}</div>
      {sub && <div className="mt-1 text-xs text-ink-mute dark:text-slate-400">{sub}</div>}
    </div>
  );
}

function OpsStrip() {
  const ob = useQuery({ queryKey: ["obligations", ""], queryFn: () => api<{ summary: { overdue: number; due_30: number } }>("/api/obligations") });
  const sp = useQuery({ queryKey: ["spend-summary"], queryFn: () => api<{ exceptions: number; at_risk: number; off_contract: number }>("/api/spend/summary") });
  const sla = useQuery({ queryKey: ["sla"], queryFn: () => api<{ summary: { breach_months: number; credit_usd: number } }>("/api/sla") });
  const rk = useQuery({ queryKey: ["risk"], queryFn: () => api<{ vendors: { vendor: string; score: number; tier: string }[] }>("/api/risk/vendors") });
  if (!ob.data || !sp.data || !sla.data || !rk.data) return null;
  const top = rk.data.vendors[0];
  return (
    <section aria-label="Vendor operations">
      <h2 className="mb-2 text-lg font-semibold">Vendor operations</h2>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Link to="/obligations"><Tile l="Overdue obligations" v={ob.data.summary.overdue} tone={ob.data.summary.overdue ? "red" : "green"} sub={`${ob.data.summary.due_30} more due in 30 days`} /></Link>
        <Link to="/spend"><Tile l="Spend exceptions" v={sp.data.exceptions} tone="amber" sub={`${usd(sp.data.at_risk)} at risk · ${usd(sp.data.off_contract)} off-contract`} /></Link>
        <Link to="/obligations"><Tile l="SLA breach months" v={sla.data.summary.breach_months} tone={sla.data.summary.breach_months ? "red" : "green"} sub={`~${usd(sla.data.summary.credit_usd)} estimated credits`} /></Link>
        {top && <Link to="/risk"><Tile l="Highest-risk vendor" v={<span className="text-lg">{top.vendor.replace(/ (Inc|LLP|Ltd)$/, "")}</span>} sub={<span className="inline-flex items-center gap-2">score {top.score.toFixed(0)} <TierChip tier={top.tier} /></span>} /></Link>}
      </div>
    </section>
  );
}

/** What to do with a contract whose deadline is near: the action a VMO would take. */
function action(i: Item): { label: string; sev: Sev; chip: string; primary: boolean } {
  if (i.notice_passed) return { label: "Negotiate exit", sev: "critical", chip: `notice deadline passed (${fmtDate(i.notice_deadline)})`, primary: true };
  if (i.auto_renew && i.notice_days_left <= 30) return { label: "Send notice", sev: i.notice_days_left <= 14 ? "critical" : "high", chip: `last day to cancel ${fmtDate(i.notice_deadline)} · ${daysLabel(i.notice_days_left)}`, primary: true };
  if (i.days_left <= 30) return { label: "Plan renewal", sev: "critical", chip: `ends ${fmtDate(i.expiry_date)} · ${daysLabel(i.days_left)}`, primary: true };
  return { label: "Review", sev: i.days_left <= 60 ? "high" : "medium", chip: `ends ${fmtDate(i.expiry_date)} · ${daysLabel(i.days_left)}`, primary: false };
}

export default function Dashboard() {
  const q = useQuery({ queryKey: ["dash"], queryFn: () => api<Dash>("/api/dashboard"), refetchInterval: 30000 });
  const meta = useQuery({ queryKey: ["meta"], queryFn: () => api<{ today: string }>("/api/meta") });
  if (!q.data) return <Loading q={q} />;
  const { kpis: k, lanes, monthly, risks } = q.data;
  const all = (["30", "60", "90"] as const).flatMap((key) => lanes[key].items);
  const queue = [...all].sort((a, b) => (a.auto_renew && !b.auto_renew ? -1 : !a.auto_renew && b.auto_renew ? 1 : 0) || (a.auto_renew ? a.notice_days_left - b.notice_days_left : a.days_left - b.days_left)).slice(0, 8);
  const urgent = all.filter((i) => i.auto_renew && (i.notice_passed || i.notice_days_left <= 30));
  const urgentValue = urgent.reduce((n, i) => n + Number(i.annual_value || 0), 0);
  const day = meta.data?.today ? new Date(meta.data.today + "T00:00:00").toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" }) : "";
  return (
    <div className="space-y-6">
      <section>
        <div className="text-xs font-semibold uppercase tracking-wider text-ink-mute dark:text-slate-400">{day}</div>
        <h1 className="mt-1 max-w-3xl font-serif text-3xl leading-tight md:text-4xl">
          {urgent.length
            ? <>{urgent.length} notice deadline{urgent.length !== 1 ? "s" : ""} need a decision now. <span className="text-indigo-600">{usd(urgentValue)}</span> a year renews unless someone acts.</>
            : <>No notice deadlines need a decision right now. {k.expiring_90} contract{k.expiring_90 !== 1 ? "s" : ""} expire in the next 90 days.</>}
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-ink-mute dark:text-slate-400">Deadlines are expiry minus the notice period, so you see the last day to act, not the day the contract ends.</p>
      </section>

      <section className="grid grid-cols-2 gap-4 lg:grid-cols-5" aria-label="Key figures">
        <Kpi label="Contracts" value={k.contracts} sub="incl. SOWs, work orders & amendments" />
        <Kpi label="Annual value" value={usd(k.annual_value)} sub="active, amendment-adjusted" />
        <Kpi label="Expiring in 90 days" value={k.expiring_90} sub={`${usd(k.expiring_90_value)} at stake`} sev="high" />
        <Kpi label="Auto-renew, notice due" value={k.autorenew_notice_soon} sub={`${k.autorenew_notice_passed} already passed`} sev="critical" />
        <Kpi label="Uncapped liability" value={k.uncapped} sub="vendors with unlimited exposure" sev="critical" />
      </section>

      <div className="flex flex-wrap items-start gap-5">
        <section className="min-w-0 flex-[999_1_620px] rounded-xl border border-line bg-white p-5 dark:border-slate-700 dark:bg-slate-800" aria-label="Decision queue">
          <div className="flex flex-wrap items-baseline justify-between gap-2"><h2 className="text-lg font-semibold">Decision queue</h2><span className="text-sm text-ink-mute dark:text-slate-400">sorted by last day to act</span></div>
          <ul className="mt-3 divide-y divide-line dark:divide-slate-700">
            {queue.map((i) => {
              const a = action(i);
              return (
                <li key={i.id} className="grid items-center gap-x-4 gap-y-1 py-3 md:grid-cols-[minmax(0,2.2fr)_minmax(0,1.3fr)_auto_auto]">
                  <div className="min-w-0"><Link to={`/contracts/${i.id}`} className="font-semibold hover:underline">{i.title}</Link>
                    <div className="text-xs text-ink-mute dark:text-slate-400"><Link to={`/vendors/${encodeURIComponent(i.vendor)}`} className="hover:underline">{i.vendor}</Link>{i.property ? ` · ${i.property}` : ""} · {i.auto_renew ? "auto-renews" : "no auto-renew"}</div></div>
                  <div><SeverityChip sev={a.sev} label={a.chip} /></div>
                  <div className="text-right tabular-nums"><b>{usd(i.annual_value)}</b><div className="text-xs text-ink-mute dark:text-slate-400">per year</div></div>
                  <Link to={`/contracts/${i.id}`} className={`inline-flex min-h-[44px] items-center justify-center rounded-lg border px-4 text-sm font-semibold ${a.primary ? "border-indigo-600 bg-indigo-600 text-white hover:bg-indigo-700" : "border-slate-300 bg-white hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-800"}`}>{a.label}</Link>
                </li>
              );
            })}
            {!queue.length && <li className="py-6 text-center text-sm text-ink-mute">Nothing needs a decision in the next 90 days.</li>}
          </ul>
        </section>

        <aside className="flex min-w-0 flex-[1_1_320px] flex-col gap-5">
          <Card title="Next 30 / 60 / 90 days">
            <table className="w-full text-sm"><thead><tr><th className="pb-1 text-left text-xs font-semibold uppercase text-ink-mute">Window</th><th className="pb-1 text-right text-xs font-semibold uppercase text-ink-mute">Contracts</th><th className="pb-1 text-right text-xs font-semibold uppercase text-ink-mute">Value</th></tr></thead>
              <tbody>{(["30", "60", "90"] as const).map((key) => <tr key={key} className="border-t border-line dark:border-slate-700"><td className="py-2"><SeverityChip sev={lanes[key].severity} label={`≤${key} days`} /></td><td className="py-2 text-right tabular-nums">{lanes[key].count}</td><td className="py-2 text-right tabular-nums">{usd(lanes[key].value)}</td></tr>)}</tbody></table>
          </Card>
          <Card title="Needs attention">
            <div className="space-y-3 text-sm">
              {([["uncapped", "Uncapped liability", "critical"], ["pd_without_dpa", "Personal data, no DPA", "critical"], ["no_tfc", "No termination for convenience", "high"]] as [string, string, Sev][]).map(([key, label, sev]) => (
                <div key={key}><div className="mb-1 flex items-center gap-2 font-medium">{label} <SeverityChip sev={sev} label={String(risks[key].length)} /></div>
                  <ul className="space-y-0.5">{risks[key].slice(0, 4).map((r) => <li key={r.id}><Link className="text-indigo-600 hover:underline dark:text-indigo-400" to={`/contracts/${r.id}`}>{r.title}</Link></li>)}{!risks[key].length && <li className="text-ink-mute">None</li>}</ul></div>
              ))}
            </div>
          </Card>
        </aside>
      </div>

      <OpsStrip />

      <Card title="Expiries over the next 12 months (contracts per month)">
        <div className="h-56">
          <ResponsiveContainer>
            <BarChart data={monthly} margin={{ left: 0, right: 8 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="label" fontSize={11} />
              <YAxis allowDecimals={false} fontSize={11} width={28} />
              <Tooltip formatter={(v: number, n: string, p) => n === "count" ? [`${v} contracts (${usd((p.payload as { value: number }).value)})`, "Expiring"] : [v, n]} />
              <Bar dataKey="count" fill="#0E6B5E" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <section className="flex flex-wrap items-center gap-4 rounded-xl border border-indigo-200 bg-indigo-50 p-5 dark:border-slate-700 dark:bg-slate-800">
        <div className="min-w-[280px] flex-1"><h2 className="font-serif text-2xl">Ask your portfolio anything</h2><p className="text-sm text-ink-mute dark:text-slate-400">Answers show the SQL or the cited clause, so you can verify them.</p></div>
        <div className="flex flex-wrap gap-2">{["Which contracts renew in 60 days?", "Who has no termination for convenience?", "Which vendors have uncapped liability?"].map((t) => (
          <Link key={t} to={`/ask?q=${encodeURIComponent(t)}`} className="inline-flex min-h-[44px] items-center rounded-lg border border-slate-300 bg-white px-4 text-sm font-semibold hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-800">{t}</Link>))}</div>
      </section>
    </div>
  );
}
