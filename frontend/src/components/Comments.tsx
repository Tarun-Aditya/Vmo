import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Btn, inputCls } from "../forms";
import { api, when } from "../lib";
import { Card } from "../ui";

export type Cm = { id: number; author: string; body: string; created_at: string };
export type Th = { id: number; status: "open" | "resolved"; source: "user" | "ai" | "guest"; severity: string | null; anchor_text: string | null; clause_type: string | null; created_by: string; assignee: string | null; due_date: string | null; resolved_by: string | null; comments: Cm[] };
type Api = { list: string; add: string; reply: (id: number) => string; patch?: (id: number) => string; guestName?: string };

/** Word / Google-Docs style comment threads: add on the selected text, reply, assign, resolve, reopen. Used signed-in (editor) and by guests (shared link). */
export default function Comments({ docId, endpoints, canAct = true, onFocus }: { docId: string; endpoints: Api; canAct?: boolean; onFocus?: (t: Th) => void }) {
  const qc = useQueryClient();
  const [show, setShow] = useState<"open" | "resolved" | "all">("open");
  const [body, setBody] = useState("");
  const [assignee, setAssignee] = useState("");
  const [reply, setReply] = useState<Record<number, string>>({});
  const key = ["threads", docId, endpoints.list];
  const q = useQuery({ queryKey: key, queryFn: () => api<{ threads: Th[]; open?: number }>(endpoints.list), refetchInterval: 8000 });
  const refresh = () => qc.invalidateQueries({ queryKey: key });
  const g = endpoints.guestName ? { name: endpoints.guestName } : {};
  const add = useMutation({ mutationFn: () => api(endpoints.add, { method: "POST", body: JSON.stringify({ body, anchor_text: window.getSelection()?.toString().trim().slice(0, 300) || null, assignee: assignee || null, ...g }) }), onSuccess: () => { setBody(""); setAssignee(""); refresh(); } });
  const send = useMutation({ mutationFn: (id: number) => api(endpoints.reply(id), { method: "POST", body: JSON.stringify({ body: reply[id], ...g }) }), onSuccess: (_r, id) => { setReply((r) => ({ ...r, [id]: "" })); refresh(); } });
  const patch = useMutation({ mutationFn: (v: { id: number; status: string }) => api(endpoints.patch!(v.id), { method: "PUT", body: JSON.stringify({ status: v.status }) }), onSuccess: refresh });
  const ai = useMutation({ mutationFn: () => api(`/api/documents/${docId}/threads/from-redline`, { method: "POST" }), onSuccess: refresh });
  const all = q.data?.threads ?? [];
  const list = all.filter((t) => show === "all" || t.status === show);
  const open = all.filter((t) => t.status === "open").length;
  return (
    <Card title={`Comments — ${open} open`} right={endpoints.patch && <button className="text-xs text-indigo-600 hover:underline dark:text-indigo-400" onClick={() => ai.mutate()} title="Open a thread for every playbook deviation found by ContractIQ">+ AI findings</button>}>
      {canAct && (
        <div className="mb-3 space-y-1">
          <textarea className={`${inputCls} h-16`} aria-label="New comment" placeholder="Select text in the document, then comment here. @name notifies someone." value={body} onChange={(e) => setBody(e.target.value)} />
          <div className="flex items-center gap-2">
            {endpoints.patch && <input className={`${inputCls} w-40`} aria-label="Assign to" placeholder="Assign to (e-mail)" value={assignee} onChange={(e) => setAssignee(e.target.value)} />}
            <Btn onClick={() => add.mutate()} disabled={!body.trim() || add.isPending}>Comment</Btn>
          </div>
          {add.error && <p className="text-xs text-red-600">{String(add.error).replace("Error: ", "")}</p>}
        </div>)}
      <div className="mb-2 flex gap-1 text-xs" role="tablist" aria-label="Thread filter">
        {(["open", "resolved", "all"] as const).map((s) => <button key={s} role="tab" aria-selected={show === s} onClick={() => setShow(s)} className={`rounded px-2 py-0.5 capitalize ${show === s ? "bg-indigo-600 text-white" : "bg-slate-100 dark:bg-slate-700"}`}>{s}</button>)}
      </div>
      <ul className="max-h-[60vh] space-y-2 overflow-y-auto overflow-x-hidden">
        {list.length === 0 && <li className="text-sm text-slate-500">No {show === "all" ? "" : show} comments.</li>}
        {list.map((t) => (
          <li key={t.id} data-thread={t.id} className={`min-w-0 break-words rounded border p-2 text-sm ${t.status === "resolved" ? "border-slate-200 opacity-70 dark:border-slate-700" : "border-amber-400"}`}>
            {t.anchor_text && <button className="mb-1 block w-full truncate border-l-4 border-amber-400 bg-amber-50 px-2 text-left text-xs italic dark:bg-slate-900" onClick={() => onFocus?.(t)} title={t.anchor_text}>“{t.anchor_text}”</button>}
            <div className="mb-1 flex flex-wrap items-center gap-1 text-xs text-slate-500">
              {t.source === "ai" && <span className="rounded bg-indigo-100 px-1 font-medium text-indigo-900">ContractIQ{t.severity ? ` · ${t.severity}` : ""}</span>}
              {t.assignee && <span>→ {t.assignee}{t.due_date ? ` · due ${t.due_date}` : ""}</span>}
              {t.status === "resolved" && <span className="font-medium text-emerald-700">✓ resolved by {t.resolved_by}</span>}
            </div>
            {t.comments.map((c) => <div key={c.id} className="mb-1 min-w-0 break-words"><b>{c.author}</b> <span className="text-xs text-slate-500">{when(c.created_at)}</span><p className="whitespace-pre-wrap">{c.body}</p></div>)}
            {canAct && t.status === "open" && (
              <div className="mt-1 flex gap-1"><input className={`${inputCls} min-w-0 flex-1`} aria-label={`Reply to thread ${t.id}`} placeholder="Reply…" value={reply[t.id] ?? ""} onChange={(e) => setReply((r) => ({ ...r, [t.id]: e.target.value }))} onKeyDown={(e) => e.key === "Enter" && reply[t.id]?.trim() && send.mutate(t.id)} />
                <Btn kind="ghost" onClick={() => send.mutate(t.id)} disabled={!reply[t.id]?.trim()}>Reply</Btn></div>)}
            {endpoints.patch && canAct && <div className="mt-1 text-right">{t.status === "open" ? <button className="text-xs font-medium text-emerald-700 hover:underline" onClick={() => patch.mutate({ id: t.id, status: "resolved" })}>✓ Resolve</button>
              : <button className="text-xs text-indigo-600 hover:underline" onClick={() => patch.mutate({ id: t.id, status: "open" })}>Reopen</button>}</div>}
          </li>))}
      </ul>
    </Card>
  );
}
