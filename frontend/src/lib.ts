import { useEffect, useState } from "react";

export const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

/** ₹ in lakh / crore. */
export function inr(n: number | string | null | undefined): string {
  if (n === null || n === undefined || n === "") return "—";
  const v = Number(n);
  if (v >= 1e7) return `₹${(v / 1e7).toFixed(2)} Cr`;
  if (v >= 1e5) return `₹${(v / 1e5).toFixed(1)} L`;
  return `₹${v.toLocaleString("en-IN")}`;
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

export type Col = { key: string; label: string; kind: "text" | "date" | "money" | "bool" | "number" | "score" | "quote" };
export type Table = { title: string | null; columns: Col[]; rows: Record<string, unknown>[]; row_count: number };
export type Step = { title: string; detail?: string; sql?: string; columns?: string[]; rows?: unknown[][]; row_count?: number; error?: string };
