import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Btn, inputCls } from "../forms";
import { api, when } from "../lib";
import { Card } from "../ui";

type Step = { id: number; seq: number; label: string; approvers: string[]; status: "waiting" | "pending" | "approved" | "rejected"; decided_by: string | null; decided_at: string | null; comment: string | null };
type Ap = { id: number; status: string; rule_name: string; steps: Step[] };
const ICON = { waiting: "○", pending: "◐", approved: "✓", rejected: "✗" } as const;

/** The approval chain a rule picked for this draft: who has approved, who is next, decide your step. */
export default function ApprovalPanel({ docId }: { docId: string }) {
  const qc = useQueryClient();
  const [comment, setComment] = useState("");
  const q = useQuery({ queryKey: ["approval", docId], queryFn: () => api<{ approval: Ap | null; matching_rule: { name: string } | null }>(`/api/documents/${docId}/approval`) });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["approval", docId] }); qc.invalidateQueries({ queryKey: ["redline"] }); qc.invalidateQueries({ queryKey: ["redline-docs"] }); };
  const start = useMutation({ mutationFn: () => api(`/api/documents/${docId}/approval/start`, { method: "POST" }), onSuccess: refresh });
  const decide = useMutation({ mutationFn: (v: { sid: number; decision: string }) => api(`/api/approvals/${q.data!.approval!.id}/steps/${v.sid}/decide`, { method: "POST", body: JSON.stringify({ decision: v.decision, comment: comment || null }) }), onSuccess: () => { setComment(""); refresh(); } });
  if (!q.data) return null;
  const a = q.data.approval, active = a?.status === "pending";
  const err = start.error ?? decide.error;
  return (
    <Card title={a ? `Approval — ${a.rule_name} · ${a.status}` : "Approval"}>
      {!a || !active && a.status === "cancelled" ? (
        q.data.matching_rule ? <div className="flex items-center gap-3 text-sm"><span>Rule “{q.data.matching_rule.name}” applies.</span><Btn onClick={() => start.mutate()} disabled={start.isPending}>Request approval</Btn></div>
          : <p className="text-sm text-slate-500">No approval rule applies to this document. Add one in Admin → Approval rules.</p>
      ) : (
        <ol className="space-y-1 text-sm">
          {a.steps.map((s) => (
            <li key={s.id} className="flex flex-wrap items-center gap-2"><b className={s.status === "approved" ? "text-emerald-600" : s.status === "rejected" ? "text-red-600" : "text-slate-500"}>{ICON[s.status]}</b>
              <span className="font-medium">{s.seq}. {s.label}</span><span className="text-xs text-slate-500">{s.approvers.join(", ")}</span>
              {s.decided_by && <span className="text-xs text-slate-500">· {s.decided_by} {when(s.decided_at)}{s.comment ? ` — “${s.comment}”` : ""}</span>}
              {s.status === "pending" && active && (<span className="ml-auto flex items-center gap-1"><input className={`${inputCls} w-40`} aria-label="Decision comment" placeholder="Comment" value={comment} onChange={(e) => setComment(e.target.value)} />
                <Btn onClick={() => decide.mutate({ sid: s.id, decision: "approve" })}>Approve</Btn><Btn kind="danger" onClick={() => decide.mutate({ sid: s.id, decision: "reject" })}>Reject</Btn></span>)}
            </li>))}
        </ol>)}
      {err && <p role="alert" className="mt-1 text-sm text-red-600">{String(err).replace("Error: ", "")}</p>}
    </Card>
  );
}
