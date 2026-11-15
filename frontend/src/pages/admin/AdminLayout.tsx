import { useQuery } from "@tanstack/react-query";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { api } from "../../lib";

// path, tab label, page title, subtitle, group. Three groups so the bar reads as "how documents are read", "what the rules are", "how the system runs".
const TABS: [string, string, string, string, string][] = [
  ["/admin", "Pipeline", "Sources, pipeline and engine", "Where contracts come from, what each run did, and which engine reads them", "Reading"],
  ["/admin/clauses", "Key clauses", "Key clause library", "What clauses to identify, and where each one is required", "Reading"],
  ["/admin/values", "Values", "Values and limits", "Numbers pulled from contracts, and how they are read", "Reading"],
  ["/admin/quality", "Quality", "Extraction quality", "Corrections, measured accuracy and the review sheet", "Reading"],
  ["/admin/checklist", "Checklist", "Redline checklist", "Rules every draft is checked against before signing", "Rules"],
  ["/admin/thresholds", "Thresholds", "Thresholds", "Spend checks, risk points and SLA credits", "Rules"],
  ["/admin/risk", "Risk weights", "Risk weights", "How the vendor risk score is weighted", "Rules"],
  ["/admin/obligations", "Obligations", "Obligation rules", "Which values become tracked duties", "Rules"],
  ["/admin/approvals", "Approvals", "Approval rules", "Who must approve which drafts, in order", "Rules"],
  ["/admin/alerts", "Alerts", "Alert rules and channels", "When to raise an alert and where it is sent", "Rules"],
  ["/admin/connectors", "Connectors", "Connectors", "Google Drive, OneDrive, SharePoint, mailbox and procurement systems", "System"],
  ["/admin/access", "Access and audit", "Access and audit", "Roles, API tokens and who changed what", "System"],
  ["/admin/usage", "AI usage", "AI usage", "Calls, tokens and cost", "System"],
];
const GROUPS = ["Reading", "Rules", "System"];

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
      <nav className="flex flex-wrap items-end gap-x-6 gap-y-2 border-b border-line pb-px dark:border-slate-700" aria-label="Admin sections">
        {GROUPS.map((g) => (
          <div key={g} role="group" aria-label={g} className="flex flex-col">
            <span className="px-3 text-[11px] font-semibold uppercase tracking-wider text-ink-mute dark:text-slate-500">{g}</span>
            <div className="flex flex-wrap">
              {TABS.filter((t) => t[4] === g).map(([to, label, , sub]) => (
                <NavLink key={to} to={to} end={to === "/admin"} title={sub}
                  className={({ isActive }) => `-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium ${isActive ? "border-indigo-600 text-indigo-700 dark:text-indigo-300" : "border-transparent text-slate-600 hover:text-slate-900 dark:text-slate-300 dark:hover:text-white"}`}>
                  {label}
                </NavLink>))}
            </div>
          </div>))}
      </nav>
      <Outlet />
    </div>
  );
}
