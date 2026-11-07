import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import "./index.css";
import { api } from "./lib";
import { Layout } from "./ui";
import Dashboard from "./pages/Dashboard";
import Contracts from "./pages/Contracts";
import ContractDetail from "./pages/ContractDetail";
import Ask from "./pages/Ask";
import Redline from "./pages/Redline";
import Templates from "./pages/Templates";
import Clauses from "./pages/Clauses";
import Vendors from "./pages/Vendors";
import VendorProfile from "./pages/VendorProfile";
import NewContract from "./pages/NewContract";
import DocumentEditor from "./pages/DocumentEditor";
import Obligations from "./pages/Obligations";
import Spend from "./pages/Spend";
import Risk from "./pages/Risk";
import Alerts from "./pages/Alerts";
import AlertSettings from "./pages/admin/AlertSettings";
import Access from "./pages/admin/Access";
import Quality from "./pages/admin/Quality";
import ApprovalRules from "./pages/admin/ApprovalRules";
import Login from "./pages/Login";
import SharedDoc from "./pages/Shared";
import Sign from "./pages/Sign";
import RiskWeights from "./pages/admin/RiskWeights";
import Connectors from "./pages/admin/Connectors";
import Thresholds from "./pages/admin/Thresholds";
import ObligationRules from "./pages/admin/ObligationRules";
import AdminLayout from "./pages/admin/AdminLayout";
import Pipeline from "./pages/admin/Pipeline";
import Kcc from "./pages/admin/Kcc";
import Values from "./pages/admin/Values";
import Checklist from "./pages/admin/Checklist";
import Usage from "./pages/admin/Usage";

const qc = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1, staleTime: 5000 } } });

/** AUTH_MODE=off (demo): straight in. AUTH_MODE=on: sign in (or create the first administrator) first. */
function Gate({ children }: { children: React.ReactNode }) {
  const [n, setN] = React.useState(0);
  const cfg = useQuery({ queryKey: ["auth-config", n], queryFn: () => api<{ auth_required: boolean; needs_bootstrap: boolean }>("/api/auth/config"), staleTime: 0 });
  const me = useQuery({ queryKey: ["me", n], queryFn: () => api<{ email: string }>("/api/auth/me"), enabled: !!cfg.data?.auth_required, retry: false, staleTime: 0 });
  React.useEffect(() => { const f = () => setN((x) => x + 1); window.addEventListener("ciq-signed-out", f); return () => window.removeEventListener("ciq-signed-out", f); }, []);
  if ((window.location.pathname.startsWith("/shared/") || window.location.pathname.startsWith("/sign/"))) return <>{children}</>;      // a share link is its own credential
  if (!cfg.data) return <div className="p-8 text-sm text-slate-500">Loading…</div>;
  if (cfg.data.auth_required && (me.isLoading || me.isError)) return me.isLoading ? <div className="p-8 text-sm text-slate-500">Loading…</div> : <Login bootstrap={cfg.data.needs_bootstrap} onDone={() => { qc.clear(); setN((x) => x + 1); }} />;
  return <>{children}</>;
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <Gate>
      <BrowserRouter>
        <Routes>
          <Route path="shared/:token" element={<SharedDoc />} />
          <Route path="sign/:token" element={<Sign />} />
          <Route element={<Layout />}>
            <Route index element={<Dashboard />} />
            <Route path="contracts" element={<Contracts />} />
            <Route path="contracts/:id" element={<ContractDetail />} />
            <Route path="vendors" element={<Vendors />} />
            <Route path="vendors/:name" element={<VendorProfile />} />
            <Route path="clauses" element={<Clauses />} />
            <Route path="ask" element={<Ask />} />
            <Route path="redline" element={<Redline />} />
            <Route path="redline/:id" element={<Redline />} />
            <Route path="templates" element={<Templates />} />
            <Route path="new" element={<NewContract />} />
            <Route path="obligations" element={<Obligations />} />
            <Route path="spend" element={<Spend />} />
            <Route path="risk" element={<Risk />} />
            <Route path="alerts" element={<Alerts />} />
            <Route path="documents/:id/edit" element={<DocumentEditor />} />
            <Route path="admin" element={<AdminLayout />}>
              <Route index element={<Pipeline />} />
              <Route path="clauses" element={<Kcc />} />
              <Route path="values" element={<Values />} />
              <Route path="checklist" element={<Checklist />} />
              <Route path="risk" element={<RiskWeights />} />
              <Route path="connectors" element={<Connectors />} />
              <Route path="alerts" element={<AlertSettings />} />
              <Route path="thresholds" element={<Thresholds />} />
              <Route path="obligations" element={<ObligationRules />} />
              <Route path="access" element={<Access />} />
              <Route path="quality" element={<Quality />} />
              <Route path="approvals" element={<ApprovalRules />} />
              <Route path="usage" element={<Usage />} />
            </Route>
          </Route>
        </Routes>
      </BrowserRouter>
      </Gate>
    </QueryClientProvider>
  </React.StrictMode>
);
