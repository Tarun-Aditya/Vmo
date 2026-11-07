import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router-dom";
import Comments from "../components/Comments";
import DocEditor from "../components/DocEditor";
import { Btn, Field, inputCls } from "../forms";
import { api } from "../lib";

type Shared = { title: string; vendor: string; type: string; md: string; level: "view" | "comment" | "edit"; version: number; redline?: { clause_type: string; heading: string; status: string; severity: string; deviation: string; suggested_text: string }[] };

/** A draft opened through a share link: no account needed. The link's level decides whether the guest can only read, comment, or edit. */
export default function SharedDoc() {
  const { token } = useParams();
  const [name, setName] = useState(() => { try { return localStorage.getItem("ciq_guest") ?? ""; } catch { return ""; } });
  const [ok, setOk] = useState(!!name);
  const [md, setMd] = useState<string | null>(null);
  const [saved, setSaved] = useState("");
  const q = useQuery({ queryKey: ["shared", token], queryFn: async () => { const d = await api<Shared>(`/api/shared/${token}`); setMd((m) => m ?? d.md); return d; }, retry: false });
  if (q.isError) return <div className="mx-auto mt-20 max-w-md rounded border border-amber-400 bg-amber-50 p-4 text-sm text-amber-900" role="alert"><b>This link is not valid any more.</b> It may have expired or been revoked. Ask the sender for a new one.</div>;
  if (!q.data || md === null) return <div className="p-8 text-sm text-slate-500">Loading…</div>;
  const d = q.data;
  if (!ok) return (
    <div className="mx-auto mt-20 max-w-sm space-y-3 rounded-lg border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-800">
      <h1 className="text-lg font-semibold">{d.title}</h1><p className="text-sm text-slate-500">Shared with you to {d.level === "view" ? "read" : d.level === "comment" ? "read and comment on" : "edit"}. Enter your name so others know who you are.</p>
      <Field label="Your name"><input className={inputCls} aria-label="Your name" value={name} onChange={(e) => setName(e.target.value)} /></Field>
      <Btn disabled={!name.trim()} onClick={() => { try { localStorage.setItem("ciq_guest", name); } catch { /* private mode */ } setOk(true); }}>Open the document</Btn>
    </div>);
  const save = async () => { try { const r = await api<{ version: number }>(`/api/shared/${token}/content`, { method: "PUT", body: JSON.stringify({ md, name }) }); setSaved(`Saved as version ${r.version}`); } catch (e) { setSaved(String(e).replace("Error: ", "")); } };
  return (
    <div className="mx-auto max-w-7xl space-y-3 p-4">
      <div className="flex flex-wrap items-center gap-3"><h1 className="text-xl font-semibold">{d.title}</h1><span className="rounded bg-slate-200 px-1.5 text-xs font-semibold uppercase dark:bg-slate-700">{d.level}</span>
        <span className="text-sm text-slate-500">Signed in as {name} (guest)</span>{d.level === "edit" && <span className="ml-auto"><Btn onClick={save}>Save new version</Btn></span>}{saved && <span className="text-xs text-slate-500">{saved}</span>}</div>
      <div className="grid gap-4 lg:grid-cols-4">
        <div className="lg:col-span-3"><DocEditor value={md} onChange={setMd} readOnly={d.level !== "edit"} title={d.title} status={`Version ${d.version}`} height="75vh" /></div>
        <Comments docId={`shared-${token}`} canAct={d.level !== "view"} endpoints={{ list: `/api/shared/${token}`, add: `/api/shared/${token}/threads`, reply: (id) => `/api/shared/${token}/threads/${id}/comments`, guestName: name }} />
      </div>
      {!!d.redline?.length && (
        <section className="rounded border border-slate-200 p-3 dark:border-slate-700" aria-label="Playbook findings"><h2 className="mb-2 text-sm font-semibold">Playbook findings ({d.redline.length})</h2>
          <ul className="space-y-2 text-sm">{d.redline.map((i) => (
            <li key={i.clause_type}><span className="mr-2 rounded bg-slate-200 px-1.5 text-xs font-bold uppercase dark:bg-slate-700">{i.severity}</span><b>{i.heading}</b> — {i.deviation}
              {i.suggested_text && <div className="mt-1 rounded bg-emerald-50 p-2 text-xs text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200"><u>Suggested:</u> {i.suggested_text}</div>}</li>))}</ul></section>)}
    </div>
  );
}
