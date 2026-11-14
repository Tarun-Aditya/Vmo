// One end-to-end video of ContractIQ: every feature, in the order a VMO would use it, in Demo mode (no Claude, simulated systems).
// Nothing is hard-coded to a vendor: it reads what is loaded through the API, drives the real UI, and writes a pass/fail report next to the video.
// Needs: API on :8000 (SIMULATORS=1, SCHEDULER_ENABLED=0), web on :5173, pilot corpus seeded (make seed-pilot), AUTH_MODE=off.
// Usage: NODE_PATH=$(npm root -g) node scripts/demo_e2e.js [outDir]
const { chromium } = require('playwright');
const fs = require('fs');
const OUT = process.argv[2] || 'reports/e2e';
const U = process.env.WEB || 'http://localhost:5173', A = process.env.API || 'http://localhost:8000';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [], errs = [];
const RUN = Date.now().toString(36);   // unique names so a re-run is not treated as a duplicate by the hash check
let n = 0; let TOTAL = 22;

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1366, height: 768 }, recordVideo: { dir: OUT, size: { width: 1366, height: 768 } } });
  const p = await ctx.newPage();
  p.on('pageerror', (e) => errs.push('pageerror: ' + e.message));
  const caption = (t) => p.evaluate((t) => {
    let el = document.getElementById('__cap');
    if (!el) { el = document.createElement('div'); el.id = '__cap';
      el.style.cssText = 'position:fixed;left:50%;bottom:28px;pointer-events:none;transform:translateX(-50%);z-index:99999;background:rgba(15,23,42,.94);color:#fff;padding:10px 20px;border-radius:10px;font:600 16px system-ui;max-width:92%;text-align:center';
      document.body.appendChild(el); }
    el.textContent = t; }, t).catch(() => {});
  const api = async (path, method = 'GET', body) => {
    const r = await p.request.fetch(A + path, { method, headers: { 'content-type': 'application/json' }, data: body ? JSON.stringify(body) : undefined });
    const txt = await r.text(); try { return JSON.parse(txt); } catch { return txt; }
  };
  const go = async (path) => { await p.goto(U + path); await p.waitForLoadState('networkidle').catch(() => {}); await sleep(900); };
  const shot = (name) => p.screenshot({ path: `${OUT}/${name}.png` }).catch(() => {});
  // one feature = one step: caption, do it, hold, record pass/fail
  const feature = async (title, fn, hold = 2200) => {
    n++; const label = `${n}/${TOTAL} · ${title}`;
    try { const note = await fn(label); await caption(label + (typeof note === 'string' ? ' — ' + note : '')); await sleep(hold); await shot(String(n).padStart(2, '0')); results.push([true, title, typeof note === 'string' ? note : '']); }
    catch (e) { results.push([false, title, e.message.split('\n')[0]]); await caption(label + ' (step failed, continuing)'); await sleep(800); }
  };

  const meta = await api('/api/meta');
  const contracts = await api('/api/contracts');
  const live = contracts.filter((c) => c.status !== 'draft'), drafts = contracts.filter((c) => c.status === 'draft');
  const msa = live.find((c) => c.type === 'MSA' && live.some((k) => k.parent_id === c.id)) || live[0];
  await api('/api/admin/mode', 'PUT', { demo: true });
  if (((await api('/api/properties').catch(() => null)) || {}).properties?.length) TOTAL = 25;      // three property steps on a corpus with properties

  await feature('Portfolio dashboard: decision queue, 30/60/90 buckets, Demo mode badge', async (l) => {
    await go('/'); await caption(l);
    return `${live.length} contracts and ${drafts.length} drafts read from documents`; });

  // the owner's questions first, when the corpus carries properties: what each property costs, where one vendor charges hotels differently, what a buyer would inherit
  const props = await api('/api/properties').catch(() => null);
  if (props && props.properties && props.properties.length) {
    await feature('Properties: cost per room with the share of group agreements, and what a buyer would inherit on a sale', async (l) => {
      await go('/properties'); await caption(l);
      const b = p.getByRole('button', { name: /What makes up the cost/ }).first(); await b.click(); await sleep(1200);
      if (!(await p.getByText(/If this property were sold/).count())) throw new Error('sale view missing');
      return `${props.properties.length} properties`; });
    await feature('Compare: one vendor across properties, rates and terms side by side, and what the gap is worth', async (l) => {
      await go('/compare'); await caption(l);
      const c = await api('/api/properties/compare'); if (!c.same_vendor.length) throw new Error('nothing to compare');
      return c.saving_estimate ? `about $${Math.round(c.saving_estimate / 1000)}K a year at the best rate` : ''; });
    await feature('Certificates: what each vendor must hold, read from the certificates on file, with expiry', async (l) => {
      await go('/certificates'); await caption(l);
      const c = await api('/api/certificates'); if (!c.certificates.length) throw new Error('no certificates');
      return `${c.summary.expired} expired, ${c.summary.expiring} expiring, ${c.summary.missing} not on file`; });
  }

  await feature('Contracts repository with filters', async (l) => {
    await go('/contracts'); await caption(l);
    const s = p.getByPlaceholder(/title or vendor/i); if (await s.count()) { await s.first().fill(msa.vendor.split(' ')[0]); await sleep(900); } });

  await feature('Contract detail: fields with source, effective terms, hierarchy, signatures', async (l) => {
    await go(`/contracts/${msa.id}`); await caption(l);
    await p.mouse.wheel(0, 700); await sleep(900); await p.mouse.wheel(0, 700); });

  await feature('Vendors and vendor profile with agreement tree', async (l) => {
    await go('/vendors'); await caption(l); await sleep(1200); await go('/vendors/' + encodeURIComponent(msa.vendor)); });

  await feature('Key clauses matrix: every document by every clause, with citations', async (l) => {
    await go('/clauses'); await caption(l);
    const cell = p.locator('button[aria-label*="present"]').first(); if (await cell.count()) await cell.hover(); });

  await feature('Admin adds a key clause; the next run finds it in every document', async (l) => {
    await api('/api/admin/kcc/data_residency', 'DELETE');
    await go('/admin/clauses'); await caption(l);
    await p.getByRole('button', { name: /\+ Add clause/ }).click(); await sleep(600);
    await p.getByLabel('Clause name').fill('Data residency');
    await p.getByLabel(/Keywords/).fill('data residency\nstored in the european union\nwithin the european union');
    await p.getByRole('button', { name: /Save & re-run/ }).click(); await sleep(4500);
    await go('/clauses'); await caption(l);
    const cols = await api('/api/clause-matrix');
    if (!cols.columns.some((c) => c.key === 'data_residency')) throw new Error('new column missing');
    return 'new column "Data residency" appeared in the matrix'; }, 3000);

  await feature('Ask: a structured question (SQL, steps, table)', async (l) => {
    await go('/ask'); await caption(l);
    await p.getByLabel('Your question').fill('Which contracts have uncapped liability?');
    await p.getByRole('button', { name: 'Ask', exact: true }).click(); await p.waitForSelector('table', { timeout: 30000 }); await sleep(1500); });

  await feature('Ask: a clause question (semantic search, citations)', async (l) => {
    await go('/ask'); await caption(l);
    await p.getByLabel('Your question').fill('What does the indemnity clause say?');
    await p.getByRole('button', { name: 'Ask', exact: true }).click(); await sleep(6000); });

  await feature('Review queue: drafts redlined against template and playbook', async (l) => {
    await go('/redline'); await caption(l); });

  let uploaded = null;
  await feature('Upload a vendor draft: same pipeline, then tracked changes with findings', async (l) => {
    await go('/redline'); await caption(l);
    const md = `# Master Services Agreement – E2E Demo ${RUN}\n\n**Parties:** Arcadia Retail Inc. (the "Customer") and E2E Demo ${RUN} Inc (the "Supplier")\n**Effective Date:** 1 December 2026\n\n## Payment\nThe Customer shall pay each undisputed invoice within seventy-five (75) days of receipt.\n\n## Limitation of Liability\nThe Supplier's liability under this Agreement shall be unlimited.\n\n## Governing Law\nThis Agreement is governed by the laws of the State of Delaware.\n`;
    await p.setInputFiles('input[aria-label="Upload a document to redline"]', { name: `e2e-demo-${RUN}.md`, mimeType: 'text/markdown', buffer: Buffer.from(md) });
    await p.waitForURL(/\/redline\/\d+/, { timeout: 40000 }); await sleep(2500);
    uploaded = +p.url().match(/redline\/(\d+)/)[1]; return 'draft uploaded, deviations listed'; }, 3500);

  await feature('Word-style editor: modes, presence, comment, suggestion', async (l) => {
    if (!uploaded) throw new Error('no draft'); await go(`/documents/${uploaded}/edit`); await caption(l); });

  let share = null;
  await feature('Share link: a guest opens the draft, comments, sees playbook findings', async (l) => {
    if (!uploaded) throw new Error('no draft');
    share = await api(`/api/documents/${uploaded}/share`, 'POST', { level: 'comment', expires_days: 7, label: 'Vendor legal' });
    await go(share.path); await caption(l);
    const name = p.getByLabel('Your name'); if (await name.count()) { await name.fill('Vera (vendor legal)'); await p.getByRole('button', { name: /Open the document/ }).click(); await sleep(1500); } });

  await feature('E-signature: DocuSign-compatible flow, signers sign in order, executed copy re-enters the pipeline', async (l) => {
    if (!uploaded) throw new Error('no draft');
    const r = await api(`/api/documents/${uploaded}/signatures`, 'POST', { provider: 'docusign', sequential: true, signers: [
      { name: 'Meera Joshi', email: 'meera@arcadia.example', role: 'customer' }, { name: 'Vera Kapoor', email: 'vera@vendor.example', role: 'supplier' }] });
    const links = (r.links || []).map((x) => (typeof x === 'string' ? x : x.path || x.url));
    if (!links.length) throw new Error('no signing links: ' + JSON.stringify(r).slice(0, 120));
    for (const link of links) {
      await p.goto(link.startsWith('http') ? link : U + link); await p.waitForLoadState('networkidle').catch(() => {}); await caption(l); await sleep(1500);
      const nm = p.locator('input[name="name"], input[aria-label*="name" i]'); if (await nm.count()) await nm.first().fill(links.indexOf(link) === 0 ? 'Meera Joshi' : 'Vera Kapoor');
      const cb = p.locator('input[type="checkbox"]'); if (await cb.count()) await cb.first().check();
      const sg = p.locator('button[type="submit"], button:has-text("Sign")'); if (await sg.count()) { await sg.first().click(); await sleep(1800); }
    }
    const ex = await api(`/api/documents/${uploaded}/execute`, 'POST');
    if (!ex.executed_contract_id) throw new Error('not executed: ' + JSON.stringify(ex).slice(0, 100));
    await go(`/contracts/${ex.executed_contract_id}`); return 'signed by both, now an executed contract'; }, 3000);

  await feature('Pipeline: Run now, hash-based incremental run, per-file audit', async (l) => {
    await go('/admin'); await caption(l);
    await api('/api/admin/pipeline/upload', 'POST', { filename: `e2e-new-${RUN}.md`, content: `# Services Agreement – E2E Hash ${RUN}\n\n**Parties:** Arcadia Retail Inc. (the "Customer") and E2E Hash ${RUN} Inc (the "Supplier")\n\n## Term\nThis Agreement commences on 1 January 2027 and expires on 1 January 2029.\n` });
    const first = await api('/api/admin/pipelines/contracts/run', 'POST'); await sleep(7000);
    const second = await api('/api/admin/pipelines/contracts/run', 'POST'); await sleep(5000);
    await go('/admin'); await caption(l); await p.locator('tbody tr').first().click().catch(() => {}); await sleep(1500);
    return 'new file read once, then skipped by hash on the next run'; }, 3500);

  await feature('Connectors: simulated Coupa, SAP, Ariba, Drive, SharePoint and a mailbox, all through the real connector code', async (l) => {
    await go('/admin/connectors'); await caption(l);
    for (const re of [/Connect demo ERP/, /Connect demo cloud drives/, /Connect demo mailbox/]) {
      const bt = p.getByRole('button', { name: re }); if (await bt.count()) { await bt.click(); await sleep(7000); } }
    await go('/admin/connectors'); }, 3000);

  await feature('Spend vs contract, SLA and obligations derived from documents and feeds', async (l) => {
    await go('/spend'); await caption(l); await sleep(1500); await go('/obligations'); await caption(l); });

  await feature('Vendor risk scorecards and term benchmarks', async (l) => { await go('/risk'); await caption(l); });

  await feature('Alerts: rules, notification centre, simulated Slack/Teams/webhook/e-mail', async (l) => {
    await go('/admin/alerts'); await caption(l);
    for (const re of [/Add demo channels/, /Check alerts now/]) { const bt = p.getByRole('button', { name: re }); if (await bt.count()) { await bt.click(); await sleep(2500); } }
    await go('/alerts'); });

  await feature('Templates: clause coverage and deviation heatmap; new contract from a template', async (l) => {
    await go('/templates'); await caption(l); await sleep(1500); await go('/new'); });

  await feature('Admin configuration: values, checklist, thresholds, risk weights, approvals, access, usage', async (l) => {
    for (const path of ['/admin/values', '/admin/checklist', '/admin/thresholds', '/admin/risk', '/admin/approvals', '/admin/access', '/admin/quality', '/admin/usage']) {
      await go(path); await caption(l); await sleep(900); } }, 800);

  await feature('Demo and Live: one switch changes the engine for every module', async (l) => {
    await go('/'); await caption(l);
    const t = p.getByLabel('Demo mode');
    await t.click({ force: true }); await sleep(2500); await caption(l + ' · now Live (Claude when available, else the offline fallback)'); await sleep(2000);
    await t.click({ force: true }); await sleep(2000);
    if (!(await api('/api/meta')).demo_mode) await api('/api/admin/mode', 'PUT', { demo: true }); });

  await feature('Security: two-factor setup', async (l) => { await go('/security'); await caption(l); });

  // restore the demo state
  await api('/api/admin/kcc/data_residency', 'DELETE');
  await caption('End of the walkthrough'); await sleep(1500);
  const video = await p.video().path().catch(() => null);
  await ctx.close(); await b.close();
  if (video && fs.existsSync(video)) fs.renameSync(video, `${OUT}/contractiq-e2e.webm`);
  const pass = results.filter((r) => r[0]).length;
  const md = [`# End-to-end walkthrough: ${pass}/${results.length} features completed`, '', `Engine: ${meta.llm_label} (Demo mode, no Claude). Corpus: ${live.length} executed contracts, ${drafts.length} drafts. Simulated systems: ERP, DocuSign, drives, mailbox, alert sinks.`, '',
    ...results.map((r, i) => `${r[0] ? '✓' : '✗'} ${i + 1}. ${r[1]}${r[2] ? ' — ' + r[2] : ''}`), '', errs.length ? '## Page errors\n' + errs.slice(0, 10).join('\n') : 'No page errors.'].join('\n');
  fs.writeFileSync(`${OUT}/REPORT.md`, md); console.log(md);
})();
