import re, json
ROOT='/tmp/claude-0/-home-user-Vmo/cca9cf2d-69d9-5fec-9377-27f3a8653114/scratchpad/dsg/project/'
CSS=open(ROOT+'Ask.dc.html').read()
CSS=CSS[CSS.index('<helmet>'):CSS.index('</helmet>')+9]
CSS=CSS.replace('</style>','''.mx td,.mx th{padding:6px 4px;text-align:center;border-bottom:1px solid #EEEAE2}.sim{background:#EDE7F6;color:#4A2C86}
.inp{border:1px solid #D5D0C6;border-radius:10px;padding:10px 12px;min-height:44px;background:#fff;display:flex;align-items:center}
.tabs{display:flex;flex-wrap:wrap;gap:4px;border-bottom:1px solid #E4E0D8;margin-bottom:20px}
.tabs a{padding:10px 14px;text-decoration:none;color:#5E6670;font-weight:600;border-bottom:3px solid transparent}
.tabs a.on{color:#1B1F24;border-color:#0E6B5E}
.g{display:grid;gap:16px}.wrap{display:flex;flex-wrap:wrap;gap:20px;align-items:flex-start}
.tog{display:inline-block;width:40px;height:22px;border-radius:11px;background:#0E6B5E;position:relative;vertical-align:middle}.tog:after{content:"";position:absolute;right:3px;top:3px;width:16px;height:16px;border-radius:50%;background:#fff}.tog.off{background:#C9C4B8}.tog.off:after{right:auto;left:3px}
.bar{height:10px;border-radius:5px;background:#0E6B5E}
</style>''',1)
NAV=[('Main','Portfolio','<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>'),
('Map','Portfolio map','<circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="12" r="2.5"/><circle cx="6" cy="18" r="2.5"/><path d="M8 7l8 4M8 17l8-4"/>'),
('Contracts','Contracts','<path d="M6 3h9l4 4v14H6z"/><path d="M9 12h7M9 16h7"/>'),
('Vendors','Vendors','<circle cx="9" cy="8" r="3.5"/><path d="M3 20c0-4 3-6 6-6s6 2 6 6"/><path d="M16 5a3 3 0 010 6M18 14c2 1 3 3 3 6"/>'),
('Clauses','Key clauses','<path d="M4 6h16M4 12h10M4 18h13"/>'),
('Ask','Ask','<path d="M4 5h16v11H9l-5 4z"/>'),
('Review','Review','<path d="M4 20l4-1 11-11-3-3L5 16z"/>'),
('Templates','Templates','<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>'),
('Obligations','Obligations','<path d="M5 12l4 4 10-10"/><rect x="3" y="3" width="18" height="18" rx="3"/>'),
('Spend','Spend','<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>'),
('Risk','Risk','<path d="M12 3l8 4v5c0 4-3 7-8 9-5-2-8-5-8-9V7z"/>'),
('Alerts','Alerts','<path d="M6 17V11a6 6 0 0112 0v6l2 2H4z"/><path d="M10 21h4"/>'),
('System','Admin','<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/>')]
def nav(active):
    out='<nav class="rail" aria-label="Main"><div style="display:flex;align-items:center;gap:10px;padding:4px 12px 16px;color:#fff;font-weight:600;font-size:16px"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#5FD3C0" stroke-width="2" aria-hidden="true"><path d="M5 4h10l4 4v12H5z"/><path d="M9 13l2 2 4-4"/></svg>ContractIQ</div>'
    for f,l,ic in NAV:
        on=' class="on"' if f==active else ''
        sep='<div style="flex:1"></div>' if f=='System' else ''
        out+=f'{sep}<a{on} href="{f}.dc.html"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">{ic}</svg>{l}</a>'
    out+='<div style="margin:8px 12px 0;padding:10px 12px;border-radius:10px;background:#2A3038;font-size:12px;color:#C9CDD2"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#F2B544;margin-right:6px"></span><b style="color:#fff">Demo mode</b><br>No Claude. Simulated systems.</div></nav>'
    return out
SH={'crit':'<svg viewBox="0 0 10 10" aria-hidden="true"><path d="M5 0l5 5-5 5-5-5z" fill="currentColor"/></svg>','high':'<svg viewBox="0 0 10 10" aria-hidden="true"><path d="M5 0l5 10H0z" fill="currentColor"/></svg>','med':'<svg viewBox="0 0 10 10" aria-hidden="true"><circle cx="5" cy="5" r="5" fill="currentColor"/></svg>','low':'','ok':'<svg viewBox="0 0 10 10" aria-hidden="true"><path d="M1 5l3 3 5-6" stroke="currentColor" stroke-width="2" fill="none"/></svg>','sim':''}
def chip(k,t): return f'<span class="chip {k}">{SH.get(k,"")}{t}</span>'
def btn(t,p=False,s=False): return f'<button class="btn{" p" if p else ""}"{" style=\"min-height:36px;font-size:13px\"" if s else ""}>{t}</button>'
def inp(t,w=''): return f'<div class="inp"{" style=\"flex:"+w+"\"" if w else ""}>{t}</div>'
def lab(t): return f'<div class="lab" style="margin-bottom:4px">{t}</div>'
def fld(l,v,w='1 1 200px'): return f'<div style="flex:{w}">{lab(l)}{inp(v)}</div>'
def card(title,inner,right='',extra=''):
    h=f'<div style="display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px;margin-bottom:12px"><h2 style="margin:0;font-size:18px">{title}</h2>{right}</div>' if title else ''
    return f'<section class="card" style="{extra}">{h}{inner}</section>'
def tbl(h,rows,cls=''):
    return f'<table class="{cls}"><thead><tr>'+''.join(f'<th>{x}</th>' for x in h)+'</tr></thead><tbody>'+''.join('<tr>'+''.join(f'<td>{c}</td>' for c in r)+'</tr>' for r in rows)+'</tbody></table>'
def kpi(l,v,s='',tone=''):
    b={'crit':'#E3A29B','warn':'#E9B77F'}.get(tone,'#E4E0D8')
    return f'<div class="card" style="border-color:{b}"><div class="lab">{l}</div><div class="serif num" style="font-size:34px">{v}</div><div class="mute" style="font-size:13px">{s}</div></div>'
def kpis(*k): return '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:16px;margin-bottom:20px">'+''.join(k)+'</div>'
def head(t,sub='',right=''): return f'<header style="display:flex;flex-wrap:wrap;gap:12px;justify-content:space-between;align-items:flex-end;margin-bottom:20px"><div><h1 class="serif" style="margin:0 0 4px;font-size:34px;font-weight:400">{t}</h1><span class="mute">{sub}</span></div><div style="display:flex;gap:8px;flex-wrap:wrap">{right}</div></header>'
def topbar(): return '<div style="display:flex;flex-wrap:wrap;align-items:center;gap:12px;justify-content:flex-end;margin-bottom:14px" class="mute"><span><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#0E6B5E;margin-right:6px"></span>Synced 4 min ago · next in 26 min</span><span class="chip sim">Demo · no Claude</span><button class="btn" style="min-height:36px">☾ Dark</button><span style="width:36px;height:36px;border-radius:50%;background:#DCEFEA;color:#0E6B5E;display:grid;place-items:center;font-weight:600">PN</span></div>'
ADMIN=[('System','Pipeline'),('AdminClauses','Key clauses'),('AdminValues','Values'),('AdminChecklist','Checklist'),('AdminThresholds','Thresholds'),('AdminRisk','Risk weights'),('AdminObligations','Obligation rules'),('AdminConnectors','Connectors'),('AdminData','Data inputs'),('AdminAlerts','Alerts'),('AdminApprovals','Approvals'),('AdminAccess','Access and audit'),('AdminQuality','Quality'),('AdminUsage','Usage')]
def admintabs(cur): return '<nav class="tabs" aria-label="Admin">'+''.join(f'<a{" class=\"on\"" if f==cur else ""} href="{f}.dc.html">{l}</a>' for f,l in ADMIN)+'</nav>'
BOARDS={}
def page(fname,title,active,body,h=1100,bare=False,interactive=False,expand=True):
    shell=f'<div class="app">{nav(active)}<main class="main">{topbar()}{body}</main></div>' if not bare else body
    html=f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<script src="./support.js"></script>
</head>
<body>
<x-dc>
{CSS}
{shell}
</x-dc>
<script type="text/x-dc" data-dc-script data-props='{{"$preview":{{"width":1440,"height":{h}}}}}'>
class Component extends DCLogic {{
renderVals() {{ return {{}}; }}
}}
</script>
</body>
</html>
'''
    open(ROOT+fname+'.dc.html','w').write(html)
    BOARDS[fname+'.dc.html']=dict(w=1440,h=h,title=title,expand='fill')
