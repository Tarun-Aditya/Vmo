import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../lib";
import { Loading } from "../ui";

type C = { id: number; vendor: string; kind: string; name: string; contract_id: number | null; contract_title: string | null; page: number | null; expiry_date: string | null; received_on: string | null;
  reference: string | null; status: "expired" | "expiring" | "missing" | "valid"; days_left: number | null; properties: string[] };
const ST: Record<C["status"], { label: string; glyph: string; cls: string }> = {
  expired: { label: "Expired", glyph: "▲▲", cls: "border-red-600 bg-red-100 text-red-900 dark:bg-red-950 dark:text-red-200" },
  expiring: { label: "Expiring", glyph: "▲", cls: "border-orange-500 bg-orange-100 text-orange-900 dark:bg-orange-950 dark:text-orange-200" },
  missing: { label: "Not on file", glyph: "●", cls: "border-amber-500 bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200" },
  valid: { label: "Valid", glyph: "✓", cls: "border-emerald-600 bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200" },
};
const day = (d: string) => new Date(d + "T00:00:00").toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });

/** The certificates each vendor's contract obliges it to hold, and whether the copy on file is still in date. */
export default function Certificates() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["certificates"], queryFn: () => api<{ certificates: C[]; summary: Record<C["status"], number>; soon_days: number }>("/api/certificates") });
  const [f, setF] = useState<C["status"] | "all">("all");
  const save = useMutation({ mutationFn: (v: { id: number; expiry_date: string }) => api(`/api/certificates/${v.id}`, { method: "PATCH", body: JSON.stringify({ expiry_date: v.expiry_date, received_on: new Date().toISOString().slice(0, 10) }) }), onSuccess: () => qc.invalidateQueries({ queryKey: ["certificates"] }) });
  if (!q.data) return <Loading q={q} />;
  const { certificates, summary, soon_days } = q.data;
  const shown = certificates.filter((c) => f === "all" || c.status === f);
  return (
    <div className="space-y-5">
      <header><h1 className="font-serif text-3xl md:text-4xl">Certificates</h1>
        <p className="mt-1 max-w-3xl text-sm text-ink-mute dark:text-slate-400">What each vendor must hold under its contract: insurance, food safety, statutory inspections, payment-card security. The contract says a certificate is required; the expiry date comes from the certificate, so record it here when the vendor sends a new one.</p></header>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by status">
        <button type="button" onClick={() => setF("all")} aria-pressed={f === "all"} className={`min-h-[44px] rounded-lg border px-4 text-sm font-semibold ${f === "all" ? "border-indigo-600 bg-indigo-600 text-white" : "border-slate-300 bg-white dark:border-slate-600 dark:bg-slate-800"}`}>All {certificates.length}</button>
        {(Object.keys(ST) as C["status"][]).map((k) => (
          <button key={k} type="button" onClick={() => setF(k)} aria-pressed={f === k} className={`min-h-[44px] rounded-lg border px-4 text-sm font-semibold ${f === k ? "border-indigo-600 bg-indigo-600 text-white" : "border-slate-300 bg-white dark:border-slate-600 dark:bg-slate-800"}`}>
            <span aria-hidden>{ST[k].glyph}</span> {ST[k].label}{k === "expiring" ? ` (${soon_days} days)` : ""} {summary[k]}</button>))}
      </div>
      <div className="overflow-x-auto rounded-xl border border-line bg-white dark:border-slate-700 dark:bg-slate-800">
        <table className="w-full text-[13px]">
          <thead className="bg-slate-50 text-left text-[11.5px] uppercase tracking-wide text-ink-mute dark:bg-slate-900"><tr><th className="px-3 py-2">Status</th><th className="px-3 py-2">Certificate</th><th className="px-3 py-2">Vendor</th><th className="px-3 py-2">Required by</th><th className="px-3 py-2">Expires</th><th className="px-3 py-2">Record a new expiry date</th></tr></thead>
          <tbody>{shown.map((c) => (
            <tr key={c.id} className="border-t border-slate-100 align-top dark:border-slate-700">
              <td className="px-3 py-2.5"><span className={`inline-flex items-center gap-1 whitespace-nowrap rounded border px-1.5 py-0.5 text-xs font-medium ${ST[c.status].cls}`}><span aria-hidden>{ST[c.status].glyph}</span>{ST[c.status].label}</span></td>
              <td className="px-3 py-2.5 font-medium">{c.name}{c.reference && <div className="text-xs font-normal text-ink-mute">{c.reference}</div>}</td>
              <td className="px-3 py-2.5"><Link className="text-indigo-600 hover:underline dark:text-indigo-300" to={`/vendors/${encodeURIComponent(c.vendor)}`}>{c.vendor}</Link>
                {!!c.properties.length && <div className="text-xs text-ink-mute">{c.properties.length} propert{c.properties.length === 1 ? "y" : "ies"}</div>}</td>
              <td className="px-3 py-2.5">{c.contract_id ? <Link className="text-indigo-600 hover:underline dark:text-indigo-300" to={`/contracts/${c.contract_id}`}>{c.contract_title}</Link> : "—"}{c.page ? <span className="text-xs text-ink-mute"> · p.{c.page}</span> : null}</td>
              <td className="px-3 py-2.5 tabular-nums">{c.expiry_date ? <>{day(c.expiry_date)}<div className={`text-xs ${c.status === "valid" ? "text-ink-mute" : "font-semibold text-red-700 dark:text-red-300"}`}>{c.days_left! < 0 ? `${-c.days_left!} days ago` : `in ${c.days_left} days`}</div></> : <span className="text-ink-mute">Ask the vendor for a copy</span>}</td>
              <td className="px-3 py-2.5"><form className="flex items-center gap-2" onSubmit={(e) => { e.preventDefault(); const d = String(new FormData(e.currentTarget).get("d") || ""); if (d) { save.mutate({ id: c.id, expiry_date: d }); e.currentTarget.reset(); } }}>
                <input name="d" type="date" required aria-label={`New expiry date for ${c.name}, ${c.vendor}`} className="min-h-[36px] rounded border border-slate-300 px-2 dark:border-slate-600 dark:bg-slate-900" />
                <button className="min-h-[36px] rounded border border-slate-300 px-3 font-semibold hover:bg-slate-50 dark:border-slate-600 dark:hover:bg-slate-700" disabled={save.isPending}>Save</button></form></td>
            </tr>))}
            {!shown.length && <tr><td colSpan={6} className="px-3 py-6 text-center text-ink-mute">{certificates.length ? "None in this status." : "No contract on file requires a certificate yet."}</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
