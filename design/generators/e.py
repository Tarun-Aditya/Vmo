from lib import *
import json
rows=[("Portfolio dashboard","Main","Drawn","KPIs, decision queue, 12-month expiry chart, 30/60/90 table, vendor operations"),
("Portfolio map (bird's-eye hierarchy)","Map","Drawn","All families: parent, SOWs, amendments on one timeline; expiry and notice markers; hierarchy problems and missing dates"),
("Contracts list","Contracts","Drawn","Filters, quick flags, signatures, pagination"),
("Contract detail","Contract","Drawn","Panels drawn; missing: correct-a-field dialog, inherited-term and set-by columns, send-for-signature and approval panels, share dialog"),
("Vendors","Vendors","Drawn","Ranked table with risk, deviations, flags"),
("Vendor profile","VendorProfile","Drawn","Hierarchy, differences from templates, key dates, ask-about-vendor"),
("Key clauses matrix","Clauses","Drawn","Matrix and gaps; adding clauses moved to Admin; drafts group and hover card are sketched only"),
("Ask","Ask","Drawn","History, scope, reasoning toggle drawn"),
("Review / redline","Review","Drawn","Missing: queue filter, assignee, due date, review status and note, previous/next document, approval decision, DOCX export"),
("Document editor","DocumentEditor","Drawn","Drawn as Word-style; missing: version-note dialog, suggest-a-change dialog, share dialog, guest cursor states"),
("Template library","Templates","Drawn","Clause by clause, coverage, deviation heatmap"),
("New contract","NewContract","Drawn","Upload details, form, draft created, checklist"),
("Obligations and SLAs","Obligations","Drawn","List, filters, actual-vs-contract chart, add measurement"),
("Spend","Spend","Drawn","Missing: exception-type filter, term and at-risk columns"),
("Risk and benchmarks","Risk","Drawn","Scorecards, liability and governing-law benchmarks"),
("Alerts","Alerts","Drawn","Missing: alert status controls and assignment"),
("Shared guest view","Shared","Drawn","Link view, comments, findings"),
("Signing page","Sign","Drawn","Type-to-sign, agree, decline"),
("Sign in, SSO, MFA","Login","Drawn","Sign-in, SSO, authenticator code"),
("My security","Security","Drawn","Two-factor setup and switch-off"),
("Admin: Pipeline","System","Drawn","Missing: pipelines table (folders watched, frequency, when to run), add a document to the folder, run table columns"),
("Admin: Key clauses","AdminClauses","Drawn","Library table and editor"),
("Admin: Values","AdminValues","Drawn","Missing: editor fields (from clause, description, which way is good)"),
("Admin: Checklist","AdminChecklist","Drawn","Missing: rule editor (rule type, forbidden wording, suggested replacement wording)"),
("Admin: Thresholds","AdminThresholds","Drawn","Settings"),
("Admin: Risk weights","AdminRisk","Drawn","Weights"),
("Admin: Obligation rules","AdminObligations","Drawn","Missing: rule editor fields (frequency, metric, title template)"),
("Admin: Data inputs","AdminData","Drawn","CSV feeds, SLA measurements, document uploads: all additions live in Admin"),
("Admin: Connectors","AdminConnectors","Drawn","List and add form, simulators labelled"),
("Admin: Alerts","AdminAlerts","Drawn","Missing: channel editor (type, send-from severity) forms"),
("Admin: Approvals","AdminApprovals","Drawn","Missing: rule editor (document types, minimum value, minimum severity, approver e-mails, reminders)"),
("Admin: Access and audit","AdminAccess","Drawn","Missing: new-user form, token creation, clear lockout and reset two-factor"),
("Admin: Quality","AdminQuality","Drawn","Agreement, corrections"),
("Dialogs and panels","Dialogs","Drawn","Share, send for signature, approval decision, correct a field, version note, suggest a change, comment thread, reset access"),
("States","States","Drawn","Empty, loading, error, no permission, expired link, Claude paused, no results, session expired"),
("Dark theme","Dark","Drawn","Portfolio home in dark"),
("Phone layouts","Mobile","Drawn","Home, contract, Ask at 390 px"),
("Admin: Usage","AdminUsage","Drawn","AI usage and cost")]
dr=sum(1 for r in rows if r[2]=="Drawn"); pa=sum(1 for r in rows if r[2]=="Partly"); nd=len(rows)-dr-pa
tr=[(f'<a href="{b}.dc.html" style="color:#0E6B5E;font-weight:600;text-decoration:none">{a}</a>' if b!='(none)' else a,chip('ok','Drawn') if s=='Drawn' else (chip('med','Partly') if s=='Partly' else chip('crit','Not drawn')),n) for a,b,s,n in rows]
body=f'<div style="padding:32px 40px;max-width:1440px"><h1 class="serif" style="margin:0 0 6px;font-size:36px;font-weight:400">Redesign coverage of the application</h1><p class="mute" style="max-width:780px">Every screen group in the product now has a board. {dr} are drawn in full, {pa} are drawn but missing forms, dialogs or states, {nd} has no board. Phone layouts and the dark theme are described, not drawn.</p><div style="display:flex;gap:16px;margin:16px 0 20px;flex-wrap:wrap">{kpi("Screen groups",str(len(rows)))}{kpi("Drawn",str(dr))}{kpi("Partly",str(pa),"forms or states missing","warn")}{kpi("No board",str(nd),"","crit")}</div><div class="card">{tbl(["Screen","Status","What is on the board"],tr)}</div></div>'
page('Audit','Redesign coverage','',body,2100,bare=True)
# canvas layout
c=json.load(open(ROOT+'canvas.json'))
order=['Audit']+[b for _,b,_,_ in rows if b!='(none)']
H={}
import re
for b in order:
    s=open(ROOT+b+'.dc.html').read()
    m=re.search(r'"height":(\d+)',s); H[b]=int(m.group(1))
c['boards']={};c['order']=[]
titles={a:b for a,b,_,_ in rows}
col_x=[0,1560,3120,4680]; ys=[0]*4
for i,b in enumerate(order):
    col=i%4
    c['boards'][b+'.dc.html']={"x":col_x[col],"y":ys[col],"w":1440,"h":H[b],"title":(f"{i}"+" · "+({a:a for a,_,_,_ in rows}.get(next((a for a,bb,_,_ in rows if bb==b),'Coverage'),'Coverage')) if b!='Audit' else '0 · Coverage'),"expand":"fill"}
    if b=='System': c['boards'][b+'.dc.html']['is_interactive']=True
    c['order'].append(b+'.dc.html')
    ys[col]+=H[b]+160
# move title note and principles above/side
c['notes']={"t":{"x":0,"y":-300,"text":"ContractIQ redesign: every screen of the application","kind":"title1","maxW":6000},
"n1":{"x":0,"y":-180,"w":520,"text":"Read left to right, top to bottom. Violet 'Simulated' badges mark stand-in systems. Severity is shape + word + colour. The Demo/Live switch is in the sidebar of every screen.","fill":"teal","size":"m"}}
json.dump(c,open(ROOT+'canvas.json','w'),indent=1)
print(len(order),ys)
