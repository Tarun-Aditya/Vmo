import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, fmtDate, usd } from "../lib";
import { Card, ConfidenceBadge, Loading, Sev, SeverityChip, Td, Th } from "../ui";

type Node = { id: number; title: string; type: string; children: Node[] };
type Detail = {
  contract: { id: number; title: string; vendor: string; category: string; type: string; owner: string; status: string; property?: string | null };
  clauses: { id: number; clause_type: string; heading: string; text: string; page: number }[];
  fields: { field: string; value: string | null; confidence: number | null; source_clause_id: number | null; source_page: number | null; source_heading: string | null; corrected?: boolean; editable?: boolean }[];
  effective_terms: { field: string; value: unknown; source_id: number; source_title: string; overridden: boolean }[];
  hierarchy: Node; deviations: { severity: Sev; deviation_summary: string; heading: string }[];
  is_amendment: boolean; overrides: string[]; parent: { id: number; title: string } | null;
  lineage: { id: number; title: string; type: string }[];
  inherited_terms: { label: string; value: unknown; source_id: number; source_title: string }[];
  values: { metric_key: string; name: string; unit: string | null; kind: string; value_num: number | null; value_text: string | null; page: number | null }[];
  checks: { rule_key: string; name: string; status: "pass" | "fail" | "na"; severity: Sev; actual: string | null; expected: string | null; page: number | null; excerpt: string | null; suggested_text: string | null }[];
  signatures: { customer_signatory: string | null; customer_signed_date: string | null; supplier_signatory: string | null; supplier_signed_date: string | null; fully_executed: boolean };
};

const LABEL: Record<string, string> = {
  effective_date: "Effective date", expiry_date: "Expiry date", notice_period_days: "Notice period (days)", auto_renew: "Auto-renew",
  annual_value: "Annual value", total_value: "Total value", payment_terms_days: "Payment terms (days)", liability_cap_multiple: "Liability cap (× annual fees)",
  liability_cap_text: "Liability cap", termination_for_convenience: "Termination for convenience", governing_law: "Governing law",
  processes_personal_data: "Processes personal data", has_dpa: "Has DPA",
  customer_signatory: "Customer signatory", supplier_signatory: "Supplier signatory", customer_signed_date: "Customer signed", supplier_signed_date: "Supplier signed", fully_executed: "Fully signed",
};
function show(field: string, v: unknown, inherits = false): string {
  if (inherits && (v === null || v === undefined || v === "null") && ["liability_cap_multiple", "governing_law"].includes(field)) return "Inherited from MSA";
  if (v === null || v === undefined || v === "null") return field === "liability_cap_multiple" ? "Uncapped / n.a." : "—";
  if (field.endsWith("_date")) return fmtDate(String(v));
  if (field.endsWith("_value")) return usd(v as number);
  if (typeof v === "boolean" || v === "True" || v === "False") return String(v) === "true" || v === "True" ? "Yes" : "No";
  return String(v);
}

/** Clause text keeps the Markdown bold of the source (**defined term**): show it as bold instead of asterisks. */
function inline(t: string) {
  return t.split(/(\*\*[^*]+\*\*)/g).map((x, i) => (x.startsWith("**") && x.endsWith("**") && x.length > 4 ? <b key={i}>{x.slice(2, -2)}</b> : x.replace(/\*\*/g, "")));
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
  const meta = useQuery({ queryKey: ["meta"], queryFn: () => api<{ customer?: string }>("/api/meta") });
  const [hl, setHl] = useState<number | null>(null);
  const qc = useQueryClient();
  const [fix, setFix] = useState<{ field: string; value: string } | null>(null);
  const saveFix = useMutation({ mutationFn: () => api(`/api/contracts/${id}/fields/${fix!.field}`, { method: "PUT", body: JSON.stringify({ value: fix!.value }) }), onSuccess: () => { setFix(null); qc.invalidateQueries(); } });
  const refs = useRef<Record<number, HTMLDivElement | null>>({});
  useEffect(() => { setHl(null); }, [id]);
  useEffect(() => { if (hl) refs.current[hl]?.scrollIntoView({ behavior: "smooth", block: "center" }); }, [hl]);
  if (!q.data) return <Loading q={q} />;
  const d = q.data, c = d.contract;
  let lastPage = 0;
  return (
    <div className="space-y-4">
      <div>
        <Link to="/contracts" className="text-sm text-ink-mute hover:underline">← Contracts</Link>
        <h1 className="mt-1 max-w-4xl text-3xl leading-tight md:text-4xl">{c.title}</h1>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          {c.status === "draft" && <SeverityChip sev="medium" label="Draft" />}
          {c.status !== "draft" && (d.signatures.fully_executed ? <span className="inline-flex items-center gap-1 rounded-full bg-indigo-100 px-2.5 py-0.5 text-xs font-semibold text-indigo-900">✓ Fully executed</span> : <SeverityChip sev="high" label="Not fully signed" />)}
          {d.checks.some((x) => x.rule_key === "no_unlimited_liability" && x.status === "fail") && <SeverityChip sev="critical" label="Uncapped liability" />}
          {d.deviations.filter((v) => v.severity === "critical" || v.severity === "high").length > 0 && <SeverityChip sev="high" label={`${d.deviations.filter((v) => v.severity === "critical" || v.severity === "high").length} serious deviations`} />}
          <span className="text-sm text-ink-mute dark:text-slate-400">{c.vendor} · {c.type} · {c.category}{c.property ? ` · ${c.property}` : ""} · owner {c.owner}{d.parent && <> · under <Link className="text-indigo-600 hover:underline" to={`/contracts/${d.parent.id}`}>{d.parent.title}</Link></>}</span>
        </div>
        <nav aria-label="Contract sections" className="mt-4 flex flex-wrap gap-x-6 gap-y-1 border-b border-line text-sm font-semibold dark:border-slate-700">
          {[["#document", "Document and fields"], ["#hierarchy", "Hierarchy and effective terms"], ["#checks", "Checklist and deviations"]].map(([h, t]) => <a key={h} href={h} className="border-b-[3px] border-transparent py-2.5 text-ink-mute hover:border-indigo-600 hover:text-ink dark:text-slate-300">{t}</a>)}
          <Link className="border-b-[3px] border-transparent py-2.5 text-ink-mute hover:border-indigo-600 hover:text-ink dark:text-slate-300" to={`/ask?doc=${c.id}`}>Ask about this document</Link>
          <Link className="border-b-[3px] border-transparent py-2.5 text-ink-mute hover:border-indigo-600 hover:text-ink dark:text-slate-300" to={`/redline/${c.id}`}>{c.status === "draft" ? "Review and redline" : "Review and checklist"}</Link>
        </nav>
      </div>
      <div className="grid gap-5 lg:grid-cols-5">
        <div className="space-y-5 lg:order-2 lg:col-span-2">
          {d.lineage.length > 0 && !d.is_amendment && (
            <Card title={d.inherited_terms.length ? "Built on top of its parent agreements" : "Parent agreements"}>
              <ol className="mb-2 space-y-1 text-sm">
                {d.lineage.map((l, i) => (
                  <li key={l.id} style={{ paddingLeft: i * 14 }}>
                    <span className="mr-1 text-slate-400">{i === 0 ? "" : "↳"}</span>
                    <span className="mr-1 rounded bg-slate-200 px-1 text-[10px] font-semibold uppercase dark:bg-slate-700">{l.type}</span>
                    <Link className="text-indigo-600 hover:underline dark:text-indigo-400" to={`/contracts/${l.id}`}>{l.title}</Link>
                  </li>
                ))}
                <li style={{ paddingLeft: d.lineage.length * 14 }}><span className="mr-1 text-slate-400">↳</span><b>{c.title}</b> <span className="text-xs text-slate-500">(this document)</span></li>
              </ol>
              {d.inherited_terms.length > 0 && (
                <table className="w-full text-sm"><thead><tr><Th>Inherited term</Th><Th>Value</Th><Th>From</Th></tr></thead><tbody>
                  {d.inherited_terms.map((t) => (
                    <tr key={t.label} className="border-t border-slate-100 dark:border-slate-700"><Td className="text-slate-500">{t.label}</Td>
                      <Td className="font-medium">{typeof t.value === "boolean" ? (t.value ? "Yes" : "No") : t.value === null ? "Uncapped / n.a." : String(t.value)}</Td>
                      <Td className="text-xs"><Link className="text-indigo-600 hover:underline" to={`/contracts/${t.source_id}`}>{t.source_title}</Link></Td></tr>))}
                </tbody></table>
              )}
              <p className="mt-2 text-xs text-slate-500">The MSA prevails in a conflict (order of precedence); liability, indemnity, IP, confidentiality, data protection, audit and governing law flow down.</p>
            </Card>
          )}

          {d.values.length > 0 && (
            <Card title="Terms & limits (extracted values)">
              <table className="w-full text-sm"><tbody>
                {d.values.map((v) => (
                  <tr key={v.metric_key} className="border-t border-slate-100 dark:border-slate-700">
                    <Td className="text-slate-500">{v.name}</Td>
                    <Td className="font-medium tabular-nums">{v.value_text ?? (v.unit === "USD" ? usd(v.value_num) : Number(v.value_num).toLocaleString("en-US", { maximumFractionDigits: 2 }))}{v.unit && v.unit !== "USD" && v.value_text === null ? <span className="ml-1 text-xs font-normal text-slate-500">{v.unit}</span> : null}</Td>
                    <Td className="text-right text-[11px] text-slate-500">{v.page ? `p.${v.page}` : ""}</Td>
                  </tr>))}
              </tbody></table>
            </Card>
          )}

          {d.checks.length > 0 && (
            <Card className="scroll-mt-20" title={<><span id="checks" />{`Checklist — ${d.checks.filter((x) => x.status === "pass").length} pass · ${d.checks.filter((x) => x.status === "fail").length} fail`}</>} right={<Link className="text-xs text-indigo-600 hover:underline" to={`/redline/${c.id}`}>Open in Redline</Link>}>
              <ul className="space-y-1 text-sm">
                {d.checks.filter((x) => x.status !== "na").map((x) => (
                  <li key={x.rule_key} className="flex items-start gap-2">
                    <b className={x.status === "pass" ? "text-emerald-600" : "text-red-600"}>{x.status === "pass" ? "✓" : "✗"}</b>
                    <span className="flex-1"><span className={x.status === "fail" ? "font-medium" : "text-slate-600 dark:text-slate-300"}>{x.name}</span>{x.actual && <span className="ml-1 text-xs text-slate-500">({x.actual})</span>}</span>
                    {x.status === "fail" && <SeverityChip sev={x.severity} />}
                  </li>))}
              </ul>
            </Card>
          )}

          <Card title="Signatures" right={d.signatures.fully_executed ? <span className="font-bold text-emerald-600">✓ fully signed</span> : <span className="font-bold text-red-600">✗ not fully signed</span>}>
            <table className="w-full text-sm"><tbody>
              {([[`${meta.data?.customer ?? "Customer"} (customer)`, d.signatures.customer_signatory, d.signatures.customer_signed_date], [c.vendor, d.signatures.supplier_signatory, d.signatures.supplier_signed_date]] as [string, string | null, string | null][]).map(([party, who, when]) => (
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
                  <Td className="font-medium tabular-nums">{fix?.field === f.field ? (
                      <span className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                        <input className="w-36 rounded border border-slate-300 px-1 py-0.5 text-sm dark:border-slate-600 dark:bg-slate-800" aria-label={`Correct ${LABEL[f.field] ?? f.field}`} autoFocus value={fix.value} onChange={(e) => setFix({ ...fix, value: e.target.value })} onKeyDown={(e) => e.key === "Enter" && saveFix.mutate()} />
                        <button className="text-xs font-medium text-emerald-700" onClick={() => saveFix.mutate()}>Save</button><button className="text-xs text-slate-500" onClick={() => setFix(null)}>Cancel</button>
                        {saveFix.error && <span className="text-xs text-red-600">{String(saveFix.error).replace("Error: ", "")}</span>}</span>)
                    : <>{show(f.field, f.value, d.lineage.length > 0 && ["SOW", "Work Order"].includes(c.type))}
                        {f.corrected && <span className="ml-1 rounded bg-emerald-100 px-1 text-[10px] font-semibold text-emerald-900" title="A person corrected this value">corrected</span>}
                        {f.editable && <button className="ml-2 text-xs font-normal text-indigo-600 hover:underline dark:text-indigo-400" aria-label={`Edit ${LABEL[f.field] ?? f.field}`} onClick={(e) => { e.stopPropagation(); setFix({ field: f.field, value: f.value ?? "" }); }}>edit</button>}</>}</Td>
                  <Td className="text-right"><span className="mr-1 inline-block h-1.5 w-10 overflow-hidden rounded bg-slate-200 align-middle dark:bg-slate-700" aria-hidden><i className="block h-full bg-indigo-600" style={{ width: `${Math.round(Number(f.confidence ?? 0) * 100)}%` }} /></span><ConfidenceBadge v={f.confidence} />
                    <div className="text-[11px] text-slate-500">{f.source_heading ? `${f.source_heading} · p.${f.source_page}` : `header · p.${f.source_page ?? 1}`}</div></Td>
                </tr>
              ))}
            </tbody></table>
          </Card>

          {!d.is_amendment && d.effective_terms.length > 0 && (
            <Card title="Effective terms (after amendments)">
              <table className="w-full text-sm">
                <thead><tr><Th>Term</Th><Th>Current value</Th><Th>Set by</Th></tr></thead>
                <tbody>
                  {d.effective_terms.filter((e) => e.field !== "liability_cap_text").map((e) => (
                    <tr key={e.field} className={`border-t border-slate-100 dark:border-slate-700 ${e.overridden ? "bg-indigo-50 dark:bg-indigo-950/40" : ""}`}>
                      <Td className="text-slate-500">{LABEL[e.field]}</Td>
                      <Td className="font-medium tabular-nums">{show(e.field, e.value, d.lineage.length > 0 && ["SOW", "Work Order"].includes(c.type))}</Td>
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

          <Card title="Hierarchy" className="scroll-mt-20"><span id="hierarchy" /><Tree n={d.hierarchy} current={c.id} /></Card>

          {d.deviations.length > 0 && (
            <Card title="Deviations from standard template">
              <ul className="space-y-2 text-sm">{d.deviations.map((v, i) => (
                <li key={i} className="flex gap-2"><SeverityChip sev={v.severity} /><span><b>{v.heading}.</b> {v.deviation_summary}</span></li>))}</ul>
            </Card>
          )}
        </div>

        <Card title="Document" className="scroll-mt-20 lg:order-1 lg:col-span-3"><span id="document" />
          <div className="max-h-[80vh] space-y-3 overflow-y-auto pr-3 font-serif text-[16px] leading-7">
            {d.clauses.map((cl, i) => {
              const newPage = cl.page !== lastPage; lastPage = cl.page;
              return (
                <div key={cl.id}>
                  {newPage && <div className="my-2 border-b border-dashed border-slate-300 text-[11px] uppercase tracking-wider text-slate-400 dark:border-slate-600">Page {cl.page}</div>}
                  <div ref={(el) => { refs.current[cl.id] = el; }} onClick={() => setHl(cl.id)}
                    className={`rounded-md p-2 transition ${hl === cl.id ? "border-b-2 border-amber-600 bg-amber-100 dark:bg-amber-900/40" : ""}`}>
                    <div className="font-sans text-xs font-semibold uppercase tracking-wider text-ink-mute dark:text-slate-400">{i + 1} · {cl.heading}</div><p className="mt-1">{inline(cl.text)}</p>
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
