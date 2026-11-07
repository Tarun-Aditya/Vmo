import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Btn, Field, Toggle, inputCls } from "../../forms";
import { Pill } from "../../components/vmo";
import { api, ago, inFuture } from "../../lib";
import { Card, Loading } from "../../ui";

type Conn = { id: number; name: string; type: "gdrive" | "onedrive" | "sharepoint" | "imap" | "coupa" | "sap" | "ariba" | "rest"; type_label: string; config: Record<string, string | boolean>; secrets_set: Record<string, boolean>; target: "contracts" | "drafts" | "feeds"; enabled: boolean;
  trigger_mode: "periodic" | "manual"; interval_minutes: number; last_sync_at: string | null; next_sync_at: string | null; last_status: string | null; last_message: string | null; files: number };
type Draft = { id?: number; name: string; type: Conn["type"]; config: Record<string, string | boolean>; secrets: Record<string, string>; target: "contracts" | "drafts" | "feeds"; enabled: boolean; trigger_mode: "periodic" | "manual"; interval_minutes: number };
type RemoteFile = { path: string; status: string; modified: string | null; size: number | null; web_url: string | null };

const FIELDS: Record<Conn["type"], { cfg: [string, string, string?][]; sec: [string, string, string?][] }> = {
  gdrive: { cfg: [["folder", "Drive folder (link or ID)", "https://drive.google.com/drive/folders/…"]], sec: [["service_account_json", "Service account key (JSON)", "{ \"client_email\": …, \"private_key\": … } — share the folder with its e-mail"], ["refresh_token", "…or OAuth refresh token"], ["client_id", "OAuth client ID"], ["client_secret", "OAuth client secret"]] },
  onedrive: { cfg: [["tenant_id", "Tenant ID"], ["user", "User (e-mail / UPN)", "jordan@company.com"], ["drive_id", "…or drive ID"], ["folder", "Folder path", "Contracts/Vendors"]], sec: [["client_id", "Application (client) ID"], ["client_secret", "Client secret"]] },
  sharepoint: { cfg: [["tenant_id", "Tenant ID"], ["site_url", "Site URL", "https://contoso.sharepoint.com/sites/Legal"], ["library", "Document library", "Documents"], ["folder", "Folder path", "Vendor Agreements"]], sec: [["client_id", "Application (client) ID"], ["client_secret", "Client secret"]] },
  imap: { cfg: [["host", "IMAP host", "imap.company.com"], ["port", "Port", "993"], ["username", "Mailbox user", "contracts@company.com"], ["folder", "Mail folder", "INBOX"], ["from_filter", "Only from (optional)"], ["subject_filter", "Subject contains (optional)"]], sec: [["password", "Password / app password"]] },
  coupa: { cfg: [["base_url", "Coupa instance URL", "https://acme.coupahost.com"], ["scope", "OAuth scope", "core.invoice.read"]], sec: [["client_id", "OAuth client ID"], ["client_secret", "OAuth client secret"]] },
  sap: { cfg: [["base_url", "SAP API host", "https://sandbox.api.sap.com/s4hanacloud"]], sec: [["api_key", "API key (Business Accelerator Hub or gateway)"]] },
  ariba: { cfg: [["base_url", "Ariba API host"], ["token_url", "OAuth token URL"], ["path", "Reporting path"]], sec: [["client_id", "Application key / client ID"], ["client_secret", "OAuth client secret"]] },
  rest: { cfg: [["base_url", "API base URL"], ["path", "List path", "/api/invoices"], ["items_path", "Items path in JSON", "d.results"]], sec: [["token", "Bearer token"], ["api_key", "…or API key"]] },
};
const blank = (): Draft => ({ name: "", type: "gdrive", config: { recursive: true }, secrets: {}, target: "contracts", enabled: true, trigger_mode: "periodic", interval_minutes: 60 });

function Files({ id }: { id: number }) {
  const q = useQuery({ queryKey: ["connector-files", id], queryFn: () => api<RemoteFile[]>(`/api/connectors/${id}/files`) });
  if (!q.data) return <p className="text-sm text-slate-500">Loading…</p>;
  return (
    <ul className="max-h-48 space-y-0.5 overflow-auto text-xs" aria-label="Synced files">
      {q.data.map((f) => <li key={f.path} className="flex gap-2"><span className={f.status === "synced" ? "text-emerald-600" : "text-amber-600"}>{f.status === "synced" ? "✓" : "⚠"}</span><span className="flex-1 truncate">{f.web_url ? <a className="text-indigo-600 hover:underline dark:text-indigo-400" href={f.web_url} target="_blank" rel="noreferrer">{f.path}</a> : f.path}</span><span className="text-slate-500">{f.status !== "synced" ? f.status : ""}</span></li>)}
      {q.data.length === 0 && <li className="text-slate-500">No files synced yet.</li>}
    </ul>
  );
}

export default function Connectors() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["connectors"], queryFn: () => api<{ connectors: Conn[]; types: Record<string, string> }>("/api/connectors"), refetchInterval: 5000 });
  const [edit, setEdit] = useState<Draft | null>(null);
  const meta = useQuery({ queryKey: ["meta"], queryFn: () => api<{ simulators?: boolean }>("/api/meta") });
  const demo = useMutation({ mutationFn: () => api<{ connectors: { name: string; status: string; new: number }[] }>("/api/connectors/demo-erp", { method: "POST" }),
    onSuccess: (r) => { setDemoMsg(r.connectors.map((c) => `${c.name}: ${c.new} new invoice(s)`).join(" · ")); qc.invalidateQueries(); } });
  const [demoMsg, setDemoMsg] = useState("");
  const cloud = useMutation({ mutationFn: (what: string) => api<{ connectors: { name: string; new: number }[] }>(`/api/connectors/${what}`, { method: "POST" }),
    onSuccess: (r) => { setDemoMsg(r.connectors.map((c) => `${c.name}: ${c.new} new file(s)`).join(" · ")); qc.invalidateQueries(); } });
  const [open, setOpen] = useState<number | null>(null);
  const [msg, setMsg] = useState<Record<number, { ok: boolean; text: string }>>({});
  const save = useMutation({
    mutationFn: (d: Draft) => api<Conn>(d.id ? `/api/connectors/${d.id}` : "/api/connectors", { method: d.id ? "PUT" : "POST", body: JSON.stringify(d) }),
    onSuccess: () => { setEdit(null); qc.invalidateQueries({ queryKey: ["connectors"] }); },
  });
  const test = useMutation({ mutationFn: (id: number) => api<{ ok: boolean; detail: string }>(`/api/connectors/${id}/test`, { method: "POST" }), onSuccess: (r, id) => setMsg((m) => ({ ...m, [id]: { ok: r.ok, text: r.detail } })) });
  const sync = useMutation({ mutationFn: (id: number) => api<{ status: string; message: string }>(`/api/connectors/${id}/sync?wait=true`, { method: "POST" }), onSuccess: (r, id) => { setMsg((m) => ({ ...m, [id]: { ok: r.status === "ok", text: r.message } })); qc.invalidateQueries(); } });
  const del = useMutation({ mutationFn: (id: number) => api(`/api/connectors/${id}`, { method: "DELETE" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["connectors"] }) });
  if (!q.data) return <Loading q={q} />;
  const f = edit ? FIELDS[edit.type] : null;
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="max-w-3xl text-sm text-slate-500">Connect a Google Drive folder, a OneDrive folder or a SharePoint library. New and changed contracts (PDF, Word, Markdown, text) are copied into the inbox on a schedule and run through the pipeline; the original link is kept on each contract. Credentials are stored encrypted and never shown again.</p>
        <div className="flex gap-2">
          {meta.data?.simulators && <Btn kind="ghost" onClick={() => cloud.mutate("demo-cloud")} disabled={cloud.isPending} title="Simulated Google Drive, OneDrive and SharePoint with demo contracts">{cloud.isPending && cloud.variables === "demo-cloud" ? "Connecting…" : "Connect demo cloud drives"}</Btn>}
          {meta.data?.simulators && <Btn kind="ghost" onClick={() => cloud.mutate("demo-mailbox")} disabled={cloud.isPending} title="A simulated IMAP mailbox with two contract e-mails">{cloud.isPending && cloud.variables === "demo-mailbox" ? "Connecting…" : "Connect demo mailbox"}</Btn>}
          {meta.data?.simulators && <Btn kind="ghost" onClick={() => demo.mutate()} disabled={demo.isPending} title="Registers a simulated Coupa and a simulated SAP S/4HANA (built into this app) and syncs them: the real connectors run against them over HTTP">{demo.isPending ? "Connecting…" : "Connect demo ERP (simulated Coupa + SAP)"}</Btn>}
          <Btn onClick={() => setEdit(blank())}>+ Add connector</Btn></div>
      </div>

      {demoMsg && <p role="status" className="rounded border border-emerald-500 bg-emerald-50 p-2 text-sm text-emerald-900">{demoMsg}. Open <a className="underline" href="/contracts">Contracts</a>, <a className="underline" href="/spend">Spend</a> and <a className="underline" href="/alerts">Alerts</a> to see what arrived.</p>}
      {edit && f && (
        <Card title={edit.id ? `Edit ${edit.name}` : "New connector"}>
          <div className="grid gap-3 md:grid-cols-3">
            <Field label="Name"><input className={inputCls} aria-label="Connector name" value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></Field>
            <Field label="Service"><select className={inputCls} aria-label="Service" value={edit.type} disabled={!!edit.id} onChange={(e) => setEdit({ ...edit, type: e.target.value as Conn["type"], config: { recursive: true }, secrets: {}, target: ["coupa", "sap", "ariba", "rest"].includes(e.target.value) ? "feeds" : edit.target === "feeds" ? "contracts" : edit.target })}><option value="gdrive">Google Drive</option><option value="onedrive">OneDrive</option><option value="sharepoint">SharePoint</option><option value="imap">Mailbox (IMAP)</option><option value="coupa">Coupa (invoices)</option><option value="sap">SAP S/4HANA (invoices)</option><option value="ariba">SAP Ariba (invoices)</option><option value="rest">Generic REST (invoices)</option></select></Field>
            <Field label="Import as"><select className={inputCls} aria-label="Import as" value={edit.target} onChange={(e) => setEdit({ ...edit, target: e.target.value as Draft["target"] })}><option value="contracts">Executed contracts</option><option value="drafts">Vendor drafts (review queue)</option><option value="feeds">Invoices / reports (spend and SLA)</option></select></Field>
            {f.cfg.map(([k, label, ph]) => <Field key={k} label={label}><input className={inputCls} aria-label={label} placeholder={ph} value={String(edit.config[k] ?? "")} onChange={(e) => setEdit({ ...edit, config: { ...edit.config, [k]: e.target.value } })} /></Field>)}
            {f.sec.map(([k, label, ph]) => (
              <Field key={k} label={label} hint={edit.id ? "Leave blank to keep the stored value." : undefined}>
                {k === "service_account_json" ? <textarea className={`${inputCls} h-16 font-mono text-xs`} aria-label={label} placeholder={ph} value={edit.secrets[k] ?? ""} onChange={(e) => setEdit({ ...edit, secrets: { ...edit.secrets, [k]: e.target.value } })} />
                  : <input className={inputCls} type="password" autoComplete="off" aria-label={label} value={edit.secrets[k] ?? ""} onChange={(e) => setEdit({ ...edit, secrets: { ...edit.secrets, [k]: e.target.value } })} />}
              </Field>))}
            <Field label="Include sub-folders"><label className="flex items-center gap-2 pt-1"><input type="checkbox" checked={edit.config.recursive !== false} onChange={(e) => setEdit({ ...edit, config: { ...edit.config, recursive: e.target.checked } })} />Yes</label></Field>
            <Field label="Sync"><select className={inputCls} aria-label="Sync trigger" value={edit.trigger_mode} onChange={(e) => setEdit({ ...edit, trigger_mode: e.target.value as Draft["trigger_mode"] })}><option value="periodic">On a schedule</option><option value="manual">Manual only</option></select></Field>
            {edit.trigger_mode === "periodic" && <Field label="Every (minutes)"><input className={inputCls} type="number" min={1} aria-label="Sync interval" value={edit.interval_minutes} onChange={(e) => setEdit({ ...edit, interval_minutes: Number(e.target.value) })} /></Field>}
          </div>
          <div className="mt-4 flex items-center gap-3">
            <Btn onClick={() => save.mutate(edit)} disabled={!edit.name.trim() || save.isPending}>{save.isPending ? "Saving…" : "Save connector"}</Btn>
            <Btn kind="ghost" onClick={() => setEdit(null)}>Cancel</Btn>
            {save.error && <span className="text-sm text-red-600">{String(save.error)}</span>}
          </div>
        </Card>)}

      {q.data.connectors.length === 0 && !edit && <Card><p className="text-sm text-slate-500">No connectors yet. Add one to start syncing contracts from your cloud storage.</p></Card>}
      {q.data.connectors.map((c) => (
        <Card key={c.id} title={<span>{c.name} <Pill>{c.type_label}</Pill> <Pill cls={c.target === "drafts" ? "bg-amber-100 text-amber-900" : undefined}>{c.target === "drafts" ? "vendor drafts" : "executed contracts"}</Pill></span>}
          right={<div className="flex items-center gap-2"><Toggle checked={c.enabled} label={`${c.name} enabled`} onChange={(v) => save.mutate({ ...c, enabled: v, secrets: {} })} /></div>}>
          <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-sm">
            <span>{c.files} file{c.files !== 1 ? "s" : ""} synced</span>
            <span>Last sync: {c.last_sync_at ? ago(c.last_sync_at) : "never"} {c.last_status && <b className={c.last_status === "ok" ? "text-emerald-600" : "text-red-600"}>{c.last_status === "ok" ? "✓" : "✗"}</b>}</span>
            <span>{c.trigger_mode === "manual" ? "Manual only" : c.enabled ? `Next: ${inFuture(c.next_sync_at)} (every ${c.interval_minutes} min)` : "Paused"}</span>
          </div>
          {c.last_message && <p className="mt-1 text-xs text-slate-500">{c.last_message}</p>}
          {msg[c.id] && <p className={`mt-1 text-sm ${msg[c.id].ok ? "text-emerald-700 dark:text-emerald-400" : "text-red-600"}`} role="status">{msg[c.id].ok ? "✓ " : "✗ "}{msg[c.id].text}</p>}
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Btn kind="ghost" onClick={() => test.mutate(c.id)} disabled={test.isPending}>Test connection</Btn>
            <Btn onClick={() => sync.mutate(c.id)} disabled={sync.isPending}>{sync.isPending && sync.variables === c.id ? "Syncing…" : "▶ Sync now"}</Btn>
            <Btn kind="ghost" onClick={() => setEdit({ ...c, secrets: {} })}>Edit</Btn>
            <button className="text-xs text-indigo-600 hover:underline dark:text-indigo-400" onClick={() => setOpen(open === c.id ? null : c.id)}>{open === c.id ? "Hide files" : "Show files"}</button>
            <button className="ml-auto text-xs text-red-600 hover:underline" onClick={() => window.confirm(`Delete connector “${c.name}”? Imported contracts are kept.`) && del.mutate(c.id)}>Delete</button>
          </div>
          {open === c.id && <div className="mt-2"><Files id={c.id} /></div>}
        </Card>))}
    </div>
  );
}
