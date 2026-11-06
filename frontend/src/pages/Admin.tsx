import { useQuery } from "@tanstack/react-query";
import { api } from "../lib";
import { Card, Loading, Td, Th } from "../ui";

type U = { rows: { purpose: string; model: string; calls: number; input_tokens: number; output_tokens: number; avg_latency_ms: number; est_cost_usd: number }[];
  total_calls: number; total_input_tokens: number; total_output_tokens: number; est_cost_usd: number; price_note: string; llm_available: boolean };

export default function Admin() {
  const q = useQuery({ queryKey: ["usage"], queryFn: () => api<U>("/api/admin/usage") });
  if (!q.data) return <Loading q={q} />;
  const u = q.data;
  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <h1 className="text-xl font-semibold">AI usage</h1>
      <div className="grid grid-cols-4 gap-4">
        {[["LLM calls", u.total_calls], ["Input tokens", u.total_input_tokens.toLocaleString()], ["Output tokens", u.total_output_tokens.toLocaleString()], ["Est. cost", `$${u.est_cost_usd}`]].map(([l, v]) => (
          <Card key={String(l)}><div className="text-xs uppercase text-slate-500">{l}</div><div className="text-2xl font-semibold tabular-nums">{v}</div></Card>))}
      </div>
      <Card title="By purpose">
        {u.rows.length === 0 ? <p className="text-sm text-slate-500">No LLM calls logged yet{u.llm_available ? "." : " — running on the offline engine (no ANTHROPIC_API_KEY)."}</p> : (
          <table className="w-full text-sm"><thead><tr><Th>Purpose</Th><Th>Model</Th><Th>Calls</Th><Th>In</Th><Th>Out</Th><Th>Avg ms</Th><Th>Est. $</Th></tr></thead>
            <tbody>{u.rows.map((r) => <tr key={r.purpose + r.model} className="border-t border-slate-100 dark:border-slate-700"><Td>{r.purpose}</Td><Td>{r.model}</Td><Td>{r.calls}</Td><Td>{r.input_tokens}</Td><Td>{r.output_tokens}</Td><Td>{r.avg_latency_ms}</Td><Td>{r.est_cost_usd}</Td></tr>)}</tbody></table>)}
        <p className="mt-2 text-xs text-slate-500">{u.price_note}</p>
      </Card>
    </div>
  );
}
