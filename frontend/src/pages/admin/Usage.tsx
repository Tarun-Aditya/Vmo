import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib";
import { Card, Loading, Td, Th } from "../../ui";

type U = { rows: { purpose: string; model: string; calls: number; input_tokens: number; output_tokens: number; avg_latency_ms: number; est_cost_usd: number }[];
  total_calls: number; total_input_tokens: number; total_output_tokens: number; est_cost_usd: number; price_note: string; llm_available: boolean };

const n = (v: number) => Number(v).toLocaleString("en-US");
const usd2 = (v: number) => "$" + Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const secs = (ms: number) => (Number(ms) >= 1000 ? `${(Number(ms) / 1000).toFixed(1)} s` : `${Math.round(Number(ms))} ms`);

/** What Claude has been used for, and roughly what it cost. */
export default function Usage() {
  const q = useQuery({ queryKey: ["usage"], queryFn: () => api<U>("/api/admin/usage") });
  if (!q.data) return <Loading q={q} />;
  const u = q.data;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {([["Claude calls", n(u.total_calls)], ["Input tokens", n(u.total_input_tokens)], ["Output tokens", n(u.total_output_tokens)], ["Estimated cost", usd2(u.est_cost_usd)]] as [string, string][]).map(([l, v]) => (
          <Card key={l}><div className="text-xs font-semibold uppercase tracking-wider text-ink-mute dark:text-slate-400">{l}</div><div className="mt-1 font-serif text-3xl tabular-nums">{v}</div></Card>))}
      </div>
      <Card title="By purpose">
        {u.rows.length === 0 ? <p className="text-sm text-slate-500">No Claude calls logged yet{u.llm_available ? "." : ": the application is running on the offline engine."}</p> : (
          <div className="overflow-x-auto"><table className="w-full text-sm">
            <thead><tr><Th>Purpose</Th><Th>Model</Th><Th className="text-right">Calls</Th><Th className="text-right">Tokens in</Th><Th className="text-right">Tokens out</Th><Th className="text-right">Average time</Th><Th className="text-right">Estimated cost</Th></tr></thead>
            <tbody>{u.rows.map((r) => (
              <tr key={r.purpose + r.model} className="border-t border-slate-100 dark:border-slate-700">
                <Td>{r.purpose}</Td><Td className="font-mono text-xs">{r.model}</Td><Td className="text-right tabular-nums">{n(r.calls)}</Td>
                <Td className="text-right tabular-nums">{n(r.input_tokens)}</Td><Td className="text-right tabular-nums">{n(r.output_tokens)}</Td>
                <Td className="text-right tabular-nums">{secs(r.avg_latency_ms)}</Td><Td className="text-right tabular-nums">{usd2(r.est_cost_usd)}</Td>
              </tr>))}</tbody>
          </table></div>)}
        <p className="mt-2 text-xs text-slate-500">{u.price_note}. Calls made through a Claude subscription are not billed per token; the estimate shows what the same work would cost on the API.</p>
      </Card>
    </div>
  );
}
