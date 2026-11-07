import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Btn, inputCls } from "../forms";
import { api, when } from "../lib";
import { Card } from "../ui";

type Signer = { id: number; seq: number; name: string; email: string; role: string; status: string; signed_at: string | null };
type Req = { id: number; status: string; provider: string; external_id: string | null; sequential: boolean; executed_contract_id: number | null; signers: Signer[] };
type Made = Req & { links: { email: string; path: string }[] };
const blank = () => ({ name: "", email: "", role: "customer" });

/** Send the draft for signature, watch each signer, hand out personal links, and mark the signed draft as an executed contract. */
export default function SignaturePanel({ docId }: { docId: string }) {
  const qc = useQueryClient();
  const [signers, setSigners] = useState([blank(), { ...blank(), role: "supplier" }]);
  const [provider, setProvider] = useState("internal");
  const [links, setLinks] = useState<Made["links"]>([]);
  const q = useQuery({ queryKey: ["signatures", docId], queryFn: () => api<Req[]>(`/api/documents/${docId}/signatures`), refetchInterval: 8000 });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["signatures", docId] }); qc.invalidateQueries(); };
  const send = useMutation({ mutationFn: () => api<Made>(`/api/documents/${docId}/signatures`, { method: "POST", body: JSON.stringify({ signers, provider, sequential: true }) }), onSuccess: (r) => { setLinks(r.links); refresh(); } });
  const sync = useMutation({ mutationFn: (id: number) => api(`/api/signatures/${id}/sync`, { method: "POST" }), onSuccess: refresh });
  const cancel = useMutation({ mutationFn: (id: number) => api(`/api/signatures/${id}`, { method: "DELETE" }), onSuccess: () => { setLinks([]); refresh(); } });
  const execute = useMutation({ mutationFn: () => api<{ executed_contract_id: number }>(`/api/documents/${docId}/execute`, { method: "POST" }), onSuccess: (r) => { window.location.href = `/contracts/${r.executed_contract_id}`; } });
  const last = q.data?.[0];
  const active = last?.status === "pending";
  return (
    <Card title={last ? `Signatures — ${last.status}` : "Signatures"}>
      {last ? (
        <div className="space-y-2 text-sm">
          <ol className="space-y-0.5">{last.signers.map((s) => <li key={s.id}><b className={s.status === "signed" ? "text-emerald-600" : s.status === "declined" ? "text-red-600" : "text-slate-500"}>{s.status === "signed" ? "✓" : s.status === "declined" ? "✗" : "○"}</b> {s.seq}. {s.name} <span className="text-xs text-slate-500">({s.role}) {s.email}{s.signed_at ? ` · signed ${when(s.signed_at)}` : ""}</span></li>)}</ol>
          {links.length > 0 && <div role="status" className="rounded border border-emerald-500 bg-emerald-50 p-2 text-xs text-emerald-900">Personal signing links, shown once: {links.map((l) => <div key={l.path} className="break-all">{l.email}: <a className="underline" href={window.location.origin + l.path}>{window.location.origin + l.path}</a></div>)}</div>}
          <div className="flex flex-wrap gap-2">
            {active && last.provider === "docusign" && <Btn kind="ghost" onClick={() => sync.mutate(last.id)}>Check DocuSign status</Btn>}
            {active && <Btn kind="danger" onClick={() => cancel.mutate(last.id)}>Cancel request</Btn>}
            {last.status === "completed" && <a className="text-indigo-600 hover:underline" href={`/api/signatures/${last.id}/certificate`} target="_blank" rel="noreferrer">Completion certificate</a>}
            {last.status === "completed" && !last.executed_contract_id && <Btn onClick={() => execute.mutate()} disabled={execute.isPending}>Mark executed</Btn>}
            {last.executed_contract_id && <Link className="text-indigo-600 hover:underline" to={`/contracts/${last.executed_contract_id}`}>Open executed contract</Link>}
          </div>
        </div>) : null}
      {!active && (
        <div className={last ? "mt-3 space-y-1 border-t border-slate-200 pt-3 dark:border-slate-700" : "space-y-1"}>
          {signers.map((s, i) => (
            <div key={i} className="flex flex-wrap gap-1">
              <input className={`${inputCls} w-32`} aria-label={`Signer ${i + 1} name`} placeholder="Name" value={s.name} onChange={(e) => setSigners(signers.map((x, j) => j === i ? { ...x, name: e.target.value } : x))} />
              <input className={`${inputCls} w-44`} aria-label={`Signer ${i + 1} e-mail`} placeholder="E-mail" value={s.email} onChange={(e) => setSigners(signers.map((x, j) => j === i ? { ...x, email: e.target.value } : x))} />
              <select className={`${inputCls} w-28`} aria-label={`Signer ${i + 1} role`} value={s.role} onChange={(e) => setSigners(signers.map((x, j) => j === i ? { ...x, role: e.target.value } : x))}><option value="customer">Customer</option><option value="supplier">Supplier</option><option value="other">Other</option></select>
            </div>))}
          <div className="flex items-center gap-2"><button className="text-xs text-indigo-600 hover:underline" onClick={() => setSigners([...signers, blank()])}>+ signer</button>
            <select className={`${inputCls} w-40`} aria-label="Signature provider" value={provider} onChange={(e) => setProvider(e.target.value)}><option value="internal">ContractIQ (click to sign)</option><option value="docusign">DocuSign</option></select>
            <Btn onClick={() => send.mutate()} disabled={send.isPending || signers.some((s) => !s.name.trim() || !s.email.includes("@"))}>Send for signature</Btn></div>
          {send.error && <p role="alert" className="text-sm text-red-600">{String(send.error).replace("Error: ", "")}</p>}
        </div>)}
    </Card>
  );
}
