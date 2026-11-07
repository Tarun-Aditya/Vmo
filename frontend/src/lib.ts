import { useEffect, useState } from "react";

export const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export const TOKEN_KEY = "ciq_token";
export const getToken = (): string | null => { try { return localStorage.getItem(TOKEN_KEY); } catch { return null; } };
export const setToken = (t: string | null) => { try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY); } catch { /* private mode */ } };
/** Download / open links cannot send headers: the token travels as a query parameter instead. */
export const authUrl = (path: string) => { const t = getToken(); return `${API}${path}${t ? `${path.includes("?") ? "&" : "?"}access_token=${encodeURIComponent(t)}` : ""}`; };

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const tok = getToken();
  const r = await fetch(`${API}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(tok ? { Authorization: `Bearer ${tok}` } : {}), ...(init?.headers ?? {}) },
  });
  if (r.status === 401 && tok) { setToken(null); window.dispatchEvent(new Event("ciq-signed-out")); }
  if (!r.ok) {
    const body = await r.text();
    let msg = body;
    try {
      const j = JSON.parse(body);
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j);
    } catch {
      /* plain text */
    }
    throw new Error(msg || String(r.status));
  }
  return r.json();
}

/** US dollars: $4.80M, $540K, $48,000. */
export function usd(n: number | string | null | undefined): string {
  if (n === null || n === undefined || n === "") return "—";
  const v = Number(n);
  if (v >= 1e6) return "$" + (v / 1e6).toFixed(2) + "M";
  if (v >= 1e3) return "$" + (v / 1e3).toFixed(v % 1e3 === 0 ? 0 : 1) + "K";
  return "$" + v.toLocaleString("en-US");
}

export const fmtDate = (d?: string | null) =>
  d ? new Date(d + "T00:00:00").toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }) : "—";

export function daysLabel(n: number): string {
  if (n < 0) return `${-n}d overdue`;
  if (n === 0) return "today";
  return `in ${n}d`;
}

/** Persisted boolean setting shared across components via a storage event. */
export function useSetting(key: string, initial: boolean): [boolean, (v: boolean) => void] {
  const read = () => {
    try { const v = localStorage.getItem(key); return v === null ? initial : v === "1"; } catch { return initial; }
  };
  const [val, setVal] = useState(read);
  useEffect(() => {
    const h = () => setVal(read());
    window.addEventListener("setting-changed", h);
    return () => window.removeEventListener("setting-changed", h);
  }, []);
  return [val, (v: boolean) => {
    try { localStorage.setItem(key, v ? "1" : "0"); } catch { /* ignore */ }
    window.dispatchEvent(new Event("setting-changed"));
    setVal(v);
  }];
}

export type Col = { key: string; label: string; kind: "text" | "date" | "money" | "bool" | "number" | "score" | "quote" | "severity" };
export type Table = { title: string | null; kv?: boolean; columns: Col[]; rows: Record<string, unknown>[]; row_count: number };
export type Step = { title: string; detail?: string; sql?: string; columns?: string[]; rows?: unknown[][]; row_count?: number; error?: string };

export const when = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "—";

export function ago(iso?: string | null): string {
  if (!iso) return "never";
  const m = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  return m < 1 ? "just now" : m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} d ago`;
}

export function inFuture(iso?: string | null): string {
  if (!iso) return "—";
  const m = Math.round((new Date(iso).getTime() - Date.now()) / 60000);
  return m <= 0 ? "due now" : m < 60 ? `in ${m} min` : m < 1440 ? `in ${Math.floor(m / 60)} h ${m % 60} min` : `in ${Math.round(m / 1440)} d`;
}

export type Status = {
  running: boolean;
  config: { enabled: boolean; interval_minutes: number; last_run_at: string | null; next_run_at: string | null };
  last_run: { id: number; status: string; trigger: string; new_docs: number; updated: number; failed: number } | null;
  documents: Record<string, number>;
};
