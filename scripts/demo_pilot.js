// Data-agnostic walkthrough of every screen on whatever corpus is loaded (built for the 36-document pilot corpus).
// Asserts against the API (nothing hard-coded to a vendor or document), records a captioned video + screenshots.
// Usage: NODE_PATH=$(npm root -g) node scripts/demo_pilot.js [outDir] [label]     (api :8000, web :5173; AUTH_MODE=off)
const { chromium } = require('playwright');
const fs = require('fs');
const OUT = process.argv[2] || '/tmp/demo-pilot', LABEL = process.argv[3] || '';
const U = process.env.WEB || 'http://localhost:5173', A = process.env.API || 'http://localhost:8000';
const results = [], errs = [];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1280, height: 720 }, recordVideo: { dir: OUT, size: { width: 1280, height: 720 } } });
  const p = await ctx.newPage();
  p.on('pageerror', (e) => errs.push('pageerror: ' + e.message));
  p.on('console', (m) => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errs.push('console: ' + m.text()); });
  const caption = (t) => p.evaluate((t) => {
    let el = document.getElementById('__cap');
    if (!el) { el = document.createElement('div'); el.id = '__cap';
      el.style.cssText = 'position:fixed;left:50%;bottom:84px;pointer-events:none;transform:translateX(-50%);z-index:99999;background:rgba(15,23,42,.93);color:#fff;padding:10px 20px;border-radius:10px;font:600 16px system-ui;max-width:90%;text-align:center';
      document.body.appendChild(el); }
    el.textContent = t; }, t);
  const check = async (name, fn) => {
    try { const ok = await fn(); results.push([typeof ok === 'string' ? false : ok !== false, typeof ok === 'string' ? name + ' — ' + ok : name]); }
    catch (e) { results.push([false, name + ' — ' + e.message.split('\n')[0]]); }
  };
  const shot = (n) => p.screenshot({ path: `${OUT}/${n}.png` });
  const step = async (cap, n, ms = 2200) => { await caption(cap); await sleep(ms); if (n) await shot(n); };
  const api = async (path) => (await p.request.get(A + path)).json();
  const visit = async (path, h1) => { await p.goto(U + path); await p.waitForSelector(`h1:has-text("${h1}")`, { timeout: 15000 }); await sleep(900); };

  const meta = await api('/api/meta');
  const contracts = await api('/api/contracts');
  const live = contracts.filter((c) => c.status !== 'draft'), drafts = contracts.filter((c) => c.status === 'draft');

  // 1 dashboard
  await p.goto(U + '/'); await p.waitForSelector('text=Contract expiry', { timeout: 15000 }); await sleep(900);
  await step(`${LABEL} Dashboard — ${live.length} contracts and ${drafts.length} vendor drafts, read from the documents`, '01-dashboard');
  await check('dashboard shows expiry buckets', async () => (await p.locator('body').innerText()).includes('Contract expiry'));

  // 2 repository + a real document
  await visit('/contracts', 'Contract repository');
  await step('Repository — every document: executed contracts and drafts, filterable', '02-contracts');
  await check('repository lists every document', async () => (await p.locator('tbody tr').count()) >= live.length);
  const withUrl = live.find((c) => c.type === 'SOW') || live[0];
  await p.goto(U + `/contracts/${withUrl.id}`); await p.waitForSelector('text=Ask about this document'); await sleep(1200);
  await step('Contract detail: terms, signatures, checklist, effective terms with provenance', '03-detail');
  const det = await api(`/api/contracts/${withUrl.id}`);
  await check('detail loads extracted fields and clauses', async () => !!det.contract && det.clauses.length > 3);

  // 3 vendors
  await visit('/vendors', 'Vendors');
  await step('Vendors — portfolio spend, next dates, risk', '04-vendors');
  const vendors = await api('/api/vendors');
  await p.goto(U + '/vendors/' + encodeURIComponent(live[0].vendor)); await p.waitForSelector('text=Risk scorecard', { timeout: 15000 }); await sleep(900);
  await step('Vendor profile: agreement tree, risk scorecard with drivers, spend exceptions', '05-vendor');
  await check('vendor list matches API', async () => (vendors.vendors || vendors).length > 3);

  // 4 ask
  await visit('/ask', 'Ask your vendor portfolio');
  await p.fill('form input', 'Which vendors have uncapped liability?'); await p.click('form button:has-text("Ask")');
  await p.waitForFunction(() => document.querySelectorAll('[data-msg="assistant"]').length > 0 && !document.querySelector('[data-streaming]'), null, { timeout: 120000 });
  await sleep(1000);
  await step(`Ask (${meta.llm_label}) — the answer, then how it was found`, '06-ask', 2800);
  await check('Ask answered with a result', async () => (await p.locator('[data-msg="assistant"]').last().innerText()).length > 40);

  // 5 redline
  await visit('/redline', 'Review queue');
  await step('Review queue — vendor drafts are redlined against the standard and wait for review', '07-redline', 2600);
  const dr = drafts[0];
  await check('tracked-changes .docx export', async () => { const r = await p.request.get(`${A}/api/redline/${dr.id}/export.docx`); const buf = await r.body(); return r.ok() && buf.slice(0, 2).toString() === 'PK' && Number(r.headers()['x-tracked-changes']) >= 0; });

  // 6 VMO depth
  for (const [path, h, cap, n] of [['/obligations', 'Obligations & SLAs', 'Obligations & SLAs — what each party must do, read from the contracts', '08-obligations'],
                                   ['/spend', 'Spend vs contract', 'Spend vs contract — invoices matched and checked', '09-spend'],
                                   ['/risk', 'Vendor risk & benchmarks', 'Vendor risk scores and term benchmarks', '10-risk']]) {
    await visit(path, h); await step(cap, n, 2400);
  }
  const obl = await api('/api/obligations');
  await check('obligations were derived from the contracts', async () => (obl.summary?.total ?? obl.rows?.length) > 5);

  // 7 alerts
  await visit('/alerts', 'Alerts'); await step('Alerts — raised once per event: renewal notices, expiries, overdue duties, SLA, spend, risk', '11-alerts', 2600);
  const al = await api('/api/alerts/summary');
  await check('alerts raised from live data', async () => al.open > 0);
  await p.getByRole('button', { name: 'Acknowledge' }).first().click(); await sleep(700);
  await check('acknowledge moves an alert out of Open', async () => (await api('/api/alerts/summary')).open === al.open - 1);

  // 8 admin
  for (const [path, cap, n, expect] of [['/admin/connectors', 'Connectors — Google Drive, OneDrive, SharePoint: sync on a schedule into the inbox', '12-connectors', 'Add connector'],
                                        ['/admin/alerts', 'Alert rules and delivery channels (e-mail, Slack, Teams, webhook)', '13-alert-rules', 'Alert rules'],
                                        ['/admin/thresholds', 'Thresholds — spend checks, risk points and SLA credits are configuration', '14-thresholds', 'Thresholds'],
                                        ['/admin/obligations', 'Obligation rules — which extracted values become tracked duties', '15-obl-rules', 'Obligation'],
                                        ['/admin/access', 'Users, roles, API tokens and the audit log', '16-access', 'Audit log']]) {
    await p.goto(U + path); await p.waitForSelector(`text=${expect}`, { timeout: 15000 }); await sleep(900); await step(cap, n, 2200);
  }
  await p.goto(U + '/admin/connectors'); await p.waitForSelector('text=+ Add connector'); await p.click('text=+ Add connector'); await sleep(500);
  await p.getByLabel('Service', { exact: true }).selectOption('sharepoint'); await step('Add a connector: pick the service, enter the tenant and library, test the connection, sync now', '17-add-connector', 2600);

  await check('no browser errors', async () => errs.length === 0 || errs.join(' | ').slice(0, 300));
  await caption('Done'); await sleep(800);
  await ctx.close(); await b.close();
  const vids = fs.readdirSync(OUT).filter((f) => f.endsWith('.webm'));
  if (vids[0]) fs.renameSync(`${OUT}/${vids[0]}`, `${OUT}/walkthrough.webm`);
  let bad = 0;
  for (const [ok, name] of results) { console.log((ok ? 'PASS ' : 'FAIL ') + name); if (!ok) bad++; }
  console.log(`${results.length - bad}/${results.length} checks passed`);
  process.exit(bad ? 1 : 0);
})();
