import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { API, api, getToken } from "../lib";

export type Presence = { name: string; editing: boolean };

/** The live channel of one document: who is here, and pushes when a version is saved or comments / suggestions change. */
export function useCollab(docId: string, currentVersion: number | undefined) {
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ["whoami"], queryFn: () => api<{ email: string; name?: string }>("/api/auth/me") });
  const [users, setUsers] = useState<Presence[]>([]);
  const [newer, setNewer] = useState<{ version: number; by: string } | null>(null);
  const ws = useRef<WebSocket | null>(null);
  const ver = useRef(currentVersion);
  ver.current = currentVersion;
  const name = me.data?.name || me.data?.email || "Guest";
  useEffect(() => {
    if (!me.data) return;
    let closed = false, timer: number | undefined;
    const connect = () => {
      const tok = getToken();
      const s = new WebSocket(`${API.replace(/^http/, "ws")}/ws/documents/${docId}?name=${encodeURIComponent(name)}${tok ? `&access_token=${encodeURIComponent(tok)}` : ""}`);
      ws.current = s;
      s.onmessage = (e) => {
        const m = JSON.parse(e.data);
        if (m.type === "presence") setUsers(m.users);
        else if (m.type === "threads") qc.invalidateQueries({ queryKey: ["threads"] });
        else if (m.type === "version" && (ver.current ?? 0) < m.version) { setNewer({ version: m.version, by: m.by }); qc.invalidateQueries({ queryKey: ["threads"] }); }
      };
      s.onclose = () => { if (!closed) timer = window.setTimeout(connect, 3000); };
    };
    connect();
    return () => { closed = true; window.clearTimeout(timer); ws.current?.close(); };
  }, [docId, me.data, name, qc]);
  const setEditing = (on: boolean) => ws.current?.readyState === 1 && ws.current.send(JSON.stringify({ type: "editing", on }));
  return { users, newer, dismiss: () => setNewer(null), setEditing, name };
}
