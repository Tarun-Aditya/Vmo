import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, fmtDate, inr } from "../lib";
import { Card, ConfidenceBadge, Loading, Sev, SeverityChip, Td, Th } from "../ui";

type Node = { id: number; title: string; type: string; children: Node[] };
type Detail = {
  contract: { id: number; title: string; vendor: string; category: string; type: string; owner: string; status: string };
  clauses: { id: number; clause_type: string; heading: string; text: string; page: number }[];
  fields: { field: string; value: string | null; confidence: number | null; source_clause_id: number | null; source_page: number | null; source_heading: string | null }[];
  effective_terms: { field: string; value: unknown; source_id: number; source_title: string; overridden: boolean }[];
  hierarchy: Node; deviations: { severity: Sev; deviation_summary: string; heading: string }[];
  is_amendment: boolean; overrides: string[]; parent: { id: number; title: string } | null;
  signatures: { customer_signatory: string | null; customer_signed_date: string | null; supplier_signatory: string | null; supplier_signed_date: string | null; fully_executed: boolean };
};

const LABEL: Record<string, string> = {
  effective_date: "Effective date", expiry_date: "Expiry date", notice_period_days: "Notice period (days)", auto_renew: "Auto-renew",
  annual_value: "Annual value", total_value: "Total value", payment_terms_days: "Payment terms (days)", liability_cap_multiple: "Liability cap (× annual fees)",
  liability_cap_text: "Liability cap", termination_for_convenience: "Termination for convenience", governing_law: "Governing law",
  processes_personal_data: "Processes personal data", has_dpa: "Has DPA",
  customer_signatory: "Customer signatory", supplier_signatory: "Supplier signatory", customer_signed_date: "Customer signed", supplier_signed_date: "Supplier signed", fully_executed: "Fully signed",
};
function show(field: string, v: unknown): string {
  if (v === null || v === undefined || v === "null") return field === "liability_cap_multiple" ? "Uncapped / n.a." : "—";
  if (field.endsWith("_date")) return fmtDate(String(v));
  if (field.endsWith("_value")) return inr(v as number);
  if (typeof v === "boolean" || v === "True" || v === "False") return String(v) === "true" || v === "True" ? "Yes" : "No";
  return String(v);
}

function Tree({ n, current }: { n: Node; current: number }) {
  return (
    <ul className="ml-3 border-l border-slate-300 pl-3 text-sm dark:border-slate-600">
      <li className="py-0.5">
        <Link to={`/contracts/${n.id}`} className={n.id === current ? "font-semibold text-indigo-600 dark:text-indigo-400" : "hover:underline"}>
          <span className="mr-1 rounded bg-slate-200 px-1 text-[10px] dark:bg-slate-700">{n.type}</span>{n.title}
        </Link>
        {n.children.length > 0 && n.children.map((c) => <Tree key={c.id} n={c} current={current} />)}
      </li>
    </ul>
  );
}

export default function ContractDetail() {
  const { id } = useParams();
  const q = useQuery({ queryKey: ["contract", id], queryFn: () => api<Detail>(`/api/contracts/${id}`) });
  const [hl, setHl] = useState<number | null>(null);
  const refs = useRef<Record<number, HTMLDivElement | null>>({});
  useEffect(() => { setHl(null); }, [id]);
  useEffect(() => { if (hl) refs.current[hl]?.scrollIntoView({ behavior: "smooth", block: "center" }); }, [hl]);
  if (!q.data) return <Loading q={q} />;
  const d = q.data, c = d.contract;
  let lastPage = 0;
  return (
    <div className="space-y-4">
      <div>
        <Link to="/contracts" className="text-sm text-slate-500 hover:underline">← Contracts</Link>
        <h1 className="text-xl font-semibold">{c.title}</h1>
        <p className="text-sm text-slate-500">{c.vendor} · {c.type} · {c.category} · owner {c.owner} · <span className="capitalize">{c.status}</span>
          {d.parent && <> · amends/under <Link className="text-indigo-600 hover:underline" to={`/contracts/${d.parent.id}`}>{d.parent.title}</Link></>}</p>
      </div>
      <div className="grid gap-4 lg:grid-cols-5">
        <div className="space-y-4 lg:col-span-2">
          <Card title="Signatures" right={d.signatures.fully_executed ? <span className="font-bold text-emerald-600">✓ fully signed</span> : <span className="font-bold text-red-600">✗ not fully signed</span>}>
            <table className="w-full text-sm"><tbody>
              {([["Arcadia Retail Ltd", d.signatures.customer_signatory, d.signatures.customer_signed_date], [c.vendor, d.signatures.supplier_signatory, d.signatures.supplier_signed_date]] as [string, string | null, string | null][]).map(([party, who, when]) => (
                <tr key={party} className="border-t border-slate-100 dark:border-slate-700"><Td className="text-slate-500">{party}</Td>
                  <Td className="font-medium">{who ?? <span className="text-red-600">signature pending</span>}</Td><Td className="text-right tabular-nums">{when ? fmtDate(when) : "—"}</Td></tr>))}
            </tbody></table>
          </Card>

          <Card title="Extracted fields (click to see the source)">
            <table className="w-full text-sm"><tbody>
              {d.fields.filter((f) => f.field !== "liability_cap_text" && !/signat|signed|fully_executed/.test(f.field)).map((f) => (
                <tr key={f.field} onClick={() => f.source_clause_id && setHl(f.source_clause_id)}
                  className={`border-t border-slate-100 dark:border-slate-700 ${f.source_clause_id ? "cursor-pointer hover:bg-indigo-50 dark:hover:bg-slate-700" : ""} ${hl && hl === f.source_clause_id ? "bg-yellow-50 dark:bg-yellow-900/30" : ""}`}>
                  <Td className="text-slate-500">{LABEL[f.field] ?? f.field}</Td>
                  <Td className="font-medium tabular-nums">{show(f.field, f.value)}</Td>
                  <Td className="text-right"><ConfidenceBadge v={f.confidence} />
                    <div className="text-[11px] text-slate-500">{f.source_heading ? `${f.source_heading} · p.${f.source_page}` : `header · p.${f.source_page ?? 1}`}</div></Td>
                </tr>
              ))}
            </tbody></table>
          </Card>

          {!d.is_amendment && (
            <Card title="Effective terms (after amendments)">
              <table className="w-full text-sm">
                <thead><tr><Th>Term</Th><Th>Current value</Th><Th>Set by</Th></tr></thead>
                <tbody>
                  {d.effective_terms.filter((e) => e.field !== "liability_cap_text").map((e) => (
                    <tr key={e.field} className={`border-t border-slate-100 dark:border-slate-700 ${e.overridden ? "bg-indigo-50 dark:bg-indigo-950/40" : ""}`}>
                      <Td className="text-slate-500">{LABEL[e.field]}</Td>
                      <Td className="font-medium tabular-nums">{show(e.field, e.value)}</Td>
                      <Td className="text-xs">{e.overridden
                        ? <Link to={`/contracts/${e.source_id}`} className="font-medium text-indigo-700 hover:underline dark:text-indigo-300">⟲ Overridden by {e.source_title}</Link>
                        : <span className="text-slate-500">Original contract</span>}</Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
          {d.is_amendment && <Card title="This amendment overrides"><p className="text-sm">{d.overrides.map((o) => LABEL[o]).join(", ")}</p></Card>}

          <Card title="Hierarchy"><Tree n={d.hierarchy} current={c.id} /></Card>

          {d.deviations.length > 0 && (
            <Card title="Deviations from standard template">
              <ul className="space-y-2 text-sm">{d.deviations.map((v, i) => (
                <li key={i} className="flex gap-2"><SeverityChip sev={v.severity} /><span><b>{v.heading}.</b> {v.deviation_summary}</span></li>))}</ul>
            </Card>
          )}
        </div>

        <Card title="Document" className="lg:col-span-3">
          <div className="max-h-[75vh] space-y-3 overflow-y-auto pr-2 text-sm leading-relaxed">
            {d.clauses.map((cl, i) => {
              const newPage = cl.page !== lastPage; lastPage = cl.page;
              return (
                <div key={cl.id}>
                  {newPage && <div className="my-2 border-b border-dashed border-slate-300 text-[11px] uppercase tracking-wider text-slate-400 dark:border-slate-600">Page {cl.page}</div>}
                  <div ref={(el) => { refs.current[cl.id] = el; }} onClick={() => setHl(cl.id)}
                    className={`rounded p-2 transition ${hl === cl.id ? "bg-yellow-100 ring-2 ring-yellow-400 dark:bg-yellow-900/40" : ""}`}>
                    <div className="font-semibold">{i + 1}. {cl.heading}</div><p>{cl.text}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      </div>
    </div>
  );
}
