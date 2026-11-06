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
import Admin from "./pages/Admin";
import Clauses from "./pages/Clauses";
import Vendors from "./pages/Vendors";
import VendorProfile from "./pages/VendorProfile";

const qc = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1 } } });

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
            <Route path="templates" element={<Templates />} />
            <Route path="admin" element={<Admin />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);
