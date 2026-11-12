import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Btn } from "../forms";
import { api, ago } from "../lib";
import { Card, Loading, SeverityChip, Sev } from "../ui";

export type AlertRow = { id: number; rule_key: string; title: string; body: string | null; severity: Sev; link: string | null; contract_id: number | null; vendor: string | null; status: "open" | "acknowledged" | "resolved"; created_at: string; read_at: string | null; acknowledged_by: string | null; delivered: Record<string, { ok: boolean }> };

export default function Alerts() {
  const qc = useQueryClient();
  const [status, setStatus] = useState<"open" | "acknowledged" | "resolved">("open");
  const q = useQuery({ queryKey: ["alerts", status], queryFn: () => api<{ items: AlertRow[]; unread: number }>(`/api/alerts?status=${status}&limit=300`) });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["alerts"] }); qc.invalidateQueries({ queryKey: ["alerts-summary"] }); };
  const set = useMutation({ mutationFn: (v: { id: number; status: string }) => api(`/api/alerts/${v.id}`, { method: "PUT", body: JSON.stringify({ status: v.status, by: "you" }) }), onSuccess: refresh });
  const readAll = useMutation({ mutationFn: () => api("/api/alerts/read-all", { method: "POST" }), onSuccess: refresh });
  const run = useMutation({ mutationFn: () => api<{ new: number }>("/api/alerts/evaluate", { method: "POST" }), onSuccess: refresh });
  if (!q.data) return <Loading q={q} />;
  const items = q.data.items;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">Alerts</h1>
          <p className="text-sm text-slate-500">Raised once per event from the live data: renewal notices, expiries, overdue duties, SLA breaches, spend exceptions, vendor risk. Rules and channels are in <Link className="text-indigo-600 hover:underline dark:text-indigo-400" to="/admin/alerts">Admin → Alerts</Link>.</p>
        </div>
        <div className="flex gap-2">
          <Btn kind="ghost" onClick={() => run.mutate()} disabled={run.isPending}>{run.isPending ? "Checking…" : run.data ? `Checked · ${run.data.new} new` : "Check now"}</Btn>
          <Btn kind="ghost" onClick={() => readAll.mutate()}>Mark all read</Btn>
        </div>
      </div>
      <div className="flex gap-1" role="tablist" aria-label="Alert status">
        {(["open", "acknowledged", "resolved"] as const).map((s) => (
          <button key={s} role="tab" aria-selected={status === s} onClick={() => setStatus(s)} className={`rounded px-3 py-1 text-sm capitalize ${status === s ? "bg-indigo-600 text-white" : "bg-slate-100 dark:bg-slate-800"}`}>{s}</button>))}
      </div>
      <Card>
        {items.length === 0 && <p className="text-sm text-slate-500">Nothing here.</p>}
        <ul className="divide-y divide-slate-200 dark:divide-slate-700">
          {items.map((a) => (
            <li key={a.id} className={`flex flex-wrap items-start gap-3 py-3 ${!a.read_at && a.status === "open" ? "font-medium" : ""}`}>
              <SeverityChip sev={a.severity} />
              <div className="min-w-0 flex-1">
                <div className="text-sm">{a.link ? <Link className="hover:underline" to={a.link}>{a.title}</Link> : a.title}</div>
                {a.body && <div className="text-xs font-normal text-slate-500">{a.body}</div>}
                <div className="mt-0.5 text-xs font-normal text-slate-500">{ago(a.created_at)}{a.acknowledged_by && ` · by ${a.acknowledged_by}`}{Object.keys(a.delivered).length > 0 && ` · sent to ${Object.entries(a.delivered).map(([n, d]) => `${n}${d.ok ? " ✓" : " ✗"}`).join(", ")}`}</div>
              </div>
              <div className="flex gap-1">
                {a.status === "open" && <Btn kind="ghost" onClick={() => set.mutate({ id: a.id, status: "acknowledged" })}>Acknowledge</Btn>}
                {a.status !== "resolved" && <Btn kind="ghost" onClick={() => set.mutate({ id: a.id, status: "resolved" })}>Resolve</Btn>}
                {a.status !== "open" && <Btn kind="ghost" onClick={() => set.mutate({ id: a.id, status: "open" })}>Reopen</Btn>}
              </div>
            </li>))}
        </ul>
      </Card>
    </div>
  );
}
