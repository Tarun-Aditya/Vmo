import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Me, api, propQs, usd, useProperty } from "../lib";
import { Loading, Sev, SeverityChip } from "../ui";

type Act = { kind: string; severity: Sev; title: string; detail: string; link: string };
type Pledge = { contract_id: number; title: string; emergency_hours: number; fault_hours: number; text: string; page: number | null };
type Vend = { vendor: string; promise: Pledge | null; calls: number; measured: number; late: number; on_time_pct: number | null; median_hours: number | null; worst_hours: number | null; open: number };
type Call = { id: number; vendor: string; kind: string; description: string | null; reported_at: string; attended_at: string | null; resolved_at: string | null; promised_hours: number | null;
  attend_hours: number | null; late: boolean; open: boolean; contract_id: number | null };
type Contact = { id: number; vendor: string; property: string | null; name: string; role: string | null; phone: string | null; email: string | null; source: string };
type D = { property: string; city: string | null; kind: string | null; rooms: number | null; annual_value: number | null; value_per_room: number | null; contracts: number; vendors: string[];
  act: Act[]; service: { calls: Call[]; vendors: Vend[]; days: number; late: number; open: number }; contacts: Contact[]; alerts: { id: number; title: string; severity: Sev; link: string | null }[];
  sale: { locked_contracts: number; locked_value: number; exit_on_sale: number; on_notice: number } };

const KIND: Record<string, string> = { renewal: "Renewal", obligation: "Obligation", certificate: "Certificate", service: "Service" };
const card = "rounded-xl border border-line bg-white p-5 dark:border-slate-700 dark:bg-slate-800";
const input = "min-h-[40px] w-full rounded-lg border border-slate-300 bg-white px-2.5 text-sm dark:border-slate-600 dark:bg-slate-900";
const btn = "inline-flex min-h-[40px] items-center rounded-lg border border-slate-300 px-3 text-sm font-semibold hover:bg-slate-50 dark:border-slate-600 dark:hover:bg-slate-700";
const primary = "inline-flex min-h-[40px] items-center rounded-lg bg-indigo-600 px-4 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50";
const when = (iso: string) => new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
const hrs = (h: number | null) => (h === null ? "—" : `${h >= 10 ? Math.round(h) : h} h`);
const localNow = () => { const d = new Date(Date.now() - new Date().getTimezoneOffset() * 6e4); return d.toISOString().slice(0, 16); };

/** The property manager's page: one hotel, what needs doing this week, how the vendors on site are performing, and who to call. */
export default function MyProperty() {
  const qc = useQueryClient();
  const who = useQuery({ queryKey: ["whoami"], queryFn: () => api<Me>("/api/auth/me") });
  const [prop, setProp, locked] = useProperty(who.data);
  const q = useQuery({ queryKey: ["my-property", prop], queryFn: () => api<D & { choose?: string[] }>("/api/my-property" + propQs(prop)) });
  const refresh = () => qc.invalidateQueries({ queryKey: ["my-property"] });
  const [call, setCall] = useState({ vendor: "", kind: "fault", description: "", reported_at: "", attended_at: "" });
  const [ct, setCt] = useState({ vendor: "", name: "", role: "", phone: "", email: "" });
  const logCall = useMutation({
    mutationFn: () => api("/api/service-events", { method: "POST", body: JSON.stringify({ property: prop, vendor: call.vendor, kind: call.kind, description: call.description || null,
      reported_at: call.reported_at ? new Date(call.reported_at).toISOString() : null, attended_at: call.attended_at ? new Date(call.attended_at).toISOString() : null }) }),
    onSuccess: () => { setCall({ vendor: "", kind: "fault", description: "", reported_at: "", attended_at: "" }); refresh(); },
  });
  const mark = useMutation({ mutationFn: (v: { id: number; field: "attended_at" | "resolved_at" }) => api(`/api/service-events/${v.id}`, { method: "PATCH", body: JSON.stringify({ [v.field]: new Date().toISOString() }) }), onSuccess: refresh });
  const addCt = useMutation({ mutationFn: () => api("/api/vendor-contacts", { method: "POST", body: JSON.stringify({ ...ct, property: prop }) }), onSuccess: () => { setCt({ vendor: "", name: "", role: "", phone: "", email: "" }); refresh(); } });
  const delCt = useMutation({ mutationFn: (id: number) => api(`/api/vendor-contacts/${id}`, { method: "DELETE" }), onSuccess: refresh });

  if (!q.data) return <Loading q={q} />;
  if (q.data.choose) return (
    <div className="space-y-4">
      <h1 className="font-serif text-3xl md:text-4xl">My hotel</h1>
      <p className="text-sm text-ink-mute dark:text-slate-400">Choose the property you manage. Every screen that can be narrowed to one property will follow it (you can change it at the top of the page).</p>
      <div className="flex flex-wrap gap-2">{q.data.choose.map((p) => <button key={p} type="button" className={btn} onClick={() => setProp(p)}>{p}</button>)}</div>
    </div>);
  const d = q.data;
  const tiles: [string, string, string?][] = [
    ["Per year under contract", usd(Math.round(Number(d.annual_value ?? 0))), d.value_per_room ? `${usd(Math.round(d.value_per_room))} per room` : undefined],
    ["To act on", String(d.act.length), d.act.filter((a) => a.severity === "critical").length ? `${d.act.filter((a) => a.severity === "critical").length} critical` : undefined],
    ["Late service calls", String(d.service.late), `last ${d.service.days} days · ${d.service.open} still open`],
    ["Contracts here", String(d.contracts), `${d.vendors.length} vendors`],
  ];
  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wider text-ink-mute">My hotel{d.kind || d.city ? ` · ${[d.kind, d.city].filter(Boolean).join(" · ")}` : ""}</div>
          <h1 className="mt-1 font-serif text-3xl md:text-4xl">{d.property}</h1>
        </div>
        {!locked && <button type="button" className={btn} onClick={() => setProp("")}>Change property</button>}
      </header>

      <section className="grid grid-cols-2 gap-3 md:grid-cols-4" aria-label="Key figures">
        {tiles.map(([l, v, sub]) => (
          <div key={l} className={card}><div className="text-xs font-semibold uppercase tracking-wider text-ink-mute">{l}</div><div className="mt-1 font-serif text-3xl tabular-nums">{v}</div>{sub && <div className="mt-1 text-xs text-ink-mute">{sub}</div>}</div>))}
      </section>

      <section className={card} aria-label="To act on">
        <h2 className="font-serif text-2xl">To act on</h2>
        {!d.act.length && <p className="mt-2 text-sm text-ink-mute">Nothing needs action at this property right now.</p>}
        <ul className="mt-3 divide-y divide-slate-100 dark:divide-slate-700">
          {d.act.map((a, i) => (
            <li key={i} className="flex flex-wrap items-start gap-3 py-2.5">
              <SeverityChip sev={a.severity} />
              <span className="w-24 shrink-0 text-xs font-semibold uppercase tracking-wider text-ink-mute">{KIND[a.kind]}</span>
              <div className="min-w-0 flex-1"><Link className="font-medium text-indigo-700 hover:underline dark:text-indigo-300" to={a.link.startsWith("#") ? "/my-property" : a.link}>{a.title}</Link>
                <div className="text-xs text-ink-mute">{a.detail}</div></div>
            </li>))}
        </ul>
      </section>

      <section id="service" className={card} aria-label="Service at this property">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="font-serif text-2xl">Service on site</h2>
          <span className="text-xs text-ink-mute">Response promised by each vendor's contract, against the calls logged here (last {d.service.days} days)</span>
        </div>
        <div className="mt-3 overflow-x-auto"><table className="w-full text-sm">
          <thead><tr className="text-left text-xs uppercase tracking-wide text-ink-mute"><th className="py-2 pr-3">Vendor</th><th className="pr-3">Promised</th><th className="pr-3 text-right">Calls</th><th className="pr-3 text-right">On time</th><th className="pr-3 text-right">Typical</th><th className="pr-3 text-right">Worst</th><th className="text-right">Open</th></tr></thead>
          <tbody>{d.service.vendors.map((v) => (
            <tr key={v.vendor} className="border-t border-slate-100 dark:border-slate-700">
              <td className="py-2 pr-3 font-medium">{v.vendor}</td>
              <td className="pr-3 text-xs">{v.promise ? <Link className="text-indigo-700 hover:underline dark:text-indigo-300" to={`/contracts/${v.promise.contract_id}`} title={v.promise.text}>
                {v.promise.emergency_hours !== v.promise.fault_hours ? `${v.promise.emergency_hours} h emergency · ${v.promise.fault_hours} h other` : `within ${v.promise.fault_hours} h`}</Link> : <span className="text-ink-mute">not stated</span>}</td>
              <td className="pr-3 text-right tabular-nums">{v.calls}</td>
              <td className={`pr-3 text-right tabular-nums ${v.late ? "font-semibold text-red-700 dark:text-red-300" : ""}`}>{v.on_time_pct === null ? "—" : `${v.on_time_pct}%`}{v.late ? ` (${v.late} late)` : ""}</td>
              <td className="pr-3 text-right tabular-nums">{hrs(v.median_hours)}</td><td className="pr-3 text-right tabular-nums">{hrs(v.worst_hours)}</td>
              <td className="text-right tabular-nums">{v.open || ""}</td>
            </tr>))}</tbody>
        </table></div>

        <h3 className="mt-5 text-sm font-semibold">Recent calls</h3>
        <ul className="mt-2 divide-y divide-slate-100 text-sm dark:divide-slate-700">
          {d.service.calls.slice(0, 12).map((c) => (
            <li key={c.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
              <span className="w-28 shrink-0 tabular-nums text-ink-mute">{when(c.reported_at)}</span>
              <span className="min-w-0 flex-1"><b>{c.vendor}</b> · {c.description || c.kind}{c.kind === "emergency" && <span className="ml-1 text-xs font-semibold uppercase text-red-700"> emergency</span>}</span>
              <span className={`text-xs ${c.late ? "font-semibold text-red-700 dark:text-red-300" : "text-ink-mute"}`}>
                {c.late && <span aria-hidden>▲ </span>}{c.kind === "planned" ? "planned work" : c.attend_hours === null ? "not attended yet" : `attended in ${hrs(c.attend_hours)}`}{c.promised_hours !== null ? ` · promised ${c.promised_hours} h` : ""}</span>
              {c.attended_at === null && <button type="button" className={btn} onClick={() => mark.mutate({ id: c.id, field: "attended_at" })}>Attended now</button>}
              {c.attended_at !== null && c.open && <button type="button" className={btn} onClick={() => mark.mutate({ id: c.id, field: "resolved_at" })}>Fixed now</button>}
            </li>))}
          {!d.service.calls.length && <li className="py-2 text-ink-mute">No calls logged in this period.</li>}
        </ul>

        <form className="mt-4 grid gap-2 rounded-lg bg-paper p-3 sm:grid-cols-6 dark:bg-slate-900" onSubmit={(e) => { e.preventDefault(); logCall.mutate(); }} aria-label="Log a service call">
          <div className="text-sm font-semibold sm:col-span-6">Log a service call</div>
          <select className={`${input} sm:col-span-2`} required aria-label="Vendor" value={call.vendor} onChange={(e) => setCall({ ...call, vendor: e.target.value })}>
            <option value="">Vendor…</option>{d.vendors.map((v) => <option key={v}>{v}</option>)}</select>
          <select className={input} aria-label="Kind" value={call.kind} onChange={(e) => setCall({ ...call, kind: e.target.value })}>
            <option value="fault">Fault</option><option value="emergency">Emergency</option><option value="request">Request</option><option value="planned">Planned</option></select>
          <input className={`${input} sm:col-span-3`} aria-label="What happened" placeholder="What happened" value={call.description} onChange={(e) => setCall({ ...call, description: e.target.value })} />
          <label className="text-xs text-ink-mute sm:col-span-2">Reported<input className={input} type="datetime-local" max={localNow()} value={call.reported_at} onChange={(e) => setCall({ ...call, reported_at: e.target.value })} /></label>
          <label className="text-xs text-ink-mute sm:col-span-2">Attended (if already)<input className={input} type="datetime-local" max={localNow()} value={call.attended_at} onChange={(e) => setCall({ ...call, attended_at: e.target.value })} /></label>
          <div className="flex items-end sm:col-span-2"><button className={primary} disabled={!call.vendor || logCall.isPending}>{logCall.isPending ? "Saving…" : "Log call"}</button>
            {logCall.error && <span className="ml-2 text-xs text-red-600">{String(logCall.error)}</span>}</div>
        </form>
      </section>

      <section className={card} aria-label="Who to call">
        <h2 className="font-serif text-2xl">Who to call</h2>
        <div className="mt-3 overflow-x-auto"><table className="w-full text-sm">
          <thead><tr className="text-left text-xs uppercase tracking-wide text-ink-mute"><th className="py-2 pr-3">Vendor</th><th className="pr-3">Name</th><th className="pr-3">Role</th><th className="pr-3">Phone</th><th className="pr-3">E-mail</th><th /></tr></thead>
          <tbody>{d.contacts.map((c) => (
            <tr key={c.id} className="border-t border-slate-100 dark:border-slate-700">
              <td className="py-2 pr-3">{c.vendor}</td><td className="pr-3 font-medium">{c.name}{c.property ? "" : <span className="ml-1 text-xs text-ink-mute">(all properties)</span>}</td>
              <td className="pr-3 text-ink-mute">{c.role}</td>
              <td className="pr-3 tabular-nums">{c.phone ? <a className="text-indigo-700 hover:underline dark:text-indigo-300" href={`tel:${c.phone}`}>{c.phone}</a> : "—"}</td>
              <td className="pr-3">{c.email ? <a className="text-indigo-700 hover:underline dark:text-indigo-300" href={`mailto:${c.email}`}>{c.email}</a> : "—"}</td>
              <td className="text-right">{c.property && <button type="button" className="text-xs text-red-700 hover:underline" onClick={() => delCt.mutate(c.id)} aria-label={`Remove ${c.name}`}>Remove</button>}</td>
            </tr>))}
            {!d.contacts.length && <tr><td colSpan={6} className="py-3 text-ink-mute">No contacts recorded yet. Contracts rarely name a day-to-day contact: add the ones you use.</td></tr>}
          </tbody></table></div>
        <form className="mt-3 grid gap-2 sm:grid-cols-6" onSubmit={(e) => { e.preventDefault(); addCt.mutate(); }} aria-label="Add a contact">
          <select className={`${input} sm:col-span-2`} required aria-label="Contact vendor" value={ct.vendor} onChange={(e) => setCt({ ...ct, vendor: e.target.value })}><option value="">Vendor…</option>{d.vendors.map((v) => <option key={v}>{v}</option>)}</select>
          <input className={input} required aria-label="Contact name" placeholder="Name" value={ct.name} onChange={(e) => setCt({ ...ct, name: e.target.value })} />
          <input className={input} aria-label="Contact role" placeholder="Role" value={ct.role} onChange={(e) => setCt({ ...ct, role: e.target.value })} />
          <input className={input} aria-label="Contact phone" placeholder="Phone" value={ct.phone} onChange={(e) => setCt({ ...ct, phone: e.target.value })} />
          <div className="flex gap-2"><input className={input} aria-label="Contact e-mail" placeholder="E-mail" type="email" value={ct.email} onChange={(e) => setCt({ ...ct, email: e.target.value })} />
            <button className={primary} disabled={!ct.vendor || !ct.name || addCt.isPending}>Add</button></div>
        </form>
      </section>

      <section className={card} aria-label="If the property were sold">
        <h2 className="font-serif text-2xl">If this property were sold</h2>
        <p className="mt-2 text-sm">{d.sale.exit_on_sale} contract{d.sale.exit_on_sale !== 1 ? "s" : ""} can be ended on the sale, {d.sale.on_notice} on notice, and{" "}
          <b className={d.sale.locked_contracts ? "text-red-700 dark:text-red-300" : ""}>{d.sale.locked_contracts} cannot be ended early</b>
          {d.sale.locked_contracts ? <> (about {usd(Math.round(d.sale.locked_value))} still to run).</> : "."} <Link className="text-indigo-700 hover:underline dark:text-indigo-300" to="/properties">Details on Properties</Link></p>
      </section>
    </div>
  );
}
