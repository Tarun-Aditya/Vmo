import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, usd } from "../lib";
import { Loading } from "../ui";

type P = { id: number; property: string; city: string | null; country: string | null; kind: string | null; rooms: number | null; contracts: number; named_contracts: number; vendors: number;
  annual_value: number; direct_value: number; shared_value: number; value_per_room: number | null; ending_90: number; categories: string[] };
type Item = { contract_id: number; title: string; vendor: string; category: string; type: string; basis: string; contract_annual_value: number | null; share: number; attributed_value: number | null;
  exit?: "sale" | "notice" | "locked"; exit_text?: string; exit_from?: string | null; locked_value: number; expiry_date: string | null };
type Sale = { locked_contracts: number; locked_value: number; exit_on_sale: number; on_notice: number };
const EXIT: Record<string, { glyph: string; cls: string }> = { sale: { glyph: "✓", cls: "text-emerald-700 dark:text-emerald-300" }, notice: { glyph: "●", cls: "text-amber-700 dark:text-amber-300" }, locked: { glyph: "▲", cls: "font-semibold text-red-700 dark:text-red-300" } };
const BASIS: Record<string, string> = { named: "names this property", children: "group agreement · its schedules name this property", group: "group agreement · covers every property", stated: "group agreement · coverage recorded" };
const btn = "inline-flex min-h-[44px] items-center rounded-lg border border-slate-300 px-4 hover:bg-slate-50 dark:border-slate-600 dark:hover:bg-slate-700";

function Detail({ id }: { id: number }) {
  const q = useQuery({ queryKey: ["property", id], queryFn: () => api<{ contracts: Item[]; sale: Sale }>(`/api/properties/${id}`) });
  if (!q.data) return <Loading q={q} />;
  const sale = q.data.sale;
  return (
    <div className="mt-3 overflow-x-auto">
      <p className="mb-2 rounded-lg bg-paper p-3 text-[13px] dark:bg-slate-900"><b>If this property were sold:</b> {sale.exit_on_sale} contract{sale.exit_on_sale !== 1 ? "s" : ""} can be ended on the sale, {sale.on_notice} on notice, and{" "}
        <span className={sale.locked_contracts ? "font-semibold text-red-700 dark:text-red-300" : ""}>{sale.locked_contracts} cannot be ended early</span>
        {sale.locked_contracts ? <>: a buyer inherits about {usd(Math.round(sale.locked_value))} of commitments until they run out.</> : "."}</p>
      <table className="w-full text-[13px]">
        <thead><tr className="text-left text-xs uppercase text-ink-mute"><th className="py-1.5 pr-2 font-semibold">Contract</th><th className="py-1.5 pr-2 font-semibold">Why it counts here</th><th className="py-1.5 pr-2 font-semibold">On a sale</th><th className="py-1.5 text-right font-semibold">Per year</th></tr></thead>
        <tbody>{q.data.contracts.map((c) => (
          <tr key={c.contract_id} className="border-t border-slate-100 dark:border-slate-700">
            <td className="py-1.5 pr-2"><Link className="text-indigo-600 hover:underline dark:text-indigo-300" to={`/contracts/${c.contract_id}`}>{c.vendor}</Link><div className="text-xs text-ink-mute">{c.type} · {c.category}</div></td>
            <td className="py-1.5 pr-2 text-xs text-ink-mute">{BASIS[c.basis]}{c.basis !== "named" && c.contract_annual_value ? ` · ${Math.round(Number(c.share) * 100)}% of ${usd(c.contract_annual_value)}` : ""}</td>
            <td className={`py-1.5 pr-2 text-xs ${EXIT[c.exit ?? "notice"].cls}`}><span aria-hidden>{EXIT[c.exit ?? "notice"].glyph}</span> {c.exit_text}{c.exit_from && c.exit_from !== "this contract" ? <span className="font-normal text-ink-mute"> (from {c.exit_from})</span> : null}
              {c.exit === "locked" && c.locked_value > 0 ? <div className="font-normal text-ink-mute">about {usd(Math.round(c.locked_value))} left to run</div> : null}</td>
            <td className="py-1.5 text-right tabular-nums">{c.attributed_value ? usd(Math.round(Number(c.attributed_value))) : "—"}</td>
          </tr>))}</tbody>
      </table>
    </div>);
}

/** The owner's view of each property: what it costs under contract (its own schedules plus its share of group agreements), with whom, what ends soon,
 *  and what a buyer would inherit if it were sold. */
export default function Properties() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["properties"], queryFn: () => api<{ properties: P[]; group_level: number; rooms_known: boolean }>("/api/properties") });
  const [open, setOpen] = useState<number | null>(null);
  const save = useMutation({ mutationFn: (v: { id: number; rooms: number }) => api(`/api/properties/${v.id}`, { method: "PATCH", body: JSON.stringify({ rooms: v.rooms }) }), onSuccess: () => qc.invalidateQueries() });
  if (!q.data) return <Loading q={q} />;
  const { properties, group_level, rooms_known } = q.data;
  const total = properties.reduce((a, p) => a + Number(p.annual_value), 0);
  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div><h1 className="font-serif text-3xl md:text-4xl">Properties</h1>
          <p className="mt-1 max-w-3xl text-sm text-ink-mute dark:text-slate-400">What each property costs under contract: the schedules that name it, plus its share of the {group_level} group-level agreement{group_level !== 1 ? "s" : ""} that cover it
            ({rooms_known ? "split by number of rooms" : "split equally until room counts are entered"}). {usd(Math.round(total))} a year across {properties.length} properties.</p></div>
        <Link className={`${btn} border-indigo-600 bg-indigo-600 text-sm font-semibold text-white hover:bg-indigo-700`} to="/compare">Compare properties</Link>
      </header>
      {!properties.length && <p className="rounded-xl border border-line bg-white p-6 text-sm text-ink-mute dark:border-slate-700 dark:bg-slate-800">No contracts carry a property yet. A property is read from the document (a "Property:" line or the sidecar file).</p>}
      <div className="grid gap-4 lg:grid-cols-2">
        {properties.map((p) => (
          <section key={p.id} className="rounded-xl border border-line bg-white p-5 dark:border-slate-700 dark:bg-slate-800" aria-label={p.property}>
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="font-serif text-2xl">{p.property}</h2>
              <span className="text-xs text-ink-mute">{[p.kind, p.city].filter(Boolean).join(" · ")}</span>
            </div>
            <dl className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
              <div><dt className="text-xs uppercase text-ink-mute">Per year</dt><dd className="font-serif text-2xl tabular-nums">{usd(Math.round(Number(p.annual_value)))}</dd></div>
              <div><dt className="text-xs uppercase text-ink-mute">Per room</dt><dd className="font-serif text-2xl tabular-nums">{p.value_per_room ? usd(Math.round(p.value_per_room)) : "—"}</dd></div>
              <div><dt className="text-xs uppercase text-ink-mute">Rooms</dt><dd className="font-serif text-2xl tabular-nums">
                {p.rooms ?? <form onSubmit={(e) => { e.preventDefault(); const n = Number(new FormData(e.currentTarget).get("rooms")); if (n > 0) save.mutate({ id: p.id, rooms: n }); }}>
                  <input name="rooms" type="number" min={1} aria-label={`Rooms at ${p.property}`} placeholder="enter" className="w-20 rounded border border-slate-300 px-1.5 py-0.5 text-sm font-normal dark:border-slate-600 dark:bg-slate-900" /></form>}</dd></div>
              <div><dt className="text-xs uppercase text-ink-mute">Vendors</dt><dd className="font-serif text-2xl tabular-nums">{p.vendors}</dd></div>
            </dl>
            <p className="mt-2 text-xs text-ink-mute">{usd(Math.round(Number(p.direct_value)))} in {p.named_contracts} contract{p.named_contracts !== 1 ? "s" : ""} naming this property · {usd(Math.round(Number(p.shared_value)))} share of {p.contracts - p.named_contracts} group agreement{p.contracts - p.named_contracts !== 1 ? "s" : ""}</p>
            {p.ending_90 > 0 && <p className="mt-2 text-sm font-semibold text-orange-700 dark:text-orange-300">▲ {p.ending_90} ending within 90 days</p>}
            <ul className="mt-3 flex flex-wrap gap-1.5 text-xs">{p.categories.map((c) => <li key={c} className="rounded-full bg-paper px-2 py-0.5 dark:bg-slate-700">{c}</li>)}</ul>
            <div className="mt-4 flex flex-wrap gap-2 text-sm font-semibold">
              <button type="button" className={btn} aria-expanded={open === p.id} onClick={() => setOpen(open === p.id ? null : p.id)}>{open === p.id ? "Hide" : "What makes up the cost"}</button>
              <Link className={btn} to={`/contracts?property=${encodeURIComponent(p.property)}`}>Contracts</Link>
              <Link className={btn} to={`/map?property=${encodeURIComponent(p.property)}`}>On the map</Link>
            </div>
            {open === p.id && <Detail id={p.id} />}
          </section>))}
      </div>
    </div>
  );
}
