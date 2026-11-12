import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router-dom";
import DocEditor from "../components/DocEditor";
import { Btn, Field, inputCls } from "../forms";
import { api } from "../lib";

type S = { title: string; md: string; signer: { name: string; email: string; status: string; role: string }; request_status: string; my_turn: boolean; doc_hash: string; others: { name: string; status: string }[] };

/** A signer's personal page: read the exact document, type your name, agree. No account. */
export default function Sign() {
  const { token } = useParams();
  const [name, setName] = useState("");
  const [agree, setAgree] = useState(false);
  const q = useQuery({ queryKey: ["sign", token], queryFn: () => api<S>(`/api/sign/${token}`), retry: false });
  const sign = useMutation({ mutationFn: () => api(`/api/sign/${token}`, { method: "POST", body: JSON.stringify({ typed_name: name, agree }) }), onSuccess: () => q.refetch() });
  const decline = useMutation({ mutationFn: () => api(`/api/sign/${token}/decline?reason=declined`, { method: "POST" }), onSuccess: () => q.refetch() });
  if (q.isError) return <div className="mx-auto mt-20 max-w-md rounded border border-amber-400 bg-amber-50 p-4 text-sm text-amber-900" role="alert"><b>This signing link is not valid.</b></div>;
  if (!q.data) return <div className="p-8 text-sm text-slate-500">Loading…</div>;
  const d = q.data;
  return (
    <div className="mx-auto max-w-6xl space-y-3 p-4">
      <h1>{d.title}</h1>
      <p className="text-sm text-slate-500">For signature by {d.signer.name} ({d.signer.email}) · document fingerprint {d.doc_hash.slice(0, 12)}…</p>
      <DocEditor value={d.md} onChange={() => undefined} readOnly title={d.title} status="Read only" height="60vh" />
      <div className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800">
        {d.signer.status === "signed" ? <p className="text-emerald-700" role="status">✓ You signed this document. {d.request_status === "completed" ? "Everyone has signed." : "We will tell you when everyone has signed."}</p>
          : d.signer.status === "declined" || d.request_status !== "pending" ? <p role="status">This request is {d.request_status}.</p>
          : !d.my_turn ? <p role="status">Waiting for an earlier signer ({d.others.filter((o) => o.status !== "signed").map((o) => o.name).join(", ")}). Come back to this link later.</p>
          : (<div className="space-y-2 md:max-w-md">
              <Field label="Type your full name to sign"><input className={inputCls} aria-label="Full name" value={name} onChange={(e) => setName(e.target.value)} /></Field>
              <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} aria-label="I agree" /><span>I have read this document and agree to be bound by it. My typed name is my electronic signature.</span></label>
              <div className="flex gap-2"><Btn onClick={() => sign.mutate()} disabled={!agree || name.trim().length < 2 || sign.isPending}>Sign</Btn><Btn kind="ghost" onClick={() => decline.mutate()}>Decline</Btn></div>
              {sign.error && <p role="alert" className="text-sm text-red-600">{String(sign.error).replace("Error: ", "")}</p>}
            </div>)}
      </div>
    </div>
  );
}
