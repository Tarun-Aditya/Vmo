import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Meter, Pill, TierChip, scoreTone } from "../components/vmo";
import { api, usd } from "../lib";
import { Card, Loading } from "../ui";

type Comp = { score: number; drivers: string[]; share?: number };
type V = { vendor: string; score: number; tier: string; components: Record<string, Comp>; documents: number; annual_value: number };
type Res = { vendors: V[]; weights: { key: string; label: string; description: string; weight: number; enabled: boolean }[] };
type BV = { contract_id: number; title: string; vendor: string; type: string; value: number; outlier: boolean; breaches_policy: boolean; vs_median: number | null };
type Metric = { metric_key: string; metric: string; unit: string; n: number; min: number; p25: number; median: number; p75: number; max: number; policy: { name: string; operator: string; threshold: number; severity: string }[]; values: BV[]; breaching: number; vendors: { vendor: string; median: number; n: number }[] };
type Bench = { metrics: Metric[]; governing_law: { governing_law: string; n: number }[]; liability_caps: { cap: string; n: number }[] };

const fmt = (n: number, unit: string) => (unit === "USD" ? usd(n) : `${Number.isInteger(n) ? n : n.toFixed(2)}${unit === "%" ? "%" : unit === "days" || unit === "hours" || unit === "years" ? ` ${unit}` : unit ? ` ${unit}` : ""}`);

export function ScoreBlock({ v, weights, open = true }: { v: { score: number; tier: string; components: Record<string, Comp> }; weights: Res["weights"]; open?: boolean }) {
  return (
    <div className="grid gap-x-6 gap-y-3 md:grid-cols-2">
      {weights.filter((w) => w.enabled).map((w) => {
        const c = v.components[w.key];
        if (!c) return null;
        return (
          <div key={w.key}>
            <div className="flex items-center justify-between text-sm"><span className="font-medium">{w.label}</span><span className="tabular-nums text-slate-500">{c.score.toFixed(0)} · weight {w.weight}</span></div>
            <Meter value={c.score} tone={scoreTone(c.score)} label={`${w.label} risk ${c.score.toFixed(0)} of 100`} />
            {open && <ul className="mt-1 space-y-0.5 text-xs text-slate-600 dark:text-slate-300">{c.drivers.length ? c.drivers.map((d, i) => <li key={i}>• {d}</li>) : <li className="text-slate-400">Nothing flagged.</li>}</ul>}
          </div>);
      })}
    </div>
  );
}

function Scorecards() {
  const q = useQuery({ queryKey: ["risk"], queryFn: () => api<Res>("/api/risk/vendors") });
  const [open, setOpen] = useState<string | null>(null);
  if (!q.data) return <Loading q={q} />;
  const first = open ?? q.data.vendors[0]?.vendor;
  return (
    <div className="space-y-3">
      <p className="text-sm text-slate-600 dark:text-slate-300">Each vendor is scored 0–100 (higher = riskier) from five explainable components: {q.data.weights.filter((w) => w.enabled).map((w) => `${w.label} (${w.weight})`).join(", ")}. Weights are set in <Link className="text-indigo-600 hover:underline dark:text-indigo-400" to="/admin/risk">Admin → Risk scoring</Link>.</p>
      <ul className="space-y-2" aria-label="Vendor risk scorecards">
        {q.data.vendors.map((v, i) => (
          <li key={v.vendor} className="rounded-lg border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-800">
            <button className="flex w-full items-center gap-4 px-4 py-3 text-left" onClick={() => setOpen(first === v.vendor && open !== null ? "" : v.vendor)} aria-expanded={first === v.vendor}>
              <span className="w-6 text-sm text-slate-400">{i + 1}</span>
              <span className="min-w-0 flex-1"><span className="font-semibold">{v.vendor}</span><span className="ml-2 text-xs text-slate-500">{v.documents} docs · {usd(v.annual_value)} a year</span></span>
              <span className="hidden w-48 sm:block"><Meter value={v.score} tone={scoreTone(v.score)} label={`${v.vendor} risk score ${v.score}`} /></span>
              <span className="w-12 text-right text-xl font-semibold tabular-nums">{v.score.toFixed(0)}</span>
              <TierChip tier={v.tier} />
              <span aria-hidden className="text-slate-400">{first === v.vendor ? "▾" : "▸"}</span>
            </button>
            {first === v.vendor && (
              <div className="space-y-3 border-t border-slate-100 px-4 py-3 dark:border-slate-700">
                <ScoreBlock v={v} weights={q.data.weights} />
                <div className="flex gap-4 text-sm"><Link className="text-indigo-600 hover:underline dark:text-indigo-400" to={`/vendors/${encodeURIComponent(v.vendor)}`}>Open vendor profile</Link><Link className="text-indigo-600 hover:underline dark:text-indigo-400" to={`/ask?q=${encodeURIComponent(`Why is ${v.vendor.split(" ")[0]} rated ${v.tier} risk?`)}`}>Ask about it</Link></div>
              </div>)}
          </li>))}
      </ul>
    </div>
  );
}

function Strip({ m }: { m: Metric }) {
  const lo = Math.min(m.min, ...m.policy.map((p) => p.threshold)), hi = Math.max(m.max, ...m.policy.map((p) => p.threshold));
  const span = hi - lo || 1;
  const x = (v: number) => 40 + ((v - lo) / span) * 920;
  const anchor = (v: number): "start" | "middle" | "end" => (x(v) < 150 ? "start" : x(v) > 850 ? "end" : "middle");
  const seen: Record<string, number> = {};
  return (
    <svg viewBox="0 0 1000 190" className="w-full" role="img" aria-label={`${m.metric}: values by contract, median ${fmt(m.median, m.unit)}`}>
      <rect x={x(m.p25)} y={34} width={Math.max(x(m.p75) - x(m.p25), 4)} height={84} fill="#e0e7ff" opacity={0.75} />
      <line x1={x(m.median)} x2={x(m.median)} y1={28} y2={124} stroke="#4f46e5" strokeWidth={3} />
      <text x={x(m.median)} y={22} fontSize={24} textAnchor={anchor(m.median)} fill="#4f46e5">median {fmt(m.median, m.unit)}</text>
      {m.policy.map((p, i) => (<g key={i}><line x1={x(p.threshold)} x2={x(p.threshold)} y1={34} y2={124} stroke="#dc2626" strokeWidth={2.5} strokeDasharray="8 6" /><text x={x(p.threshold)} y={150 + (i % 2) * 0} fontSize={22} textAnchor={anchor(p.threshold)} fill="#dc2626">policy {p.operator} {fmt(p.threshold, m.unit)}</text></g>))}
      <line x1={40} x2={960} y1={76} y2={76} stroke="#94a3b8" strokeWidth={2} />
      {m.values.map((v) => {
        const k = `${v.value}`; seen[k] = (seen[k] ?? 0) + 1;
        const y = 76 + (((seen[k] - 1) % 5) - 2) * 14;
        return <circle key={v.contract_id} cx={x(v.value)} cy={y} r={8} fill={v.breaches_policy ? "#dc2626" : "#475569"} stroke={v.outlier ? "#f59e0b" : "#fff"} strokeWidth={v.outlier ? 4 : 1.5}><title>{`${v.title}: ${fmt(v.value, m.unit)}${v.breaches_policy ? " — outside policy" : ""}${v.outlier ? " — outlier" : ""}`}</title></circle>;
      })}
      <text x={40} y={182} fontSize={22} fill="#64748b">{fmt(lo, m.unit)}</text><text x={960} y={182} fontSize={22} textAnchor="end" fill="#64748b">{fmt(hi, m.unit)}</text>
    </svg>
  );
}

function Benchmarks() {
  const q = useQuery({ queryKey: ["bench"], queryFn: () => api<Bench>("/api/benchmarks") });
  if (!q.data) return <Loading q={q} />;
  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-600 dark:text-slate-300">How each term compares across the portfolio. Each dot is a contract; the shaded band is the middle half, the blue line the median, the red dashed line our policy. <b className="text-red-600">Red dots</b> breach policy; an <b className="text-amber-600">amber ring</b> marks a statistical outlier.</p>
      <div className="grid gap-4 lg:grid-cols-2">
        {q.data.metrics.map((m) => {
          const bad = m.values.filter((v) => v.breaches_policy || v.outlier);
          return (
            <Card key={m.metric_key} title={m.metric} right={<span className="text-xs text-slate-500">{m.n} contracts · {m.min === m.max ? `all ${fmt(m.min, m.unit)}` : `${fmt(m.min, m.unit)} – ${fmt(m.max, m.unit)}`}</span>}>
              <Strip m={m} />
              <div className="mt-1 flex flex-wrap items-center gap-2 text-xs">
                {m.breaching ? <Pill cls="bg-red-100 text-red-900 dark:bg-red-950 dark:text-red-200">▲ {m.breaching} outside policy</Pill> : <Pill cls="bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200">✓ all within policy</Pill>}
                {m.vendors.length > 1 && <span className="text-slate-500">lowest: {m.vendors[0].vendor.split(" ")[0]} {fmt(m.vendors[0].median, m.unit)} · highest: {m.vendors[m.vendors.length - 1].vendor.split(" ")[0]} {fmt(m.vendors[m.vendors.length - 1].median, m.unit)}</span>}
              </div>
              {bad.length > 0 && <ul className="mt-2 space-y-0.5 text-xs">{bad.slice(0, 4).map((v) => <li key={v.contract_id}><Link className="text-indigo-600 hover:underline dark:text-indigo-400" to={`/contracts/${v.contract_id}`}>{v.title}</Link>: <b>{fmt(v.value, m.unit)}</b>{v.vs_median !== null && v.vs_median !== 0 ? ` (${v.vs_median > 0 ? "+" : ""}${Math.round(v.vs_median * 100)}% vs median)` : ""}</li>)}{bad.length > 4 && <li className="text-slate-500">…and {bad.length - 4} more</li>}</ul>}
            </Card>);
        })}
        <Card title="Liability cap"><ul className="space-y-1 text-sm">{q.data.liability_caps.map((c) => <li key={c.cap} className="flex justify-between"><span>{c.cap}</span><b className="tabular-nums">{c.n}</b></li>)}</ul></Card>
        <Card title="Governing law"><ul className="space-y-1 text-sm">{q.data.governing_law.map((c) => <li key={c.governing_law} className="flex justify-between"><span>{c.governing_law}</span><b className="tabular-nums">{c.n}</b></li>)}</ul></Card>
      </div>
    </div>
  );
}

export default function Risk() {
  const [tab, setTab] = useState<"score" | "bench">("score");
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Vendor risk & benchmarks</h1>
        <p className="text-sm text-slate-500">Which vendors need attention and why, and how every term compares across the portfolio.</p>
      </div>
      <div className="flex gap-2" role="tablist">
        {([["score", "Vendor scorecards"], ["bench", "Term benchmarks"]] as const).map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)} className={`rounded-t px-3 py-1.5 text-sm font-medium ${tab === k ? "bg-indigo-600 text-white" : "bg-slate-200 dark:bg-slate-700"}`}>{l}</button>)}
      </div>
      {tab === "score" ? <Scorecards /> : <Benchmarks />}
    </div>
  );
}
