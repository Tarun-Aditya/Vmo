import { useQuery } from "@tanstack/react-query";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { api } from "../../lib";

const TABS: [string, string, string, string][] = [   // path, tab label, page title, subtitle
  ["/admin", "Pipeline", "Sources, pipeline and engine", "Where contracts come from, what each run did, and which engine reads them"],
  ["/admin/clauses", "Key clauses", "Key clause library", "What clauses to identify, and where each one is required"],
  ["/admin/values", "Values", "Values and limits", "Numbers pulled from contracts, and how they are read"],
  ["/admin/checklist", "Checklist", "Redline checklist", "Rules every draft is checked against before signing"],
  ["/admin/thresholds", "Thresholds", "Thresholds", "Spend checks, risk points and SLA credits"],
  ["/admin/risk", "Risk weights", "Risk weights", "How the vendor risk score is weighted"],
  ["/admin/obligations", "Obligation rules", "Obligation rules", "Which values become tracked duties"],
  ["/admin/connectors", "Connectors", "Connectors", "Google Drive, OneDrive, SharePoint, mailbox and procurement systems"],
  ["/admin/alerts", "Alerts", "Alert rules and channels", "When to raise an alert and where it is sent"],
  ["/admin/approvals", "Approvals", "Approval rules", "Who must approve which drafts, in order"],
  ["/admin/access", "Access and audit", "Access and audit", "Roles, API tokens and who changed what"],
  ["/admin/quality", "Quality", "Extraction quality", "Corrections, measured accuracy and the review sheet"],
  ["/admin/usage", "Usage", "AI usage", "Calls, tokens and cost"],
];

export default function AdminLayout() {
  const loc = useLocation();
  const cur = TABS.find(([to]) => (to === "/admin" ? loc.pathname.replace(/\/$/, "") === "/admin" : loc.pathname.startsWith(to))) ?? TABS[0];
  const who = useQuery({ queryKey: ["whoami"], queryFn: () => api<{ role: string; auth_required: boolean }>("/api/auth/me") });
  if (who.data && who.data.role !== "admin")
    return <div className="rounded-lg border border-amber-400 bg-amber-50 p-4 text-sm text-amber-900" role="alert"><b>Admin only.</b> Your role is {who.data.role}; configuration, connectors, users and the audit log need the admin role.</div>;
  return (
    <div className="space-y-4">
      <div>
        <h1>{cur[2]}</h1>
        <p className="mt-1 text-sm text-slate-500">{cur[3]}</p>
      </div>
      <nav className="flex flex-wrap gap-x-1 border-b border-line dark:border-slate-700" aria-label="Admin sections">
        {TABS.map(([to, label, , sub]) => (
          <NavLink key={to} to={to} end={to === "/admin"} title={sub}
            className={({ isActive }) => `-mb-px border-b-2 px-3 py-2 text-sm font-medium ${isActive ? "border-indigo-600 text-indigo-700 dark:text-indigo-300" : "border-transparent text-slate-600 hover:text-slate-900 dark:text-slate-300"}`}>
            {label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </div>
  );
}
