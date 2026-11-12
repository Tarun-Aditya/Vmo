import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, usd } from "../lib";
import { Loading } from "../ui";

type P = { property: string; contracts: number; vendors: number; annual_value: number; ending_90: number; categories: string[]; vendor_names: string[] };

/** One card per hotel: what is contracted there, with whom, and what ends soon. */
export default function Properties() {
  const q = useQuery({ queryKey: ["properties"], queryFn: () => api<{ properties: P[]; group_level: number }>("/api/properties") });
  if (!q.data) return <Loading q={q} />;
  const { properties, group_level } = q.data;
  return (
    <div className="space-y-6">
      <header><h1 className="font-serif text-3xl md:text-4xl">Properties</h1>
        <p className="mt-1 text-sm text-ink-mute dark:text-slate-400">What is contracted at each property, with whom, and what ends soon. {group_level} group-level agreement{group_level !== 1 ? "s" : ""} apply to all properties.</p></header>
      {!properties.length && <p className="rounded-xl border border-line bg-white p-6 text-sm text-ink-mute dark:border-slate-700 dark:bg-slate-800">No contracts carry a property yet. A property is read from the document (a "Property:" line or the sidecar file).</p>}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {properties.map((p) => (
          <section key={p.property} className="rounded-xl border border-line bg-white p-5 dark:border-slate-700 dark:bg-slate-800" aria-label={p.property}>
            <h2 className="font-serif text-2xl">{p.property}</h2>
            <dl className="mt-3 grid grid-cols-3 gap-2 text-sm">
              <div><dt className="text-xs uppercase text-ink-mute">Contracts</dt><dd className="font-serif text-2xl tabular-nums">{p.contracts}</dd></div>
              <div><dt className="text-xs uppercase text-ink-mute">Vendors</dt><dd className="font-serif text-2xl tabular-nums">{p.vendors}</dd></div>
              <div><dt className="text-xs uppercase text-ink-mute">Per year</dt><dd className="font-serif text-2xl tabular-nums">{usd(p.annual_value)}</dd></div>
            </dl>
            {p.ending_90 > 0 && <p className="mt-2 text-sm font-semibold text-orange-700 dark:text-orange-300">▲ {p.ending_90} ending within 90 days</p>}
            <ul className="mt-3 flex flex-wrap gap-1.5 text-xs">{p.categories.map((c) => <li key={c} className="rounded-full bg-paper px-2 py-0.5 dark:bg-slate-700">{c}</li>)}</ul>
            <div className="mt-4 flex flex-wrap gap-2 text-sm font-semibold">
              <Link className="inline-flex min-h-[44px] items-center rounded-lg border border-slate-300 px-4 hover:bg-slate-50 dark:border-slate-600" to={`/contracts?property=${encodeURIComponent(p.property)}`}>Contracts</Link>
              <Link className="inline-flex min-h-[44px] items-center rounded-lg border border-slate-300 px-4 hover:bg-slate-50 dark:border-slate-600" to={`/map?property=${encodeURIComponent(p.property)}`}>On the map</Link>
              <Link className="inline-flex min-h-[44px] items-center rounded-lg border border-slate-300 px-4 hover:bg-slate-50 dark:border-slate-600" to={`/ask?q=${encodeURIComponent("Which contracts are at " + p.property + "?")}`}>Ask</Link>
            </div>
          </section>))}
      </div>
    </div>
  );
}
