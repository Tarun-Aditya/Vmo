import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Btn, Field, inputCls } from "../forms";
import { api, setToken } from "../lib";

export default function Login({ bootstrap, onDone }: { bootstrap: boolean; onDone: () => void }) {
  const [f, setF] = useState({ email: "", password: "", name: "", code: "" });
  const go = useMutation({
    mutationFn: () => api<{ token: string }>(bootstrap ? "/api/auth/bootstrap" : "/api/auth/login", { method: "POST", body: JSON.stringify(f) }),
    onSuccess: (r) => { setToken(r.token); onDone(); },
  });
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 p-4 dark:bg-slate-900">
      <form className="w-full max-w-sm space-y-4 rounded-lg border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-800" onSubmit={(e) => { e.preventDefault(); go.mutate(); }}>
        <div><div className="text-xl font-bold tracking-tight">Contract<span className="text-indigo-600">IQ</span></div>
          <p className="text-sm text-slate-500">{bootstrap ? "First start: create the administrator account." : "Sign in to continue."}</p></div>
        {bootstrap && <Field label="Name"><input className={inputCls} aria-label="Name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>}
        <Field label="E-mail"><input className={inputCls} type="email" autoComplete="username" aria-label="E-mail" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
        <Field label="Password" hint={bootstrap ? "At least 10 characters, not containing your e-mail name." : undefined}><input className={inputCls} type="password" autoComplete={bootstrap ? "new-password" : "current-password"} aria-label="Password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></Field>
        {!bootstrap && (go.error?.message?.includes("6-digit") || f.code) && <Field label="Authenticator code (or recovery code)"><input className={inputCls} autoComplete="one-time-code" aria-label="Authenticator code" value={f.code} onChange={(e) => setF({ ...f, code: e.target.value })} /></Field>}
        {go.error && <p role="alert" className="text-sm text-red-600">{String(go.error).replace("Error: ", "")}</p>}
        <Btn type="submit" disabled={!f.email || !f.password || go.isPending}>{bootstrap ? "Create administrator" : "Sign in"}</Btn>
      </form>
    </div>
  );
}
