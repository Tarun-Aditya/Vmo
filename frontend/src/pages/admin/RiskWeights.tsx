import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Btn, Toggle, inputCls } from "../../forms";
import { api } from "../../lib";
import { Card, Loading } from "../../ui";

type W = { key: string; label: string; description: string; weight: number; enabled: boolean };

export default function RiskWeights() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["risk"], queryFn: () => api<{ weights: W[] }>("/api/risk/vendors") });
  const [ws, setWs] = useState<W[]>([]);
  useEffect(() => { if (q.data) setWs(q.data.weights); }, [q.data]);
  const save = useMutation({ mutationFn: () => api("/api/admin/risk-weights", { method: "PUT", body: JSON.stringify(ws.map(({ key, weight, enabled }) => ({ key, weight, enabled }))) }), onSuccess: () => qc.invalidateQueries() });
  if (!q.data) return <Loading q={q} />;
  const total = ws.filter((w) => w.enabled).reduce((a, w) => a + Number(w.weight), 0) || 1;
  return (
    <Card title="Vendor risk scoring">
      <p className="mb-3 text-sm text-slate-500">A vendor's score is the weighted average of these components (each 0–100). Tiers: critical ≥ 50, high ≥ 30, medium ≥ 15. Saving recomputes every vendor.</p>
      <table className="w-full text-sm" aria-label="Risk weights">
        <thead><tr className="text-left text-xs uppercase text-slate-500"><th className="py-1">Component</th><th>What counts</th><th className="w-28">Weight</th><th className="w-20 text-right">Share</th><th className="w-16">On</th></tr></thead>
        <tbody>
          {ws.map((w, i) => (
            <tr key={w.key} className="border-t border-slate-100 align-top dark:border-slate-700">
              <td className="py-2 font-medium">{w.label}</td><td className="py-2 pr-4 text-slate-600 dark:text-slate-300">{w.description}</td>
              <td className="py-2"><input className={`${inputCls} w-24`} type="number" min={0} max={100} aria-label={`${w.label} weight`} value={w.weight} onChange={(e) => setWs(ws.map((x, j) => (j === i ? { ...x, weight: Number(e.target.value) } : x)))} /></td>
              <td className="py-2 text-right tabular-nums">{w.enabled ? `${Math.round((Number(w.weight) / total) * 100)}%` : "—"}</td>
              <td className="py-2"><Toggle checked={w.enabled} label={`${w.label} enabled`} onChange={(v) => setWs(ws.map((x, j) => (j === i ? { ...x, enabled: v } : x)))} /></td>
            </tr>))}
        </tbody>
      </table>
      <div className="mt-3 flex items-center gap-3"><Btn onClick={() => save.mutate()} disabled={save.isPending}>{save.isPending ? "Recomputing…" : "Save & recompute"}</Btn>{save.isSuccess && <span className="text-sm text-emerald-700 dark:text-emerald-400">✓ Scores updated.</span>}{save.error && <span className="text-sm text-red-600">{String(save.error)}</span>}</div>
    </Card>
  );
}
