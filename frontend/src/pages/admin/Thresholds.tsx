import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Btn, inputCls } from "../../forms";
import { api } from "../../lib";
import { Card, Loading } from "../../ui";

type Item = { grp: string; key: string; label: string; description: string | null; value: number | number[][]; kind: string };
type Res = { groups: Record<string, Item[]>; titles: Record<string, string> };

function Row({ it }: { it: Item }) {
  const qc = useQueryClient();
  const [v, setV] = useState(it.kind === "json" ? JSON.stringify(it.value) : String(it.value));
  const [err, setErr] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () => api(`/api/admin/config/${it.grp}/${it.key}`, { method: "PUT", body: JSON.stringify({ value: it.kind === "json" ? JSON.parse(v) : Number(v) }) }),
    onSuccess: () => { setErr(null); qc.invalidateQueries(); }, onError: (e) => setErr(String(e)),
  });
  const dirty = v !== (it.kind === "json" ? JSON.stringify(it.value) : String(it.value));
  return (
    <tr className="border-t border-slate-100 align-top dark:border-slate-700">
      <td className="py-2 pr-4"><div className="font-medium">{it.label}</div>{it.description && <div className="text-xs text-slate-500">{it.description}</div>}</td>
      <td className="w-56 py-2"><input className={`${inputCls} ${it.kind === "json" ? "font-mono text-xs" : "w-28"}`} aria-label={it.label} value={v} onChange={(e) => setV(e.target.value)} /></td>
      <td className="w-32 py-2 pl-2">{dirty && <Btn onClick={() => save.mutate()} disabled={save.isPending}>{save.isPending ? "…" : "Save"}</Btn>}{err && <div className="text-xs text-red-600">{err}</div>}</td>
    </tr>
  );
}

export default function Thresholds() {
  const q = useQuery({ queryKey: ["config"], queryFn: () => api<Res>("/api/admin/config") });
  if (!q.data) return <Loading q={q} />;
  return (
    <div className="space-y-4">
      <p className="max-w-3xl text-sm text-slate-500">Every threshold the VMO screens use is set here — what counts as an over-billed invoice, how late is late, how many points each finding adds to a vendor's risk score, the tiers, and the estimated service-credit tiers. A change recomputes spend exceptions and vendor scores straight away.</p>
      {Object.entries(q.data.groups).map(([g, items]) => (
        <Card key={g} title={q.data!.titles[g] ?? g}>
          <table className="w-full text-sm" aria-label={q.data!.titles[g] ?? g}><tbody>{items.map((it) => <Row key={`${it.grp}.${it.key}`} it={it} />)}</tbody></table>
        </Card>))}
    </div>
  );
}
