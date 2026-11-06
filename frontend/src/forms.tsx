import { ReactNode } from "react";

export const inputCls =
  "rounded border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-600 dark:bg-slate-800";
export const DOC_TYPES = ["MSA", "SOW", "Work Order", "NDA", "SaaS", "DPA", "Amendment"];

export function Btn({
  children, onClick, kind = "primary", disabled, type = "button", title,
}: { children: ReactNode; onClick?: () => void; kind?: "primary" | "ghost" | "danger"; disabled?: boolean; type?: "button" | "submit"; title?: string }) {
  const cls =
    kind === "primary" ? "bg-indigo-600 text-white hover:bg-indigo-700"
    : kind === "danger" ? "border border-red-400 text-red-700 hover:bg-red-50 dark:text-red-300 dark:hover:bg-red-950"
    : "border border-slate-300 hover:bg-slate-100 dark:border-slate-600 dark:hover:bg-slate-700";
  return (
    <button type={type} title={title} disabled={disabled} onClick={onClick} className={`rounded px-3 py-1.5 text-sm font-medium disabled:opacity-50 ${cls}`}>
      {children}
    </button>
  );
}

export function Field({ label, hint, children, className = "" }: { label: string; hint?: string; children: ReactNode; className?: string }) {
  return (
    <label className={`flex flex-col gap-1 text-sm ${className}`}>
      <span className="font-medium">{label}</span>
      {children}
      {hint && <span className="text-xs text-slate-500">{hint}</span>}
    </label>
  );
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button type="button" role="switch" aria-checked={checked} aria-label={label} onClick={() => onChange(!checked)}
      className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition ${checked ? "bg-indigo-600" : "bg-slate-300 dark:bg-slate-600"}`}>
      <span className={`inline-block h-4 w-4 rounded-full bg-white transition ${checked ? "translate-x-4" : "translate-x-0.5"}`} />
    </button>
  );
}

export const csv = (s: string): string[] => s.split(",").map((x) => x.trim()).filter(Boolean);
