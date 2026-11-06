import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import "./index.css";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const qc = new QueryClient();

function App() {
  const { data, error, isLoading } = useQuery({
    queryKey: ["health"],
    queryFn: async () => {
      const r = await fetch(`${API}/health`);
      if (!r.ok) throw new Error(String(r.status));
      return r.json() as Promise<{ status: string; db: string; pgvector: string }>;
    },
  });
  return (
    <main className="mx-auto max-w-3xl p-8">
      <h1 className="text-2xl font-semibold">ContractIQ</h1>
      <p className="mt-2 text-sm text-slate-500">Vendor contract intelligence for VMOs (POC scaffold)</p>
      <p className="mt-6 text-sm">
        API:{" "}
        {isLoading ? "checking…" : error ? "unreachable ✗" : `${data?.status} (db ${data?.db}, pgvector ${data?.pgvector}) ✓`}
      </p>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode><QueryClientProvider client={qc}><App /></QueryClientProvider></React.StrictMode>
);
