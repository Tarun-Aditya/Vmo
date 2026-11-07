import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Btn, inputCls } from "../forms";
import { api, ago } from "../lib";
import { Card } from "../ui";

type Link = { id: number; prefix: string; level: string; label: string | null; expires_at: string | null; created_by: string; revoked: boolean; uses: number; last_used_at: string | null };

/** Create view / comment / edit links for one draft (optionally expiring) and revoke them. The link is shown once. */
export default function ShareDialog({ docId }: { docId: string }) {
  const qc = useQueryClient();
  const [level, setLevel] = useState("comment");
  const [days, setDays] = useState(14);
  const [label, setLabel] = useState("");
  const [fresh, setFresh] = useState<string | null>(null);
  const q = useQuery({ queryKey: ["shares", docId], queryFn: () => api<Link[]>(`/api/documents/${docId}/share`) });
  const refresh = () => qc.invalidateQueries({ queryKey: ["shares", docId] });
  const make = useMutation({ mutationFn: () => api<{ path: string }>(`/api/documents/${docId}/share`, { method: "POST", body: JSON.stringify({ level, expires_days: days || null, label: label || null }) }), onSuccess: (r) => { setFresh(window.location.origin + r.path); setLabel(""); refresh(); } });
  const revoke = useMutation({ mutationFn: (id: number) => api(`/api/documents/${docId}/share/${id}`, { method: "DELETE" }), onSuccess: refresh });
  return (
    <Card title="Share this draft">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <select className={`${inputCls} w-36`} aria-label="Link access" value={level} onChange={(e) => setLevel(e.target.value)}><option value="view">Can view</option><option value="comment">Can comment</option><option value="edit">Can edit</option></select>
        <label className="flex items-center gap-1 text-xs text-slate-500">expires in <input className={`${inputCls} w-16`} type="number" min={0} aria-label="Expires in days" value={days} onChange={(e) => setDays(Number(e.target.value))} /> days</label>
        <input className={`${inputCls} w-40`} aria-label="Link label" placeholder="Label (e.g. Vendor legal)" value={label} onChange={(e) => setLabel(e.target.value)} />
        <Btn onClick={() => make.mutate()} disabled={make.isPending}>Create link</Btn>
      </div>
      {fresh && <p role="status" className="mt-2 break-all rounded border border-emerald-500 bg-emerald-50 p-2 font-mono text-xs text-emerald-900">Copy it now, it is not shown again: <a className="underline" href={fresh}>{fresh}</a></p>}
      <ul className="mt-2 space-y-0.5 text-xs">
        {(q.data ?? []).map((l) => <li key={l.id} className={l.revoked ? "text-slate-400 line-through" : ""}><code>{l.prefix}…</code> · {l.level}{l.label ? ` · ${l.label}` : ""} · {l.expires_at ? `expires ${ago(l.expires_at)}` : "no expiry"} · {l.uses} open{l.uses !== 1 ? "s" : ""}
          {!l.revoked && <button className="ml-2 text-red-600 hover:underline" onClick={() => revoke.mutate(l.id)}>Revoke</button>}</li>)}
        {q.data?.length === 0 && <li className="text-slate-500">No links yet.</li>}
      </ul>
    </Card>
  );
}
