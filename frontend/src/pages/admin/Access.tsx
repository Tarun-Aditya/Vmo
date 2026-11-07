import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Btn, Field, Toggle, inputCls } from "../../forms";
import { Pill } from "../../components/vmo";
import { api, ago, when } from "../../lib";
import { Card, Loading } from "../../ui";

type User = { id: number; email: string; name: string | null; role: "viewer" | "reviewer" | "admin"; source: string; active: boolean; last_login_at: string | null; tokens: number };
type Tok = { id: number; name: string; prefix: string; role: string; created_at: string; last_used_at: string | null; revoked: boolean };
type Entry = { id: number; ts: string; user_email: string | null; role: string | null; method: string; path: string; status: number | null; event: string };
const ROLE_HELP = { viewer: "read everything, ask questions", reviewer: "+ review redlines, edit documents, acknowledge alerts, mark obligations", admin: "+ configuration, connectors, users, audit log" };

function Tokens({ u }: { u: User }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["tokens", u.id], queryFn: () => api<Tok[]>(`/api/users/${u.id}/tokens`) });
  const [name, setName] = useState("");
  const [role, setRole] = useState<User["role"]>("viewer");
  const [fresh, setFresh] = useState<string | null>(null);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["tokens", u.id] }); qc.invalidateQueries({ queryKey: ["users"] }); };
  const add = useMutation({ mutationFn: () => api<{ token: string }>(`/api/users/${u.id}/tokens`, { method: "POST", body: JSON.stringify({ name, role }) }), onSuccess: (r) => { setFresh(r.token); setName(""); refresh(); } });
  const revoke = useMutation({ mutationFn: (id: number) => api(`/api/users/${u.id}/tokens/${id}`, { method: "DELETE" }), onSuccess: refresh });
  return (
    <div className="mt-2 space-y-2 rounded bg-slate-50 p-3 text-sm dark:bg-slate-900">
      <div className="flex flex-wrap items-center gap-2">
        <input className={`${inputCls} w-48`} aria-label="Token name" placeholder="Token name (e.g. BI tool)" value={name} onChange={(e) => setName(e.target.value)} />
        <select className={`${inputCls} w-32`} aria-label="Token role" value={role} onChange={(e) => setRole(e.target.value as User["role"])}>{["viewer", "reviewer", "admin"].map((r) => <option key={r}>{r}</option>)}</select>
        <Btn kind="ghost" onClick={() => add.mutate()} disabled={!name.trim()}>Create API token</Btn>
      </div>
      {fresh && <p role="status" className="break-all rounded border border-emerald-500 bg-emerald-50 p-2 font-mono text-xs text-emerald-900">Copy it now, it is not shown again: {fresh}</p>}
      <ul className="space-y-0.5 text-xs">
        {(q.data ?? []).map((t) => <li key={t.id} className={t.revoked ? "text-slate-400 line-through" : ""}>{t.name} · <code>{t.prefix}…</code> · {t.role} · {t.last_used_at ? `used ${ago(t.last_used_at)}` : "never used"} {!t.revoked && <button className="ml-2 text-red-600 hover:underline" onClick={() => revoke.mutate(t.id)}>Revoke</button>}</li>)}
        {q.data?.length === 0 && <li className="text-slate-500">No API tokens.</li>}
      </ul>
    </div>
  );
}

function Users() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["users"], queryFn: () => api<User[]>("/api/users") });
  const [f, setF] = useState({ email: "", name: "", password: "", role: "viewer" });
  const [open, setOpen] = useState<number | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ["users"] });
  const add = useMutation({ mutationFn: () => api("/api/users", { method: "POST", body: JSON.stringify(f) }), onSuccess: () => { setF({ email: "", name: "", password: "", role: "viewer" }); refresh(); } });
  const upd = useMutation({ mutationFn: (u: User & { password?: string }) => api(`/api/users/${u.id}`, { method: "PUT", body: JSON.stringify(u) }), onSuccess: refresh });
  const del = useMutation({ mutationFn: (id: number) => api(`/api/users/${id}`, { method: "DELETE" }), onSuccess: refresh });
  if (!q.data) return <Loading q={q} />;
  return (
    <Card title="Users and roles">
      <p className="mb-3 text-sm text-slate-500">{(Object.entries(ROLE_HELP) as [string, string][]).map(([r, h]) => <span key={r} className="mr-4"><b>{r}</b>: {h}</span>)}</p>
      <div className="mb-4 grid gap-2 md:grid-cols-5">
        <input className={inputCls} aria-label="New user e-mail" placeholder="e-mail" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
        <input className={inputCls} aria-label="New user name" placeholder="name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
        <input className={inputCls} type="password" autoComplete="new-password" aria-label="New user password" placeholder="password (8+)" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
        <select className={inputCls} aria-label="New user role" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>{["viewer", "reviewer", "admin"].map((r) => <option key={r}>{r}</option>)}</select>
        <Btn onClick={() => add.mutate()} disabled={!f.email || f.password.length < 8}>+ Add user</Btn>
      </div>
      {(add.error || upd.error || del.error) && <p role="alert" className="mb-2 text-sm text-red-600">{String(add.error ?? upd.error ?? del.error).replace("Error: ", "")}</p>}
      <ul className="divide-y divide-slate-200 dark:divide-slate-700">
        {q.data.map((u) => (
          <li key={u.id} className="py-2 text-sm">
            <div className="flex flex-wrap items-center gap-3">
              <Toggle checked={u.active} label={`${u.email} active`} onChange={(v) => upd.mutate({ ...u, active: v })} />
              <div className="min-w-[12rem] flex-1"><b>{u.name || u.email}</b> {u.name && <span className="text-xs text-slate-500">{u.email}</span>} {u.source !== "local" && <Pill>{u.source}</Pill>}
                <div className="text-xs text-slate-500">{u.last_login_at ? `last sign-in ${ago(u.last_login_at)}` : "never signed in"}</div></div>
              <select className={`${inputCls} w-32`} aria-label={`${u.email} role`} value={u.role} onChange={(e) => upd.mutate({ ...u, role: e.target.value as User["role"] })}>{["viewer", "reviewer", "admin"].map((r) => <option key={r}>{r}</option>)}</select>
              <button className="text-xs text-indigo-600 hover:underline dark:text-indigo-400" onClick={() => setOpen(open === u.id ? null : u.id)}>API tokens ({u.tokens})</button>
              <button className="text-xs text-red-600 hover:underline" onClick={() => window.confirm(`Delete ${u.email}?`) && del.mutate(u.id)}>Delete</button>
            </div>
            {open === u.id && <Tokens u={u} />}
          </li>))}
      </ul>
    </Card>
  );
}

function Audit() {
  const [event, setEvent] = useState("");
  const q = useQuery({ queryKey: ["audit", event], queryFn: () => api<Entry[]>(`/api/audit?limit=200${event ? `&event=${event}` : ""}`), refetchInterval: 10000 });
  return (
    <Card title="Audit log" right={<select className={`${inputCls} w-36`} aria-label="Audit filter" value={event} onChange={(e) => setEvent(e.target.value)}><option value="">All events</option><option value="request">Changes</option><option value="denied">Denied</option><option value="login">Sign-ins</option><option value="login_failed">Failed sign-ins</option></select>}>
      <p className="mb-2 text-sm text-slate-500">Every change, sign-in, refusal and export, with who did it. Reads are not logged.</p>
      <div className="max-h-96 overflow-auto">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 bg-white text-slate-500 dark:bg-slate-800"><tr><th className="py-1 pr-3">When</th><th className="pr-3">Who</th><th className="pr-3">Event</th><th className="pr-3">Request</th><th>Result</th></tr></thead>
          <tbody>
            {(q.data ?? []).map((a) => (
              <tr key={a.id} className="border-t border-slate-100 dark:border-slate-700">
                <td className="whitespace-nowrap py-1 pr-3 tabular-nums">{when(a.ts)}</td><td className="pr-3">{a.user_email ?? "—"}{a.role && <span className="text-slate-400"> · {a.role}</span>}</td>
                <td className="pr-3">{a.event}</td><td className="pr-3 font-mono">{a.method} {a.path}</td><td className={a.status && a.status >= 400 ? "font-semibold text-red-600" : ""}>{a.status ?? ""}</td>
              </tr>))}
          </tbody>
        </table>
        {q.data?.length === 0 && <p className="py-3 text-sm text-slate-500">Nothing logged yet.</p>}
      </div>
    </Card>
  );
}

export default function Access() {
  return <div className="space-y-4"><Users /><Audit /></div>;
}
