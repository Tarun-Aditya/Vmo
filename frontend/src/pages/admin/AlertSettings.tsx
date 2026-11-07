import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Btn, Field, Toggle, inputCls } from "../../forms";
import { api, ago } from "../../lib";
import { Card, Loading } from "../../ui";

type Rule = { key: string; name: string; description: string | null; severity: string; params: Record<string, number | string>; channels: string[]; enabled: boolean; open_alerts: number };
type Chan = { id: number; name: string; kind: "email" | "slack" | "teams" | "webhook"; config: Record<string, string | boolean>; secrets_set: Record<string, boolean>; enabled: boolean; min_severity: string; last_status: string | null; last_message: string | null; last_sent_at: string | null };
type Draft = { id?: number; name: string; kind: Chan["kind"]; config: Record<string, string | boolean>; secrets: Record<string, string>; enabled: boolean; min_severity: string };
const SEVS = ["low", "medium", "high", "critical"];
const CH: [string, string][] = [["in_app", "In app"], ["email", "E-mail"], ["chat", "Slack / Teams / webhook"]];
const blank = (): Draft => ({ name: "", kind: "email", config: { port: "25" }, secrets: {}, enabled: true, min_severity: "high" });

function Rules() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["alert-rules"], queryFn: () => api<Rule[]>("/api/admin/alert-rules") });
  const put = useMutation({ mutationFn: (v: { key: string; body: Partial<Rule> }) => api(`/api/admin/alert-rules/${v.key}`, { method: "PUT", body: JSON.stringify(v.body) }), onSuccess: () => qc.invalidateQueries({ queryKey: ["alert-rules"] }) });
  if (!q.data) return <Loading q={q} />;
  return (
    <Card title="Alert rules">
      <p className="mb-3 text-sm text-slate-500">Each rule watches the live data and raises an alert once per event. Choose where it goes and how serious it is.</p>
      <div className="divide-y divide-slate-200 dark:divide-slate-700">
        {q.data.map((r) => (
          <div key={r.key} className="flex flex-wrap items-center gap-3 py-2 text-sm">
            <Toggle checked={r.enabled} label={`${r.name} enabled`} onChange={(v) => put.mutate({ key: r.key, body: { enabled: v } })} />
            <div className="min-w-[14rem] flex-1"><div className="font-medium">{r.name}</div>{r.description && <div className="text-xs text-slate-500">{r.description}</div>}</div>
            {Object.entries(r.params).map(([k, v]) => (
              <label key={k} className="flex items-center gap-1 text-xs text-slate-500">{k.replace("_", " ")}
                {k === "min_severity" || k === "min_tier" ? <select className={`${inputCls} w-24`} aria-label={`${r.name} ${k}`} value={String(v)} onChange={(e) => put.mutate({ key: r.key, body: { params: { ...r.params, [k]: e.target.value } } })}>{SEVS.map((s) => <option key={s}>{s}</option>)}</select>
                  : <input className={`${inputCls} w-16`} type="number" min={0} aria-label={`${r.name} ${k}`} defaultValue={Number(v)} onBlur={(e) => Number(e.target.value) !== Number(v) && put.mutate({ key: r.key, body: { params: { ...r.params, [k]: Number(e.target.value) } } })} />}
              </label>))}
            <select className={`${inputCls} w-28`} aria-label={`${r.name} severity`} value={r.severity} onChange={(e) => put.mutate({ key: r.key, body: { severity: e.target.value } })}>{SEVS.map((s) => <option key={s}>{s}</option>)}</select>
            <div className="flex gap-2 text-xs">{CH.map(([k, l]) => <label key={k} className="flex items-center gap-1"><input type="checkbox" checked={r.channels.includes(k)} onChange={(e) => put.mutate({ key: r.key, body: { channels: e.target.checked ? [...r.channels, k] : r.channels.filter((x) => x !== k) } })} />{l}</label>)}</div>
            <span className="w-14 text-right text-xs text-slate-500">{r.open_alerts} open</span>
          </div>))}
      </div>
    </Card>
  );
}

function Channels() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["alert-channels"], queryFn: () => api<Chan[]>("/api/admin/alert-channels") });
  const [edit, setEdit] = useState<Draft | null>(null);
  const [msg, setMsg] = useState<Record<number, { ok: boolean; text: string }>>({});
  const refresh = () => qc.invalidateQueries({ queryKey: ["alert-channels"] });
  const save = useMutation({ mutationFn: (d: Draft) => api<Chan>(d.id ? `/api/admin/alert-channels/${d.id}` : "/api/admin/alert-channels", { method: d.id ? "PUT" : "POST", body: JSON.stringify(d) }), onSuccess: () => { setEdit(null); refresh(); } });
  const test = useMutation({ mutationFn: (id: number) => api<{ ok: boolean; error?: string }>(`/api/admin/alert-channels/${id}/test`, { method: "POST" }), onSuccess: (r, id) => { setMsg((m) => ({ ...m, [id]: { ok: r.ok, text: r.ok ? "Test alert delivered." : r.error ?? "failed" } })); refresh(); } });
  const del = useMutation({ mutationFn: (id: number) => api(`/api/admin/alert-channels/${id}`, { method: "DELETE" }), onSuccess: refresh });
  if (!q.data) return <Loading q={q} />;
  const cfg = (k: string, label: string, ph?: string) => edit && <Field key={k} label={label}><input className={inputCls} aria-label={label} placeholder={ph} value={String(edit.config[k] ?? "")} onChange={(e) => setEdit({ ...edit, config: { ...edit.config, [k]: e.target.value } })} /></Field>;
  const sec = (k: string, label: string) => edit && <Field key={k} label={label} hint={edit.id ? "Leave blank to keep the stored value." : undefined}><input className={inputCls} type="password" autoComplete="off" aria-label={label} value={edit.secrets[k] ?? ""} onChange={(e) => setEdit({ ...edit, secrets: { ...edit.secrets, [k]: e.target.value } })} /></Field>;
  return (
    <Card title="Delivery channels" right={<Btn onClick={() => setEdit(blank())}>+ Add channel</Btn>}>
      <p className="mb-3 text-sm text-slate-500">Where alerts are sent besides the notification centre. Secrets (SMTP password, webhook URL) are stored encrypted and never shown again.</p>
      {edit && (
        <div className="mb-4 grid gap-3 rounded border border-slate-200 p-3 md:grid-cols-3 dark:border-slate-700">
          <Field label="Name"><input className={inputCls} aria-label="Channel name" value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></Field>
          <Field label="Type"><select className={inputCls} aria-label="Channel type" value={edit.kind} disabled={!!edit.id} onChange={(e) => setEdit({ ...edit, kind: e.target.value as Chan["kind"], config: {}, secrets: {} })}><option value="email">E-mail (SMTP)</option><option value="slack">Slack</option><option value="teams">Microsoft Teams</option><option value="webhook">Generic webhook (JSON)</option></select></Field>
          <Field label="Send from severity"><select className={inputCls} aria-label="Minimum severity" value={edit.min_severity} onChange={(e) => setEdit({ ...edit, min_severity: e.target.value })}>{SEVS.map((s) => <option key={s}>{s}</option>)}</select></Field>
          {edit.kind === "email" ? <>{cfg("host", "SMTP host", "smtp.company.com")}{cfg("port", "Port")}{cfg("from", "From", "contractiq@company.com")}{cfg("to", "To", "vmo@company.com")}{cfg("username", "Username")}{sec("password", "Password")}{cfg("app_url", "App URL (for links)", "https://contractiq.company.com")}
              <Field label="Security"><div className="flex gap-4 pt-1 text-sm"><label className="flex items-center gap-1"><input type="checkbox" checked={!!edit.config.starttls} onChange={(e) => setEdit({ ...edit, config: { ...edit.config, starttls: e.target.checked } })} />STARTTLS</label><label className="flex items-center gap-1"><input type="checkbox" checked={!!edit.config.ssl} onChange={(e) => setEdit({ ...edit, config: { ...edit.config, ssl: e.target.checked } })} />SSL</label></div></Field></>
            : sec("url", edit.kind === "webhook" ? "Webhook URL" : `${edit.kind === "slack" ? "Slack" : "Teams"} incoming-webhook URL`)}
          <div className="flex items-center gap-3 md:col-span-3">
            <Btn onClick={() => save.mutate(edit)} disabled={!edit.name.trim() || save.isPending}>Save channel</Btn><Btn kind="ghost" onClick={() => setEdit(null)}>Cancel</Btn>
            {save.error && <span className="text-sm text-red-600">{String(save.error)}</span>}
          </div>
        </div>)}
      {q.data.length === 0 && !edit && <p className="text-sm text-slate-500">No channels yet: alerts appear in the notification centre only.</p>}
      <ul className="divide-y divide-slate-200 dark:divide-slate-700">
        {q.data.map((c) => (
          <li key={c.id} className="flex flex-wrap items-center gap-3 py-2 text-sm">
            <Toggle checked={c.enabled} label={`${c.name} enabled`} onChange={(v) => save.mutate({ ...c, enabled: v, secrets: {} })} />
            <div className="flex-1"><b>{c.name}</b> <span className="text-xs text-slate-500">{c.kind} · from {c.min_severity}{c.last_sent_at && ` · last ${c.last_status === "ok" ? "✓" : "✗"} ${ago(c.last_sent_at)}`}</span>
              {msg[c.id] && <div role="status" className={`text-xs ${msg[c.id].ok ? "text-emerald-700 dark:text-emerald-400" : "text-red-600"}`}>{msg[c.id].text}</div>}</div>
            <Btn kind="ghost" onClick={() => test.mutate(c.id)}>Send test</Btn><Btn kind="ghost" onClick={() => setEdit({ ...c, secrets: {} })}>Edit</Btn>
            <button className="text-xs text-red-600 hover:underline" onClick={() => window.confirm(`Delete channel “${c.name}”?`) && del.mutate(c.id)}>Delete</button>
          </li>))}
      </ul>
    </Card>
  );
}

function Sim() {
  const qc = useQueryClient();
  const meta = useQuery({ queryKey: ["meta"], queryFn: () => api<{ simulators?: boolean }>("/api/meta") });
  const out = useQuery({ queryKey: ["sim-outbox"], queryFn: () => api<{ channel: string; kind: string; text: string | null }[]>("/sim/outbox"), enabled: !!meta.data?.simulators, refetchInterval: 5000 });
  const add = useMutation({ mutationFn: () => api("/api/admin/alert-channels/demo", { method: "POST" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["alert-channels"] }) });
  const run = useMutation({ mutationFn: () => api("/api/alerts/evaluate", { method: "POST" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["sim-outbox"] }) });
  if (!meta.data?.simulators) return null;
  return (
    <Card title="Demo: simulated Slack, Teams, webhook and e-mail" right={<div className="flex gap-2"><Btn kind="ghost" onClick={() => add.mutate()}>Add demo channels</Btn><Btn kind="ghost" onClick={() => run.mutate()}>Check alerts now</Btn></div>}>
      <p className="mb-2 text-sm text-slate-500">These channels deliver to sinks built into the app. Whatever they receive shows here, as it would arrive in the real service.</p>
      <ul className="max-h-60 space-y-0.5 overflow-auto text-xs">{(out.data ?? []).map((m, i) => <li key={i}><b>{m.channel}</b> <span className="text-slate-500">({m.kind})</span> {m.text}</li>)}{out.data?.length === 0 && <li className="text-slate-500">Nothing received yet.</li>}</ul>
    </Card>
  );
}

export default function AlertSettings() {
  return <div className="space-y-4"><Sim /><Rules /><Channels /></div>;
}
