from lib import *
import re, json
act={'Main':'Main','Contract':'Contracts','Ask':'Ask','Review':'Review','Clauses':'Clauses','System':'System'}
for f,a in act.items():
    s=open(ROOT+f+'.dc.html').read()
    s=re.sub(r'<nav class="rail".*?</nav>',lambda m:nav(a),s,count=1,flags=re.S)
    s=s.replace('</style>','.tabs{display:flex;flex-wrap:wrap;gap:4px;border-bottom:1px solid #E4E0D8;margin-bottom:20px}.tabs a{padding:10px 14px;text-decoration:none;color:#5E6670;font-weight:600;border-bottom:3px solid transparent}.tabs a.on{color:#1B1F24;border-color:#0E6B5E}.sim{background:#EDE7F6;color:#4A2C86}\n</style>',1) if '.tabs{' not in s else s
    if f=='System' and 'aria-label="Admin"' not in s:
        s=s.replace('<header style="margin-bottom:20px">',admintabs('System')+'<header style="margin-bottom:20px">',1)
    # fix links of removed pages
    s=s.replace('href="Main.dc.html"><svg','href="Main.dc.html"><svg')
    open(ROOT+f+'.dc.html','w').write(s)
# ---- enrich dashboard
s=open(ROOT+'Main.dc.html').read()
extra=f'''<div class="wrap" style="margin-top:20px">
<section class="card" style="flex:999 1 560px;min-width:0" aria-label="Expiries over 12 months"><h2 style="margin:0 0 4px;font-size:18px">Expiries over the next 12 months</h2><p class="mute" style="margin:0 0 12px;font-size:13px">contracts per month</p><div style="display:flex;gap:8px;align-items:flex-end;height:150px">{"".join(f'<div style="flex:1;text-align:center"><div style="height:{h}px;background:{"#C2570C" if i<3 else "#0E6B5E"};border-radius:3px 3px 0 0"></div><div class="mute" style="font-size:11px;margin-top:4px">{m}</div></div>' for i,(m,h) in enumerate([("Nov",70),("Dec",110),("Jan",90),("Feb",50),("Mar",40),("Apr",20),("May",20),("Jun",30),("Jul",10),("Aug",20),("Sep",10),("Oct",30)]))}</div></section>
<section class="card" style="flex:1 1 380px;min-width:0" aria-label="30 60 90 buckets"><h2 style="margin:0 0 12px;font-size:18px">Next 30 / 60 / 90 days</h2>{tbl(["Window","Contracts","Value at stake"],[(chip("crit","30 days"),"4","₹ 6.4 cr"),(chip("high","60 days"),"2","₹ 3.1 cr"),(chip("med","90 days"),"2","₹ 2.4 cr")])}</section></div>
<section class="card" style="margin-top:20px" aria-label="Vendor operations"><div style="display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px"><h2 style="margin:0 0 12px;font-size:18px">Vendor operations</h2><a class="btn" style="min-height:36px;text-decoration:none" href="Obligations.dc.html">Open obligations</a></div><div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px"><div><div class="lab">Obligations due in 30 days</div><div class="serif" style="font-size:30px">4</div></div><div><div class="lab">SLA breaches this quarter</div><div class="serif" style="font-size:30px">2</div></div><div><div class="lab">Spend exceptions</div><div class="serif" style="font-size:30px">5</div></div><div><div class="lab">High-risk vendors</div><div class="serif" style="font-size:30px">3</div></div></div></section>
</main>'''
s=s.replace('</main>',extra,1).replace('"height":1180}','"height":1750}')
open(ROOT+'Main.dc.html','w').write(s)
# ---- enrich contract detail
s=open(ROOT+'Contract.dc.html').read()
extra=f'''<div class="wrap" style="margin-top:20px">
<section class="card" style="flex:1 1 360px;min-width:0"><h2 style="margin:0 0 12px;font-size:18px">Hierarchy</h2><div style="display:flex;flex-direction:column;gap:6px;font-size:13px"><div style="padding:10px 12px;border:2px solid #0E6B5E;border-radius:10px"><b>MSA</b> · you are here</div><div style="margin-left:24px;padding:8px 12px;border:1px solid #E4E0D8;border-radius:10px">SOW 1 route planning</div><div style="margin-left:24px;padding:8px 12px;border:1px solid #E4E0D8;border-radius:10px">SOW 2 warehouse ops</div><div style="margin-left:24px;padding:8px 12px;border:1px dashed #0E6B5E;border-radius:10px;background:#E9F4F1">Amendment 1 {chip("ok","overrides MSA")}</div></div><p class="mute" style="font-size:13px;margin:10px 0 0">This amendment overrides: payment terms, expiry date.</p></section>
<section class="card" style="flex:1 1 360px;min-width:0"><h2 style="margin:0 0 12px;font-size:18px">Deviations from the standard template</h2>{tbl(["Clause","What differs","Severity"],[("Liability cap","Uncapped; template 2x fees",chip("crit","Critical")),("Termination for convenience","Missing",chip("high","High")),("Payment","60 days; template 45",chip("med","Medium"))])}</section>
<section class="card" style="flex:1 1 360px;min-width:0"><h2 style="margin:0 0 12px;font-size:18px">Terms and limits</h2>{tbl(["Value","Reading","Source"],[("Payment terms","45 days","Amendment 1"),("Liability cap","None","cl. 12.1, p.4"),("Incident notice","24 hours","cl. 9.3, p.3"),("Availability","99.9%","SLA, p.8")])}</section></div>
<div class="wrap" style="margin-top:20px">
<section class="card" style="flex:1 1 360px;min-width:0"><h2 style="margin:0 0 12px;font-size:18px">Signatures</h2>{tbl(["Party","Signatory","Signed"],[("Arcadia Retail Ltd","M. Joshi, CFO","12 Mar 2023"),("Northwind Logistics","K. Bose, Director","14 Mar 2023")])}<div style="margin-top:10px">{chip("ok","Fully executed")} <button class="btn" style="min-height:36px;font-size:13px">Send for e-signature</button></div></section>
<section class="card" style="flex:1 1 360px;min-width:0"><h2 style="margin:0 0 12px;font-size:18px">A person corrected a value</h2><p style="margin:0">Governing law was read as <b>Delaware</b> and corrected to <b>England and Wales</b> by Asha on 3 Nov. Corrections survive re-runs.</p><div style="margin-top:10px"><button class="btn" style="min-height:36px;font-size:13px">Correct a field</button></div></section>
<section class="card" style="flex:1 1 360px;min-width:0"><h2 style="margin:0 0 12px;font-size:18px">Approvals and sharing</h2><p class="mute" style="margin:0 0 10px;font-size:13px">Executed contracts are read-only. Redlining is only for drafts.</p><div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn" style="min-height:36px;font-size:13px">Share link</button><button class="btn" style="min-height:36px;font-size:13px">Start amendment draft</button></div></section></div>
</main>'''
s=s.replace('</main>',extra,1).replace('"height":1180}','"height":1800}')
open(ROOT+'Contract.dc.html','w').write(s)
