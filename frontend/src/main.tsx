import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import "./index.css";
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
import RiskWeights from "./pages/admin/RiskWeights";
import Connectors from "./pages/admin/Connectors";
import AdminLayout from "./pages/admin/AdminLayout";
import Pipeline from "./pages/admin/Pipeline";
import Kcc from "./pages/admin/Kcc";
import Values from "./pages/admin/Values";
import Checklist from "./pages/admin/Checklist";
import Usage from "./pages/admin/Usage";

const qc = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1, staleTime: 5000 } } });

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Routes>
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
            <Route path="documents/:id/edit" element={<DocumentEditor />} />
            <Route path="admin" element={<AdminLayout />}>
              <Route index element={<Pipeline />} />
              <Route path="clauses" element={<Kcc />} />
              <Route path="values" element={<Values />} />
              <Route path="checklist" element={<Checklist />} />
              <Route path="risk" element={<RiskWeights />} />
              <Route path="connectors" element={<Connectors />} />
              <Route path="usage" element={<Usage />} />
            </Route>
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);
