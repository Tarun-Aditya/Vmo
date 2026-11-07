import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Btn, Field, inputCls } from "../forms";
import { api } from "../lib";
import { Card } from "../ui";

/** Each person switches on their own second factor: add the secret to an authenticator app, confirm with a code, keep the recovery codes. */
export default function Security() {
  const [setup, setSetup] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);
  const start = useMutation({ mutationFn: () => api<{ secret: string; otpauth_uri: string }>("/api/auth/mfa/setup", { method: "POST" }), onSuccess: setSetup });
  const enable = useMutation({ mutationFn: () => api<{ recovery_codes: string[] }>("/api/auth/mfa/enable", { method: "POST", body: JSON.stringify({ code }) }), onSuccess: (r) => { setCodes(r.recovery_codes); setSetup(null); setCode(""); } });
  const disable = useMutation({ mutationFn: () => api("/api/auth/mfa/disable", { method: "POST", body: JSON.stringify({ code }) }), onSuccess: () => { setCode(""); setCodes(null); } });
  return (
    <div className="mx-auto max-w-xl space-y-4">
      <h1 className="text-xl font-semibold">My security</h1>
      <Card title="Two-factor authentication">
        {!setup && !codes && <div className="space-y-2 text-sm"><p className="text-slate-500">Add a one-time code from an authenticator app (Microsoft Authenticator, Google Authenticator, 1Password…) to your sign-in.</p><Btn onClick={() => start.mutate()}>Set up authenticator</Btn></div>}
        {setup && (
          <div className="space-y-2 text-sm">
            <p>1. Add this key to your authenticator app (choose “enter a setup key”):</p><code className="block break-all rounded bg-slate-100 p-2 dark:bg-slate-900">{setup.secret}</code>
            <p className="text-xs text-slate-500">Or open this link on the device: <a className="break-all underline" href={setup.otpauth_uri}>{setup.otpauth_uri}</a></p>
            <Field label="2. Enter the 6-digit code it shows"><input className={inputCls} aria-label="Confirmation code" value={code} onChange={(e) => setCode(e.target.value)} /></Field>
            <Btn onClick={() => enable.mutate()} disabled={code.trim().length < 6}>Switch on</Btn>
          </div>)}
        {codes && <div role="status" className="space-y-1 rounded border border-emerald-500 bg-emerald-50 p-3 text-sm text-emerald-900"><b>Two-factor is on. Keep these recovery codes somewhere safe: each works once and they are not shown again.</b><div className="grid grid-cols-2 gap-1 font-mono">{codes.map((c) => <span key={c}>{c}</span>)}</div></div>}
        {(start.error || enable.error || disable.error) && <p role="alert" className="mt-2 text-sm text-red-600">{String(start.error ?? enable.error ?? disable.error).replace("Error: ", "")}</p>}
        {!setup && <div className="mt-4 flex items-end gap-2 border-t border-slate-200 pt-3 dark:border-slate-700"><Field label="Switch off (needs a current code)"><input className={inputCls} aria-label="Code to switch off" value={code} onChange={(e) => setCode(e.target.value)} /></Field><Btn kind="danger" onClick={() => disable.mutate()} disabled={code.trim().length < 6}>Switch off</Btn></div>}
      </Card>
    </div>
  );
}
