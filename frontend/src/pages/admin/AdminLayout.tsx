import { NavLink, Outlet } from "react-router-dom";

const TABS: [string, string, string][] = [
  ["/admin", "Pipeline", "Folder watch, schedule, run history"],
  ["/admin/connectors", "Connectors", "Google Drive, OneDrive, SharePoint"],
  ["/admin/alerts", "Alerts", "Rules and e-mail / Slack / Teams / webhook channels"],
  ["/admin/clauses", "Key clause library", "What clauses to identify"],
  ["/admin/values", "Values & limits", "What numbers to extract"],
  ["/admin/checklist", "Redline checklist", "Rules to run before signing"],
  ["/admin/obligations", "Obligation rules", "Which values become tracked duties"],
  ["/admin/thresholds", "Thresholds", "Spend checks, risk points, SLA credits"],
  ["/admin/risk", "Risk scoring", "Weights of the vendor risk score"],
  ["/admin/usage", "AI usage", "Calls, tokens, cost"],
];

export default function AdminLayout() {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Admin</h1>
        <p className="text-sm text-slate-500">Configure what the platform identifies, extracts and checks. Changes re-run over every document and update all screens.</p>
      </div>
      <nav className="flex flex-wrap gap-1 border-b border-slate-200 dark:border-slate-700" aria-label="Admin sections">
        {TABS.map(([to, label, sub]) => (
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
