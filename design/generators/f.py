from lib import *
import re, json
def tog(on=True): return '<span class="tog%s"></span>'%('' if on else ' off')
# ---------- refresh nav + admin tabs in boards not regenerated
for f,a in {'Main':'Main','Contract':'Contracts','Ask':'Ask','Review':'Review','Clauses':'Clauses','System':'System'}.items():
    s=open(ROOT+f+'.dc.html').read()
    s=re.sub(r'<nav class="rail".*?</nav>',lambda m:nav(a),s,count=1,flags=re.S)
    if f=='System': s=re.sub(r'<nav class="tabs" aria-label="Admin">.*?</nav>',lambda m:admintabs('System'),s,count=1,flags=re.S)
    if f=='Clauses':
        s=re.sub(r'<aside class="card" style="flex:1 1 340px;min-width:0" aria-label="Add a clause">.*?</aside>','',s,count=1,flags=re.S)
        s=s.replace('<button class="btn p">Add a clause</button>','<a class="btn p" href="AdminClauses.dc.html" style="text-decoration:none">Manage clauses in Admin</a>')
        s=s.replace('Custom clauses</div><div class="serif" style="font-size:36px">1</div><div class="mute" style="font-size:13px">Data residency, added by Priya</div>','Custom clauses</div><div class="serif" style="font-size:36px">1</div><div class="mute" style="font-size:13px">added in Admin: Data residency</div>')
    open(ROOT+f+'.dc.html','w').write(s)
# ---------- Portfolio map (bird's-eye hierarchy + timeline)
MONTHS=['Nov 25','Dec','Jan 26','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec 26']
def x(y,m,d=1): return max(0,min(100,((y-2025)*12+(m-11)+(d-1)/30)/14*100))
today=x(2025,11,10)
def colour(end):
    return end
fam=[
('Northwind Logistics','Logistics',[
 ('MSA',0,'Master Services Agreement',(2023,4,1),(2027,3,31),'31 Mar 2027',(2025,11,4),'crit','Notice passed 4 Nov'),
 ('SOW',1,'SOW 1 route planning',(2024,6,1),(2026,5,31),'31 May 2026',None,'',''),
 ('SOW',1,'SOW 2 warehouse ops',(2024,10,1),(2026,9,30),'30 Sep 2026',None,'',''),
 ('Amendment',1,'Amendment 1: payment 60 to 45, term extended',(2025,4,1),(2025,4,1),'applied 1 Apr 2025',None,'','')]),
('Pinecrest Staffing','Staffing',[
 ('MSA',0,'Master Services Agreement',(2023,2,1),(2026,1,31),'31 Jan 2026',(2026,1,1),'high','Notice by 1 Jan'),
 ('SOW',1,'SOW 2 staffing',(2025,2,1),(2026,12,31),'31 Dec 2026',None,'issue','Ends 11 months after its MSA')]),
('Helio Cloud','SaaS',[('SaaS',0,'SaaS subscription',(2024,1,2),(2027,1,2),'2 Jan 2027',(2025,11,12),'crit','Last day to cancel 12 Nov')]),
('Orchid Telecom','Telecom',[('Services',0,'Services agreement',(2024,3,1),(2026,2,28),'28 Feb 2026',(2025,11,30),'med','Notice by 30 Nov')]),
('Brightline Security','Security',[('Services',0,'Security services',(2023,12,21),(2025,12,20),'20 Dec 2025',(2025,11,24),'crit','Expires in 40 days, no auto-renew')]),
('Cobalt Analytics','SaaS',[('SaaS',0,'SaaS subscription',(2024,3,15),(2026,3,14),'14 Mar 2026',(2025,12,14),'med','Auto-renews')]),
('Lumen Surveys','Marketing',[
 ('MSA',0,'Master Services Agreement',(2024,9,1),(2026,9,30),'30 Sep 2026',None,'',''),
 ('NDA',1,'Mutual NDA',(2024,9,1),(2026,3,1),'1 Mar 2026',None,'issue','NDA expires before its MSA')]),
('Ridge Facilities','Facilities',[('SOW',0,'SOW 3 site services',(2025,3,1),(2026,2,28),'28 Feb 2026',None,'issue','No parent MSA found')]),
('Ember Marketing','Marketing',[('Services',0,'Services agreement',(2024,6,1),None,'no end date found',None,'issue','Expiry could not be read')]),
]
def bar(kind,start,end,label,flag):
    s0=x(*start); e0=x(*end) if end else 100
    if end and start==end: return f'<span style="position:absolute;left:0;top:6px" class="chip low">applied</span>'
    left=s0; w=max(e0-s0,1.5)
    months_to_end=((end[0]-2025)*12+(end[1]-11)+(end[2]-10)/30) if end else 99
    col='#B8B2A4' if not end else ('#D9695B' if months_to_end<=1.2 else ('#E5A24F' if months_to_end<=3.2 else '#2E8F80'))
    dash=' border:2px dashed #5E6670;background:#F4F2EE;color:#1B1F24;' if not end else f' background:{col};color:{"#1B1F24" if col!="#2E8F80" else "#fff"};'
    ring=' outline:2px solid #B42318;outline-offset:2px;' if flag=='issue' else ''
    return f'<span style="position:absolute;left:{left}%;width:{w}%;top:5px;height:22px;border-radius:6px;{dash}{ring}font-size:11px;font-weight:600;display:flex;align-items:center;padding:0 8px;overflow:hidden;white-space:nowrap">{label}</span>'
rowsh=''
for v,cat,items in fam:
    rowsh+=f'<div style="padding:10px 12px;background:#F4F2EE;border-top:1px solid #E4E0D8;font-weight:600;display:flex;justify-content:space-between"><span>{v} <span class="mute" style="font-weight:400">· {cat}</span></span></div>'
    for kind,lvl,name,st,en,endlbl,notice,flag,note in items:
        mk=''
        if notice:
            nx=x(*notice); sh={'crit':'<svg width="14" height="14" viewBox="0 0 10 10"><path d="M5 0l5 5-5 5-5-5z" fill="#B42318"/></svg>','high':'<svg width="14" height="14" viewBox="0 0 10 10"><path d="M5 0l5 10H0z" fill="#C2570C"/></svg>','med':'<svg width="14" height="14" viewBox="0 0 10 10"><circle cx="5" cy="5" r="5" fill="#8A6D00"/></svg>'}[flag if flag in('crit','high','med') else 'med']
            mk=f'<span title="notice deadline" style="position:absolute;left:calc({nx}% - 7px);top:9px;z-index:2">{sh}</span>'
        lbl=f'<div style="padding:8px 12px 8px {12+lvl*22}px;display:flex;flex-direction:column"><span>{"└ " if lvl else ""}<b style="font-size:13px">{name}</b></span><span class="mute" style="font-size:11px">{kind} · ends {endlbl}{(" · "+note) if note else ""}</span></div>'
        tl=f'<div style="position:relative;height:32px;margin:6px 0">{bar(kind,st,en,endlbl if en else "?",flag)}{mk}</div>'
        rowsh+=f'<div style="display:grid;grid-template-columns:330px 1fr;border-top:1px solid #EEEAE2;align-items:center"><div>{lbl}</div><div style="position:relative">{tl}</div></div>'
hdr='<div style="display:grid;grid-template-columns:330px 1fr;border-bottom:1px solid #D5D0C6;position:sticky;top:0;background:#fff"><div class="lab" style="padding:10px 12px">Contract family</div><div style="display:grid;grid-template-columns:repeat(14,1fr)">'+''.join(f'<div class="lab" style="padding:10px 0;text-align:center;font-size:11px;border-left:1px solid #EEEAE2">{m}</div>' for m in MONTHS)+'</div></div>'
grid=f'<div style="position:relative">{hdr}{rowsh}<div style="position:absolute;top:0;bottom:0;left:calc(330px + (100% - 330px) * {today/100});width:2px;background:#0E6B5E;pointer-events:none" title="today"></div></div>'
issues=[('crit','Child outlives parent','Pinecrest SOW 2 runs to 31 Dec 2026; its MSA ends 31 Jan 2026.','Extend the MSA or end the SOW'),('high','NDA expires before its MSA','Lumen NDA ends 1 Mar 2026, MSA ends 30 Sep 2026.','Renew or replace the NDA'),('high','SOW without a parent','Ridge Facilities SOW 3 refers to an MSA that is not in the repository.','Upload the MSA or link manually'),('med','No expiry date found','Ember Marketing services agreement: expiry could not be read.','Open and correct the field'),('med','Auto-renews, notice unknown','Cobalt SaaS: notice period not stated.','Check clause 3')]
iss=''.join(f'<div style="padding:12px 0;border-top:1px solid #EEEAE2"><div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">{chip(k,{"crit":"Critical","high":"High","med":"Medium"}[k])}<b>{t}</b></div><div class="mute" style="font-size:13px;margin:2px 0 6px">{d}</div><span style="font-size:13px;color:#0E6B5E;font-weight:600">{a} ›</span></div>' for k,t,d,a in issues)
legend=f'<div style="display:flex;gap:16px;flex-wrap:wrap;font-size:12px" class="mute"><span><span style="display:inline-block;width:14px;height:10px;background:#D9695B;border-radius:3px"></span> ends within 30 days</span><span><span style="display:inline-block;width:14px;height:10px;background:#E5A24F;border-radius:3px"></span> within 90 days</span><span><span style="display:inline-block;width:14px;height:10px;background:#2E8F80;border-radius:3px"></span> later</span><span><span style="display:inline-block;width:14px;height:10px;border:2px dashed #5E6670;border-radius:3px"></span> no end date</span><span><span style="display:inline-block;width:14px;height:10px;outline:2px solid #B42318;border-radius:3px"></span> hierarchy problem</span><span>◆ ▲ ● notice deadline: critical, high, medium</span><span style="color:#0E6B5E;font-weight:600">| today</span></div>'
sel=lambda t,w='1 1 150px': inp(t+' <span class="mute" style="margin-left:auto">▾</span>',w)
body=head('Portfolio map','All contracts as families: parent, children and amendments, with the last day to act on each',btn('Tree view')+btn('Export')+btn('Timeline',True))+\
kpis(kpi('Contract families','9','32 documents'),kpi('Ending within 90 days','5','across 4 families','warn'),kpi('Hierarchy problems','3','child outlives parent, orphan, NDA','crit'),kpi('Missing dates','1','no end date found','warn'),kpi('Notice already passed','1','Northwind','crit'))+\
'<div class="wrap"><section class="card" style="flex:999 1 780px;min-width:0;padding:0;overflow:hidden" aria-label="Timeline of all contracts"><div style="display:flex;flex-wrap:wrap;gap:10px;padding:14px 16px;border-bottom:1px solid #EEEAE2">'+sel('Vendor: All','1 1 150px')+sel('Type: All','1 1 120px')+sel('Status: Active','1 1 130px')+sel('Window: next 14 months','1 1 170px')+sel('Group by: Vendor','1 1 150px')+'</div><div style="padding:8px 16px">'+legend+'</div>'+grid+'</section>'+\
'<aside style="flex:1 1 340px;min-width:0;display:flex;flex-direction:column;gap:20px">'+card('Needs a look',iss,chip('crit','5 open'))+\
card('Selected: Pinecrest SOW 2','<div class="mute" style="font-size:13px;margin-bottom:8px">Effective terms after amendments</div>'+tbl(['Term','Value','From'],[('Parent','Pinecrest MSA','link'),('Ends','31 Dec 2026','SOW 2, p.1'),('Payment','45 days','MSA, p.3'),('Liability','Per MSA','MSA 12.1')])+'<div style="display:flex;gap:8px;margin-top:10px">'+btn('Open contract',False,True)+btn('Fix the dates',False,True)+'</div>')+'</aside></div>'
page('Map','Portfolio map','Map',body,2300)
# ---------- Data inputs (admin)
body=head('Data inputs','Everything that adds data to the application lives here: feeds, measurements, sources and uploads')+admintabs('AdminData')+\
'<div class="wrap"><div style="flex:1 1 440px;min-width:0;display:flex;flex-direction:column;gap:20px">'+\
card('Add an export (CSV)',f'<div style="border:2px dashed #BFB9AB;border-radius:12px;padding:16px;background:#FAF9F6;margin-bottom:12px"><b>Invoices, rate card or SLA report</b><div class="mute" style="font-size:13px">Columns are matched to contracts by vendor and contract reference.</div></div><div style="display:flex;gap:12px;flex-wrap:wrap">'+fld("Feed file name","invoices-nov.csv")+fld("Type","Invoices")+"</div><div style='margin-top:12px'>"+btn('Choose a CSV',True)+'</div>')+\
card('Add a measurement (SLA)','<div style="display:flex;flex-wrap:wrap;gap:12px">'+fld('Contract','Orchid Telecom services')+fld('Measure','Availability %')+fld('Month','Oct 2025')+fld('Actual','99.40')+'</div><div style="margin-top:12px">'+btn('Save measurement',True)+'</div>')+'</div>'+\
'<div style="flex:1 1 440px;min-width:0;display:flex;flex-direction:column;gap:20px">'+\
card('Upload documents',f'<div style="border:2px dashed #BFB9AB;border-radius:12px;padding:16px;background:#FAF9F6"><b>Executed contracts</b><div class="mute" style="font-size:13px">Word, PDF, scans or text. The same pipeline reads them all.</div></div><div style="margin-top:10px">'+btn('Choose files',True,True)+'</div>')+\
card('Sources feeding the repository',tbl(['Source','Kind','Files'],[('Coupa (simulated)','Invoices','42'),('Ariba (simulated)','Contracts','4'),('SharePoint drafts (simulated)','Drafts to redline','3'),('legal@ mailbox (simulated)','Contracts','2')])+'<div class="mute" style="font-size:13px;margin-top:8px">Add or edit a source under Connectors.</div>')+'</div></div>'
page('AdminData','Data inputs','System',body,950)
# ---------- Word-like editor (bare, full width)
pg=lambda inner: f'<div style="background:#fff;width:794px;min-height:1000px;box-shadow:0 2px 12px rgba(0,0,0,.18);padding:96px 88px;margin:0 auto;position:relative" class="serif">{inner}</div>'
tr=lambda t,k: {'del':f'<del style="background:#FBE4E1;color:#8E1B10">{t}</del>','ins':f'<ins style="background:#D9F0E6;color:#0A5247;text-decoration:underline">{t}</ins>'}[k]
cur=lambda n,c,top,left: f'<span style="position:absolute;top:{top}px;left:{left}px;border-left:2px solid {c};height:22px"><span style="position:absolute;top:-18px;left:-2px;background:{c};color:#fff;font:600 11px \'Instrument Sans\';padding:1px 6px;border-radius:4px 4px 4px 0;white-space:nowrap">{n}</span></span>'
doc=pg('<div style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#5E6670;font-family:\'Instrument Sans\'">Draft v4 · Helio Cloud</div><h1 style="font-weight:400;font-size:30px;margin:6px 0 20px">Master Services Agreement</h1>'
 '<p style="font-size:15px;line-height:1.8">This Agreement is made on 1 December 2025 between <b>Arcadia Retail Ltd</b> (the "Customer") and <b>Helio Cloud Pvt Ltd</b> (the "Supplier").</p>'
 '<h2 style="font-size:17px;margin:22px 0 4px">5. Payment</h2><p style="font-size:15px;line-height:1.8">5.1 The Customer shall pay each undisputed invoice within '+tr('seventy-five (75)','del')+' '+tr('forty-five (45)','ins')+' days of receipt.</p>'
 '<h2 style="font-size:17px;margin:22px 0 4px">9. Limitation of liability</h2><p style="font-size:15px;line-height:1.8;position:relative">9.1 '+tr('The Supplier\'s liability shall be unlimited.','del')+' '+tr('The Supplier\'s total liability shall not exceed two times the Fees paid in the twelve months before the claim.','ins')+cur('Rahul','#C2570C',58,420)+'</p>'
 '<p style="font-size:15px;line-height:1.8;position:relative"><span style="background:#FFE9A8">9.2 Neither party is liable for indirect loss.</span>'+cur('Asha','#0E6B5E',4,360)+'</p>'
 '<h2 style="font-size:17px;margin:22px 0 4px">12. Termination</h2><p style="font-size:15px;line-height:1.8">12.1 The Customer may terminate for convenience on '+tr('sixty (60)','ins')+' days\' written notice.</p>')
cm=lambda who,c,txt,top,extra='': f'<div style="position:absolute;right:0;top:{top}px;width:268px;background:#fff;border:1px solid #E4E0D8;border-left:4px solid {c};border-radius:8px;padding:10px 12px;font-size:13px;box-shadow:0 1px 4px rgba(0,0,0,.08)"><b>{who}</b> <span class="mute">just now</span><div style="margin:2px 0 6px">{txt}</div>{extra}</div>'
cmts=cm('Vera (Helio, guest)','#6B6F76','We can accept 3x. Is that workable?',380,'<div style="margin-top:6px"><b>Asha</b> 3x is the approved fallback.</div><div style="margin-top:8px;display:flex;gap:6px"><span class="chip ok">Resolve</span><span class="chip low">Reply</span></div>')+cm('Suggestion by Asha','#0E6B5E','Replace "unlimited" with a 2x cap.',250,'<div style="margin-top:8px;display:flex;gap:6px"><span class="chip ok">✓ Accept</span><span class="chip crit">✗ Reject</span></div>')+cm('Playbook: payment','#C2570C','75 days exceeds the 45-day target.',120,'<span class="chip high">'+'High</span>')
ico=lambda d:f'<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">{d}</svg>'
tb=lambda *x:'<div style="display:flex;gap:2px;align-items:center;padding:0 10px;border-right:1px solid #E4E0D8">'+''.join(f'<button class="btn" style="min-height:34px;padding:0 9px;border-color:transparent;background:{"#E8EBEF" if t.startswith("*") else "transparent"}">{t.lstrip("*")}</button>' for t in x)+'</div>'
ed=f'''<div style="background:#E9E7E1;min-height:100vh;display:flex;flex-direction:column">
<div style="background:#fff;border-bottom:1px solid #E4E0D8;padding:8px 16px;display:flex;flex-wrap:wrap;gap:12px;align-items:center"><a href="Review.dc.html" class="btn" style="min-height:36px;text-decoration:none">‹ Review</a><div><div style="font-weight:600;font-size:16px">Helio Cloud: Master Services Agreement (draft v4)</div><div class="mute" style="font-size:12px">File  Edit  View  Insert  Format  Review  ·  <span style="color:#0A5247">✓ Saved to version 4</span></div></div><div style="margin-left:auto;display:flex;gap:10px;align-items:center"><span class="chip ok">Asha</span><span class="chip med">Rahul</span><span class="chip low">Vera (guest)</span>{btn("Version history",False,True)}{btn("Share",False,True)}<div style="display:inline-flex;border:1px solid #D5D0C6;border-radius:10px;overflow:hidden"><span style="padding:0 12px;min-height:36px;display:inline-flex;align-items:center;background:#1B1F24;color:#fff;font-weight:600;font-size:13px">✎ Suggesting ▾</span></div></div></div>
<div style="background:#F7F6F2;border-bottom:1px solid #E4E0D8;padding:6px 12px;display:flex;flex-wrap:wrap;align-items:center">{tb("Undo","Redo")}{tb("*Normal text ▾","Calibri ▾","11 ▾")}{tb("<b>B</b>","<i>I</i>","<u>U</u>","A ▾")}{tb("≡ Left","Centre","Right","Justify")}{tb("• List","1. List","Indent")}{tb("Insert comment","*Track changes","Accept","Reject","Compare versions")}{tb("Insert clause from playbook ▾","Table")}</div>
<div style="display:flex;flex:1;min-height:0">
<aside style="width:240px;flex:none;background:#F7F6F2;border-right:1px solid #E4E0D8;padding:16px 12px;font-size:13px"><div class="lab" style="margin-bottom:8px">Outline</div><div style="display:flex;flex-direction:column;gap:2px">'''+''.join(f'<div style="padding:7px 8px;border-radius:6px;{"background:#DCEFEA;font-weight:600" if i==2 else ""};display:flex;justify-content:space-between"><span>{t}</span>{b}</div>' for i,(t,b) in enumerate([('1 Definitions',''),('5 Payment',chip('high','1')),('9 Limitation of liability',chip('crit','2')),('12 Termination',chip('crit','1')),('14 Governing law','')]))+f'''</div><div class="lab" style="margin:18px 0 8px">Findings (6)</div><div class="mute">Click a finding to jump to the clause.</div></aside>
<main style="flex:1;min-width:0;padding:24px 16px;position:relative;overflow:hidden"><div style="text-align:center;font-size:11px" class="mute">▏0 · · · 5 · · · 10 · · · 15 · · · 20▕ cm</div><div style="max-width:1120px;margin:8px auto 0;position:relative">{doc}<div style="position:absolute;right:-290px;top:0;width:268px;height:100%">{cmts}</div></div></main></div>
<div style="background:#fff;border-top:1px solid #E4E0D8;padding:6px 16px;font-size:12px;display:flex;gap:20px;flex-wrap:wrap" class="mute"><span>Page 2 of 11</span><span>4,812 words</span><span>Suggesting: your edits become proposals</span><span>3 suggestions · 2 comments · 1 resolved</span><span style="margin-left:auto">Version 4 · autosaved</span></div></div>'''
page('DocumentEditor','Word-style editor','',ed,1300,bare=True)
json.dump(BOARDS,open('boards_f.json','w'))
