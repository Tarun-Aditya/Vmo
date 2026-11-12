import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, usd } from "../lib";
import { Loading } from "../ui";

type Pt = { property: string; contract_id: number; vendor: string; value: number; page: number | null };
type M = { key: string; name: string; unit: string | null; lower_better: boolean | null; spread_pct: number; best: number | null; saving_estimate?: number; points: Pt[] };
type B = { vendor?: string; category: string; properties: string[]; measures: M[]; saving_estimate: number };

const fmt = (v: number, unit: string | null) => (unit?.startsWith("USD/") ? (v >= 100 ? "$" + Math.round(v).toLocaleString("en-US") : "$" + v.toFixed(2)) : v.toLocaleString("en-US", { maximumFractionDigits: 2 }));
const short = (p: string, all: string[]) => { const w = all.map((x) => x.split(" ")[0]); return w.every((x) => x === w[0]) ? p.split(" ").slice(1).join(" ") : p; };

function Measure({ m, props }: { m: M; props: string[] }) {
  const max = Math.max(...m.points.map((p) => p.value));
  return (
    <div className="border-t border-slate-100 py-3 first:border-t-0 dark:border-slate-700">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold">{m.name}{m.unit ? <span className="ml-1 font-normal text-ink-mute">({m.unit})</span> : null}</h3>
        <span className="text-xs text-ink-mute">{m.spread_pct}% between lowest and highest{m.saving_estimate ? <strong className="ml-2 text-emerald-700 dark:text-emerald-300">about {usd(m.saving_estimate)} a year at the best rate</strong> : null}</span>
      </div>
      <ul className="mt-2 space-y-1.5">{m.points.map((p) => {
        const best = m.best !== null && p.value === m.best, worst = m.lower_better !== null && p.value === (m.lower_better ? max : Math.min(...m.points.map((x) => x.value)));
        return (
          <li key={p.contract_id + p.property} className="grid grid-cols-[minmax(90px,170px)_1fr_auto] items-center gap-3 text-[13px]">
            <Link to={`/contracts/${p.contract_id}`} className="truncate text-indigo-600 hover:underline dark:text-indigo-300" title={`${p.property} · ${p.vendor}`}>{short(p.property, props)}</Link>
            <span className="h-2.5 rounded bg-slate-100 dark:bg-slate-700"><span className={`block h-2.5 rounded ${best ? "bg-emerald-600" : worst ? "bg-orange-500" : "bg-slate-400"}`} style={{ width: `${(p.value / max) * 100}%` }} /></span>
            <span className="min-w-[104px] text-right tabular-nums">{fmt(p.value, m.unit)}{best ? <span className="ml-1 text-xs font-semibold text-emerald-700 dark:text-emerald-300">best</span> : worst ? <span className="ml-1 text-xs font-semibold text-orange-700 dark:text-orange-300">▲ worst</span> : null}</span>
          </li>);
      })}</ul>
    </div>);
}

/** The same vendor (or the same kind of service) at several properties: the rates and terms side by side, and what the gap is worth. */
export default function Compare() {
  const q = useQuery({ queryKey: ["compare"], queryFn: () => api<{ same_vendor: B[]; same_category: B[]; saving_estimate: number }>("/api/properties/compare") });
  if (!q.data) return <Loading q={q} />;
  const { same_vendor, same_category, saving_estimate } = q.data;
  const block = (b: B, key: string) => (
    <section key={key} className="rounded-xl border border-line bg-white p-5 dark:border-slate-700 dark:bg-slate-800">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-serif text-xl">{b.vendor ? <Link className="hover:underline" to={`/vendors/${encodeURIComponent(b.vendor)}`}>{b.vendor}</Link> : b.category}</h2>
        <span className="text-xs text-ink-mute">{b.vendor ? b.category + " · " : ""}{b.properties.length} properties</span>
      </div>
      <div className="mt-2">{b.measures.map((m) => <Measure key={m.key} m={m} props={b.properties} />)}</div>
    </section>);
  return (
    <div className="space-y-6">
      <header><h1 className="font-serif text-3xl md:text-4xl">Compare properties</h1>
        <p className="mt-1 max-w-3xl text-sm text-ink-mute dark:text-slate-400">Where one vendor serves several properties, the rates and terms each property signed, side by side. Values are read from the contracts; click a property to see the clause.
          {saving_estimate > 0 && <> Moving every property to the vendor's own best unit rate is worth about <strong className="text-emerald-700 dark:text-emerald-300">{usd(saving_estimate)} a year</strong> (same volumes assumed).</>}</p></header>
      {!same_vendor.length && !same_category.length && <p className="rounded-xl border border-line bg-white p-6 text-sm text-ink-mute dark:border-slate-700 dark:bg-slate-800">Nothing to compare yet: no vendor or category has contracts at two properties with differing terms.</p>}
      {!!same_vendor.length && <><h2 className="text-xs font-semibold uppercase tracking-wider text-ink-mute">Same vendor, different properties</h2><div className="grid gap-4 xl:grid-cols-2">{same_vendor.map((b) => block(b, "v" + b.vendor))}</div></>}
      {!!same_category.length && <><h2 className="text-xs font-semibold uppercase tracking-wider text-ink-mute">Same service, different vendors</h2><div className="grid gap-4 xl:grid-cols-2">{same_category.map((b) => block(b, "c" + b.category))}</div></>}
      <p className="text-xs text-ink-mute">Cost per room uses each property's room count (Properties). A saving is an estimate: the dearer property's yearly value × (1 − best rate ÷ its own rate).</p>
    </div>
  );
}
