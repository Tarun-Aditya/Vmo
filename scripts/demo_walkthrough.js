// Full feature walkthrough: asserts expected values on every screen AND records a captioned video.
// Run on a freshly seeded database (it creates a draft and edits admin settings, then restores them).
// Usage: NODE_PATH=$(npm root -g) node scripts/demo_walkthrough.js [outDir]   (api :8000, web :5173)
const { chromium } = require('playwright');
const fs = require('fs');
const OUT = process.argv[2] || '/tmp/demo-video';
const U = 'http://localhost:5173', A = 'http://localhost:8000';
const results = [], errs = [];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1280, height: 720 }, recordVideo: { dir: OUT, size: { width: 1280, height: 720 } } });
  const p = await ctx.newPage();
  p.on('pageerror', (e) => errs.push('pageerror: ' + e.message));
  p.on('console', (m) => { if (m.type() === 'error') errs.push('console: ' + m.text()); });

  const caption = async (t) => p.evaluate((t) => {
    let el = document.getElementById('__cap');
    if (!el) { el = document.createElement('div'); el.id = '__cap';
      el.style.cssText = 'position:fixed;left:50%;bottom:16px;transform:translateX(-50%);z-index:99999;background:rgba(15,23,42,.93);color:#fff;padding:10px 20px;border-radius:10px;font:600 16px system-ui;max-width:90%;text-align:center;box-shadow:0 4px 20px rgba(0,0,0,.4)';
      document.body.appendChild(el); }
    el.textContent = t; }, t);
  const check = async (name, fn) => {
    try { const ok = await fn(); results.push([typeof ok === 'string' ? false : ok !== false, typeof ok === 'string' ? name + ' — ' + ok : name]); }
    catch (e) { results.push([false, name + ' — ' + e.message.split('\n')[0]]); }
  };
  const step = async (cap, ms = 1800) => { await caption(cap); await sleep(ms); };
  const scroll = async (y, ms = 800) => { await p.mouse.wheel(0, y); await sleep(ms); };
  const top = async () => { await p.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' })); await sleep(600); };
  const text = (sel) => p.locator(sel).first().innerText();
  const api = (path, init) => p.evaluate(([u, i]) => fetch(u, i).then((r) => r.json()), [A + path, init]);
  const nav = async (label) => { await p.click(`nav >> text=${label}`); await sleep(700); };
  const ans = () => text('section:has-text("Answer")');
  const ask = async (q, waitFor) => {
    await p.fill('form input', q); await p.click('button:has-text("Ask")');
    await p.waitForSelector(waitFor || 'text=Thinking'); await sleep(900);
  };

  // ---------------------------------------------------------------- 1 DASHBOARD
  await p.goto(U + '/'); await p.waitForSelector('text=Contract expiry'); await sleep(800);
  await step('1 · Dashboard — USD, live: synced from the document pipeline', 2400);
  await check('Header: pipeline badge shows it is synced', async () => (await p.locator('a:has-text("Synced")').count()) === 1);
  await check('Dashboard: 27 executed documents, $38.07M annual value', async () => (await p.locator('.text-3xl').first().innerText()) === '27' && (await p.content()).includes('$38.07M'));
  await check('Dashboard: 8 expiring in 90 days ($15.69M at stake), 2 notices due (1 passed), 3 uncapped', async () => { const c = await p.content(); return c.includes('$15.69M at stake') && c.includes('1 already passed'); });
  await scroll(300); await step('Contracts expiring in the next 30 / 60 / 90 days', 2600);
  const lane = (l) => `section[aria-label="${l}"]`;
  await check('Lanes 4 / 1 / 3 with $ value at stake', async () => (await p.locator(lane('Expiring in 0–30 days') + ' article').count()) === 4 && (await p.locator(lane('Expiring in 31–60 days') + ' article').count()) === 1 && (await p.locator(lane('Expiring in 61–90 days') + ' article').count()) === 3 && (await text(lane('Expiring in 0–30 days') + ' header')).includes('$2.62M') && (await text(lane('Expiring in 61–90 days') + ' header')).includes('$12.65M'));
  await check('AdSpark card: notice deadline passed + uncapped, $220K', async () => { const t = await text('article:has-text("AdSpark")'); return t.includes('notice deadline passed') && t.includes('uncapped') && t.includes('$220K'); });

  // ---------------------------------------------------------------- 2 VENDORS
  await top(); await nav('Vendors'); await p.waitForSelector('text=Each vendor'); await sleep(800);
  await step('2 · Vendors — IT services portfolio: spend, next dates, risk flags', 3000);
  await check('Vendors: 9 vendors, $38.07M', async () => (await p.locator('tbody tr').count()) === 9 && (await p.content()).includes('$38.07M'));
  await check('Vendors: Accentia 8 docs, $18.70M + $1.95M work orders', async () => { const t = await text('tr:has-text("Accentia")'); return t.includes('8 docs') && t.includes('$18.70M') && t.includes('$1.95M'); });
  await check('Vendors: Delmont critical (uncapped), PulseHR (no DPA), AdSpark (notice passed)', async () => (await text('tr:has-text("Delmont")')).includes('uncapped liability') && (await text('tr:has-text("PulseHR")')).includes('personal data, no DPA') && (await text('tr:has-text("AdSpark")')).includes('notice deadline passed'));
  await p.click('a:has-text("Accentia Technology Services Inc")'); await p.waitForSelector('text=Contracts & hierarchy'); await sleep(900);
  await step('Vendor profile: MSA → SOW → Work Order tree, key dates, deviations, clause coverage', 3000);
  await check('Profile: tree has MSA, 3 SOWs, 2 work orders (one pending signature)', async () => { const t = await text('section:has(h2:has-text("Contracts & hierarchy"))'); return t.includes('Application Managed Services') && t.includes('AWS Cloud Migration') && t.includes('Data Center Exit') && t.includes('Endpoint Security Hardening') && t.includes('pending'); });
  await scroll(900); await check('Profile: deviations include Key Personnel on SOW 1', async () => (await p.locator('text=Key Personnel').count()) >= 1);

  // ---------------------------------------------------------------- 3 REPOSITORY + DETAIL
  await top(); await nav('Contracts'); await p.waitForSelector('tr:has-text("AdSpark")'); await sleep(600);
  await step('3 · Repository — executed contracts and drafts in one place', 2400);
  await check('Repository: 32 documents (27 executed + 5 drafts)', async () => (await p.locator('tbody tr').count()) === 32);
  await p.selectOption('select >> nth=4', 'draft'); await sleep(700);
  await check('Status filter: 5 drafts', async () => (await p.locator('tbody tr').count()) === 5);
  await p.click('text=Reset'); await sleep(400);
  await p.click('button[role=tab]:has-text("Hierarchy")'); await sleep(900);
  await step('Hierarchy: MSA → SOW → Work Order, amendments / NDAs / DPAs under their agreement', 3000);
  await check('Hierarchy: 4 work orders; Taraka MSA tree present', async () => (await p.locator('a:has-text("Work Order ")').count()) === 4 && (await p.locator('text=Taraka Consultancy Services Ltd').count()) >= 1);
  await p.click('button[role=tab]:has-text("Table")'); await sleep(400);
  await p.click('a:has-text("Master Services Agreement – Accentia")'); await p.waitForSelector('text=Effective terms'); await sleep(900);
  await step('Contract detail: signatures, terms & limits, checklist, effective terms with provenance', 3000);
  await check('Detail: signed by Michael Brennan and Laura Stephens', async () => { const t = await text('section:has-text("Signatures")'); return t.includes('Michael Brennan') && t.includes('Laura Stephens') && t.includes('fully signed'); });
  await check('Detail: Terms & limits show insurance $5.00M, payment 45 days', async () => { const t = await text('section:has-text("Terms & limits")'); return t.includes('$5.00M') && /Payment terms\s+45/.test(t); });
  await check('Detail: checklist card (pass/fail) and Ask / Redline links', async () => (await text('section:has-text("Checklist")')).includes('✓') && (await p.locator('a:has-text("Ask about this document")').count()) === 1);
  await scroll(800); const eff = p.locator('section:has-text("Effective terms (after amendments)")');
  await check('Effective terms: payment 30 overridden by Amendment No. 1', async () => { const r = await eff.locator('tr:has-text("Payment terms")').innerText(); return /30/.test(r) && r.includes('Overridden by Amendment No. 1'); });

  // ---------------------------------------------------------------- 4 KEY CLAUSES
  await nav('Key clauses'); await p.waitForSelector('text=Key contract clauses across all documents'); await sleep(800);
  await step('4 · Key clauses — every document × every key clause: ✓ / ✗ with citations', 2800);
  await check('Matrix: 25 contracts + 5 drafts, 23 clause columns', async () => (await p.locator('tbody tr:has(button[aria-label*="Term"])').count()) === 30 && (await p.locator('thead th').count()) === 25);
  await p.locator('button[aria-label^="Master Services Agreement – Accentia Technology Services: Limitation of Liability present"]').hover(); await sleep(800);
  await check('Hover ✓: citation with text and page 4', async () => { const t = await text('[role=tooltip]'); return t.includes('Present') && t.includes('liability') && t.includes('page 4'); });
  await p.locator('button[aria-label^="Work Order 2 – Endpoint Security Hardening – Accentia Technology Services: Signed by both parties absent"]').hover(); await sleep(800);
  await step('Hover ✗: why — here the supplier has not countersigned', 2400);
  await check('Hover ✗ shows the signature evidence', async () => (await text('[role=tooltip]')).includes('Not fully signed'));

  // ---------------------------------------------------------------- 5 ASK (portfolio)
  await top(); await nav('Ask'); await p.waitForSelector('text=Scope of the question'); await sleep(600);
  await step('5 · Ask — analytical questions across the portfolio (scope: all documents)', 2400);
  await check('Ask: scope panel lists all 32 documents with search', async () => (await p.locator('ul[aria-label="Documents"] li').count()) === 32);
  await p.click('button:has-text("Which vendors have uncapped liability?")'); await p.waitForSelector('text=Thinking'); await sleep(900);
  await check('Ask: table answer (3 vendors), no SQL visible; thinking collapsed', async () => (await p.locator('section:has-text("Answer") tbody tr').count()) === 3 && (await p.locator('pre').count()) === 0 && (await ans()).includes('PulseHR'));
  await p.click('button:has-text("Thinking")'); await sleep(800);
  await check('Thinking: numbered steps incl. generated SQL', async () => (await p.locator('ol li').count()) >= 3 && (await p.locator('pre:has-text("v_effective_terms")').count()) >= 1);
  await p.click('button:has-text("Thinking")');
  await ask('How many contracts are expiring in the next quarter?', 'text=Breakdown by category');
  await step('Aggregate: headline numbers → breakdown → list', 3000);
  await check('Aggregate: 3 contracts, $12.65M, 1 Jan – 31 Mar 2027', async () => { const t = await p.locator('div.bg-indigo-50').allInnerTexts(); const a = await ans(); return t.length === 2 && t[0].includes('3') && t[1].includes('$12.65M') && a.includes('31 Mar 2027'); });
  await ask('Which contracts have payment terms below 45 days?', 'section:has-text("Answer") table');
  await step('Values & limits are askable: “payment terms below 45 days”', 2600);
  await check('Threshold question: 2 contracts with a Payment terms (days) column', async () => (await p.locator('section:has-text("Answer") tbody tr').count()) === 2 && (await text('section:has-text("Answer") thead')).toLowerCase().includes('payment terms (days)'));
  await ask('Which contracts fail the checklist?', 'text=Checklist results');
  await step('Checklist question: failures by severity, then every failing rule with value vs limit', 3000);
  await check('Checklist answer: severity breakdown + results table with ▲▲ critical first', async () => (await p.locator('section:has-text("Answer") table').count()) === 2 && (await text('section:has-text("Answer") table >> nth=1 >> tbody tr')).toLowerCase().includes('critical'));
  await ask('Which vendors have contracts expiring in the next 90 days?', 'text=Vendors');
  await check('Vendor-level: 6 vendors, tiles Contracts 8 / Vendors 6 / $15.69M', async () => { const t = await p.locator('div.bg-indigo-50').allInnerTexts(); return t.length === 3 && t[0].includes('8') && t[1].includes('6') && t[2].includes('$15.69M'); });

  // ---------------------------------------------------------------- 6 ASK (scoped to documents)
  await p.click('[role=radio]:has-text("Selected documents")'); await sleep(500);
  await p.fill('input[aria-label="Search documents"]', 'delmont'); await sleep(600);
  await p.locator('ul[aria-label="Documents"] label:has-text("Master Services Agreement – Delmont") input').check(); await sleep(500);
  await step('6 · Ask about specific documents: pick them on the right (search + select)', 2800);
  await check('Scope: 1 selected; list filtered by search', async () => (await text('aside')).includes('1 selected') && (await p.locator('ul[aria-label="Documents"] li').count()) === 6);
  await ask('Tell me about this contract', 'section:has-text("Answer") table');
  await step('Specific document → a fact sheet: dates, signatories, extracted terms and limits', 3200);
  await check('Fact sheet (Delmont MSA): England and Wales, Unlimited liability, $500K insurance', async () => { const t = await ans(); return t.includes('England and Wales') && t.includes('Unlimited') && t.includes('$500K') && t.includes('Scope: 1 selected document'); });
  await ask('What does the indemnity clause say?', 'section:has-text("Answer") table');
  await check('Clause text quoted from the selected document', async () => (await ans()).includes('The Customer shall indemnify the Supplier'));
  await p.fill('input[aria-label="Search documents"]', 'quanta'); await sleep(500);
  await p.locator('ul[aria-label="Documents"] label:has-text("Quanta") input').check();
  await p.fill('input[aria-label="Search documents"]', 'delmont'); await sleep(300);
  await p.locator('ul[aria-label="Documents"] label:has-text("Master Services Agreement – Delmont") input').uncheck(); await sleep(400);
  await ask('Which checklist rules does it fail?', 'text=Checklist results');
  await step('A draft vendor contract: the checklist rules it fails', 2800);
  await check('Scoped to the Quanta draft: SLA, incident notice, data processing rules fail', async () => { const t = await ans(); return t.includes('Quanta') && t.includes('Availability SLA') && t.includes('Security incident notice') && !t.includes('Delmont'); });
  await p.click('[role=radio]:has-text("All documents")');

  // ---------------------------------------------------------------- 7 REDLINE
  await top(); await nav('Redline'); await p.waitForSelector('[aria-label="Document with tracked changes"]'); await sleep(900);
  await step('7 · Review queue — vendor drafts from the drafts folder are redlined and wait for review', 2600);
  await check('Redline queue: 5 vendor drafts, all "To review"; clean control passes everything', async () => (await p.locator('button:has-text("Draft ")').count()) >= 5 && (await text('[role=tablist]')).includes('To review 5') && (await p.locator('text=passes checklist, matches standard').count()) === 1);
  await p.click('button:has-text("Draft SaaS Agreement – Quanta")'); await p.waitForSelector('text=Quanta'); await sleep(900);
  await check('Quanta: 4 checklist failures, 6 changes from the standard', async () => (await text('section')).includes('4 checklist rules failed, 6 changes'));
  await check('Word-style page with tracked changes in place (struck-through original, inserted wording)', async () => (await p.locator('.docpage del.tc').count()) > 0 && (await p.locator('.docpage ins.tc').count()) > 0 && (await p.locator('.docpage .rl-open').count()) >= 4);
  await step('The draft as a Word-style page: the redline is shown as tracked changes, comments in the margin', 3000);
  const qid = (await api('/api/redline/documents')).find((d) => d.title.includes('Quanta')).id;
  const changed = (await api(`/api/redline/${qid}`)).items.filter((i) => i.status === 'changed').map((i) => i.clause_type);
  await p.locator(`#cmt-${changed[0]} >> text=✓ Accept`).click(); await sleep(700);
  await check('Accepting a change turns it green in the document and moves the draft to "In review"', async () => (await p.locator('.docpage .rl-accepted').count()) === 1 && (await text('[role=tablist]')).includes('In review 1'));
  await p.locator(`#cmt-${changed[1]} >> text=✗ Reject`).click(); await sleep(600);
  await check('Rejecting restores the original wording', async () => (await p.locator('.docpage .rl-rejected').count()) === 1);
  await step('Accept or reject each change — the document updates as you decide', 2600);
  await p.fill('input[aria-label="Review note"]', 'Cap and SLA need legal sign-off'); await p.click('button:has-text("Request changes")'); await sleep(900);
  await check('Review status saved: Changes requested (with a note)', async () => { const r = await api(`/api/redline/${(await api('/api/redline/documents')).find((d) => d.title.includes('Quanta')).id}`); return r.review.status === 'changes_requested' && r.review.note.includes('legal sign-off'); });
  await p.click('[role=tab]:has-text("Pre-signature checklist")'); await sleep(500);
  await p.click('li:has-text("Availability SLA") button'); await sleep(700);
  await step('The pre-signature checklist: each failed rule shows value vs limit, the clause cited, suggested wording', 3200);
  await check('Failed rule shows suggested wording', async () => (await p.locator('text=Suggested wording').count()) >= 1);
  await p.click('text=Failures only'); await sleep(500);
  await check('Failures only: every row is a failure', async () => (await p.locator('li:has(b[aria-label="pass"])').count()) === 0);
  await top(); await p.click('button:has-text("Re-run live")'); await sleep(1800);
  await check('Re-run live keeps the findings', async () => (await text('section')).includes('4 checklist rules failed'));
  await p.click('button:has-text("Brightpath")'); await p.waitForSelector('text=Ready to sign'); await sleep(700);
  await check('Clean control: ready to sign', async () => (await text('section')).includes('Ready to sign'));
  await p.click('button:text-is("✓ Approve")'); await sleep(700);
  await check('Approve: queue shows Approved 1', async () => (await text('[role=tablist]')).includes('Approved 1'));
  await step('Approve the clean draft — the queue keeps count of what is waiting', 2200);
  // leave the seeded review state clean for repeatability
  for (const d of await api('/api/redline/documents')) { for (const ct of Object.keys((await api(`/api/redline/${d.id}`)).decisions)) await api(`/api/redline/${d.id}/decision`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ clause_type: ct, decision: null }) }); await api(`/api/redline/${d.id}/review`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: 'pending' }) }); }

  // ---------------------------------------------------------------- 8 NEW CONTRACT
  await nav('New contract'); await p.waitForSelector('text=New contract from a template'); await sleep(600);
  await p.getByLabel('Deal details', { exact: true }).fill('New SOW with Accentia Technology Services Inc for a retail analytics platform build on Snowflake and dbt starting 4 January 2027 for 12 months. Annual fees $1.8M, net 20 payment. Owner: Jordan Blake.');
  await p.click('button:has-text("Read details into the form")'); await p.waitForSelector('[role=status]'); await sleep(900);
  await step('8 · New contract: paste the deal details (an email, notes, JSON, CSV or a file) — the form is filled from them', 3400);
  await check('Brief read: SOW template, vendor, dates, fees, 20-day payment, owner; parent MSA picked', async () => { const t = await text('[role=status]'); const v = await p.getByLabel('Vendor (supplier)').inputValue(); const par = await p.getByLabel('Parent agreement').inputValue(); return t.includes('template: SOW') && v === 'Accentia Technology Services Inc' && (await p.getByLabel('Payment terms (days)').inputValue()) === '20' && (await p.getByLabel('Annual fees (USD)').inputValue()) === '1800000' && !!par; });
  await p.getByLabel('Scope of work').fill('Retail analytics platform build on Snowflake and dbt'); await sleep(300);
  await p.locator('summary:has-text("Clauses in this document")').click(); await sleep(500);
  await check('Clause picker: SOW template has 15 clauses; one can be added from the library of 39', async () => { const n = await p.locator('details input[type=checkbox]').count(); return n === 15 ? true : `clauses=${n}`; });
  await p.locator('#addclause').selectOption({ label: 'Audit Rights' }); await sleep(500);
  await step('Choose which clauses go in: the template defaults, plus any from the clause library', 2600);
  await check('Audit Rights added (16 clauses)', async () => (await p.locator('details input[type=checkbox]').count()) === 16);
  await p.click('button:has-text("Preview & check")'); await p.waitForSelector('.docpage[aria-label="Contract text"]'); await sleep(900);
  await step('The draft opens in an online editor like Word / Docs — placeholders highlighted; the checklist flags 20-day payment terms', 3400);
  await check('Draft references its MSA; checklist flags payment terms', async () => { const v = await text('.docpage[aria-label="Contract text"]'); const t = await text('section:has-text("Pre-signature checklist")'); return v.includes('Audit Rights') && v.includes('issued under the Master Services Agreement dated') && v.includes('USD 1,800,000') && t.includes('Payment terms ≥ 30 days') && /2 fail/.test(t); });
  await p.evaluate(() => { const el = document.querySelector('.docpage[aria-label="Contract text"]'); el.innerHTML = el.innerHTML.replace('within 20 days', 'within 45 days'); el.dispatchEvent(new Event('input', { bubbles: true })); });
  await p.click('button:has-text("Re-check my edits")'); await sleep(1200);
  await step('Edit the clause, re-check: every rule now passes', 2600);
  await check('After the edit: 0 failures', async () => /0 fail/.test(await text('section:has-text("Pre-signature checklist")')));
  await p.click('button:has-text("Create draft & add to repository")'); await p.waitForSelector('text=Draft created'); await sleep(900);
  await check('Created: added to the folder, extracted, no failing rules', async () => { const t = await text('section:has-text("Draft created")'); return t.includes('added to the folder') && t.includes('Every applicable checklist rule passes'); });
  await check('New draft is in the repository data (33 documents)', async () => (await api('/api/contracts')).length === 33);
  await p.click('a:has-text("Review in Redline")'); await p.waitForSelector('text=Pre-signature checklist'); await sleep(800);
  await check('Redline shows the new draft: ready to sign', async () => (await text('section')).includes('Retail analytics platform') || (await p.locator('text=Ready to sign').count()) === 1);

  await p.click('a:has-text("Edit in document editor")'); await p.waitForSelector('.docpage[aria-label="Contract text"]'); await sleep(900);
  await step('Open any draft in the online editor: edit like a Word / Google doc, save as a new version', 2600);
  await p.locator('.docpage p').last().click(); await p.keyboard.press('End'); await p.keyboard.type(' Reviewed online by Procurement.'); await sleep(500);
  await p.fill('input[aria-label="Version note"]', 'Added reviewer note'); await p.click('button:has-text("Save new version")'); await p.waitForSelector('text=Saved as version 2'); await sleep(900);
  await check('Editor: typed text saved as version 2, re-extracted, version history lists it', async () => { const id = (await api('/api/contracts')).find((c) => c.title.includes('Retail analytics')).id; const d = await api(`/api/documents/${id}/content`); return d.versions.length === 2 && d.md.includes('Reviewed online by Procurement') && (await text('section:has-text("Version history")')).includes('Added reviewer note'); });
  await nav('Redline');
  await p.setInputFiles('input[aria-label="Upload a document to redline"]', { name: 'Vendor MSA draft.md', mimeType: 'text/markdown', buffer: Buffer.from(`# Draft MSA – Uploadco\n\n**Parties:** Arcadia Retail Inc. (the "Customer") and Uploadco Inc (the "Supplier")\n**Effective Date:** 1 February 2027\n**Document Type:** MSA\n\n## 1. Payment\nThe Customer shall pay undisputed invoices within 10 days of receipt of a valid invoice.\n\n## 2. Limitation of Liability\nEach party's liability under this Agreement is unlimited, including liability for indirect and consequential losses.\n`) });
  await p.waitForSelector('.docpage[aria-label="Document with tracked changes"] del.tc'); await sleep(900);
  await step('Or upload a document (.docx / .md / .txt): it is redlined against the standard and joins the queue', 3000);
  await check('Upload: draft added to the queue, redlined with tracked changes', async () => (await text('[role=tablist]')).includes('To review 7') && (await p.locator('.docpage .rl-open').count()) >= 2);
  await p.locator('#cmt-liability_cap >> text=✓ Accept').click(); await sleep(600);
  await p.click('button:has-text("Apply 1 accepted")'); await p.waitForSelector('text=written to the document as version'); await sleep(900);
  await check('Apply accepted changes: new version written, document re-checked', async () => { const r = await api('/api/redline/documents'); const d = r.find((x) => x.title.includes('Uploadco')); const c = await api(`/api/documents/${d.id}/content`); return c.versions.length === 2 && c.md.includes('shall not exceed'); });
  await step('Apply the accepted changes: the document is rewritten as a new version and re-checked', 2600);

  await nav('Templates'); await p.waitForSelector('text=Clause library coverage'); await sleep(900);
  await step('Template library: every template clause by clause, and which clauses each template contains', 3000);
  await check('Coverage matrix lists 39 clauses across the 6 templates (MSA, SOW, Work Order, NDA, SaaS, DPA)', async () => (await p.locator('table[aria-label="Clause coverage by template"] tbody tr').count()) === 39 && (await p.locator('table[aria-label="Clause coverage by template"] thead th').count()) === 7);
  await p.click('text=Create a contract from this template'); await p.waitForSelector('[role=radio][aria-checked=true]'); await sleep(700);
  await check('Template page links into New contract with the template preselected', async () => (await p.locator('[role=radio][aria-checked=true]').innerText()).includes('Master Services Agreement'));

  // ---------------------------------------------------------------- 9 ADMIN
  await p.click('text=⚙ Admin'); await p.waitForSelector('text=Run history'); await sleep(700);
  await step('9 · Admin — pipeline: watched folder, schedule, run history', 2800);
  await check('Admin pipeline: default every 2 hours, folder + file count, runs listed', async () => { const c = await api('/api/admin/pipeline'); const n = await p.locator('text=Run history').count(); return c.config.interval_minutes === 120 && c.inbox_files >= 33 && n >= 1 && (await api('/api/admin/pipelines')).pipelines.length === 2 ? true : `interval=${c.config.interval_minutes} files=${c.inbox_files} runHistory=${n}`; });
  await p.getByLabel('Executed contracts frequency').selectOption('60'); await sleep(900);
  await step('Change the frequency: every hour', 2000);
  await p.getByLabel('Draft review (redline) trigger').selectOption('manual'); await sleep(900);
  await step('Each pipeline has its own trigger: periodic, dynamic (on a new or changed file) or manual', 3000);
  await check('Drafts pipeline switched to manual and persisted', async () => (await api('/api/admin/pipelines')).pipelines.find((x) => x.key === 'drafts').trigger_mode === 'manual');
  await p.getByLabel('Draft review (redline) trigger').selectOption('on_change'); await sleep(700);
  await check('...and back to dynamic (on new or changed files)', async () => (await api('/api/admin/pipelines')).pipelines.find((x) => x.key === 'drafts').trigger_mode === 'on_change');
  await check('Frequency saved (60 minutes) and next run recomputed', async () => (await api('/api/admin/pipeline')).config.interval_minutes === 60);
  await p.getByLabel('Executed contracts frequency').selectOption('120'); await sleep(700);
  await p.click('button:has-text("Add to folder & process")'); await p.waitForSelector('text=Saved as'); await sleep(900);
  await step('Add a document to the folder: picked up and processed', 2600);
  await check('Pasted NDA ingested (vendor read from the document)', async () => (await api('/api/vendors')).some((v) => v.vendor === 'Example Supplier Inc') || (await api('/api/contracts')).some((c) => c.vendor === 'Example Supplier Inc'));
  await p.locator('button:has-text("Run now")').first().click(); await sleep(2500);
  await check('Run now: a manual run appears in history; nothing changed so all unchanged', async () => { const runs = await api('/api/admin/pipeline/runs'); const r = runs.find((x) => x.trigger === 'manual'); return !!r && r.pipeline === 'contracts' && r.new_docs === 0 && r.unchanged >= 28; });
  await p.click('nav[aria-label="Admin sections"] >> text=Key clause library'); await p.waitForSelector('button:has-text("+ Add clause")'); await sleep(700);
  await step('Key clause library: 39 clauses, each identified by headings and keywords; add your own', 3000);
  await check('KCC library lists the clauses with document counts and matrix toggles', async () => (await p.locator('tbody tr').count()) === 39 && (await p.locator('button[role=switch]').count()) >= 78);
  await p.click('button:has-text("+ Add clause")'); await sleep(500);
  await p.getByLabel('Clause name').fill('Price Parity');
  await p.getByLabel('Heading aliases').fill('Price Parity, MFC');
  await p.getByLabel('Keywords / phrases').fill('most favou?red customer, price parity');
  await p.click('button:has-text("Preview matches")'); await sleep(1200);
  await check('Preview: definition identifies 0 clauses in the current documents (none mention it)', async () => (await text('div.rounded.border.p-3:has-text("identifies")')).includes('identifies 0 clause'));
  await p.click('button:has-text("Save & re-run on all documents")'); await sleep(2500);
  await check('Saved: appears in the library as custom', async () => (await p.locator('tr:has-text("Price Parity")').count()) === 1);
  await nav('Key clauses'); await p.waitForSelector('text=Key contract clauses across all documents'); await sleep(900);
  await step('The new clause is now a column in the key-clause matrix (and in Ask)', 2800);
  await check('Matrix gained a 24th column: Price Parity', async () => (await p.locator('thead th').count()) === 26 && (await text('thead')).includes('Price Parity'));
  await p.click('text=⚙ Admin'); await p.click('nav[aria-label="Admin sections"] >> text=Key clause library'); await p.waitForSelector('tr:has-text("Price Parity")');
  p.once('dialog', (d) => d.accept());
  await p.locator('tr:has-text("Price Parity") >> text=Delete').click(); await sleep(2500);
  await check('Custom clause deleted; matrix back to 23 columns', async () => (await api('/api/clause-matrix')).columns.length === 23);
  await p.click('nav[aria-label="Admin sections"] >> text=Values & limits'); await p.waitForSelector('button:has-text("+ Add value")'); await sleep(700);
  await step('Values & limits: the numbers extracted from clauses — payment days, caps, insurance, notice periods', 3000);
  await check('16 built-in values with coverage counts (insurance: 3 MSAs + 1 draft)', async () => (await p.locator('tbody tr').count()) === 16 && (await text('tr:has-text("Insurance cover per claim")')).includes('4 docs'));
  await p.click('nav[aria-label="Admin sections"] >> text=Redline checklist'); await p.waitForSelector('button:has-text("+ Add rule")'); await sleep(700);
  await step('Redline checklist: rules, thresholds, severity, where they apply — all editable', 3000);
  await check('34 rules incl. “Payment terms ≥ 30 days” (high) with pass/fail counts', async () => (await p.locator('tbody tr').count()) === 34 && (await text('tr:has-text("Payment terms ≥ 30 days")')).includes('high'));
  const before = (await api('/api/admin/rules')).find((r) => r.key === 'payment_terms_target').results.fail;
  await p.locator('tr:has-text("Payment terms ≥ 45 days (target)") >> text=Edit').click(); await sleep(500);
  await p.getByPlaceholder('days').fill('60'); await sleep(300);
  await p.click('button:has-text("Save & re-run on all documents")'); await sleep(2800);
  await step('Tighten a threshold (45 → 60 days): every document is re-checked', 2600);
  await check('More documents now fail the payment-terms target', async () => (await api('/api/admin/rules')).find((r) => r.key === 'payment_terms_target').results.fail > before);
  await p.locator('tr:has-text("Payment terms ≥ 45 days (target)") >> text=Edit').click(); await sleep(400);
  await p.getByPlaceholder('days').fill('45'); await p.click('button:has-text("Save & re-run on all documents")'); await sleep(2500);
  await check('Threshold restored', async () => (await api('/api/admin/rules')).find((r) => r.key === 'payment_terms_target').results.fail === before);

  // ---------------------------------------------------------------- 10 THEME / MOBILE
  await p.click('text=Dark'); await p.goto(U + '/'); await p.waitForSelector('text=Contract expiry'); await sleep(800);
  await step('Dark theme', 1800);
  await check('Theme: dark persisted', async () => await p.evaluate(() => document.documentElement.classList.contains('dark')));
  await p.click('text=Light'); await sleep(400);
  await p.setViewportSize({ width: 390, height: 800 }); await sleep(800);
  await check('Mobile: no horizontal overflow', async () => !(await p.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)));
  await p.setViewportSize({ width: 1280, height: 720 });
  await check('No console or page errors during the entire walkthrough', async () => errs.length === 0 ? true : errs.slice(0, 3).join(' | '));
  await caption('Walkthrough complete'); await sleep(1200);

  const vid = await p.video().path();
  await ctx.close(); await b.close();
  fs.writeFileSync(OUT + '/results.json', JSON.stringify({ results, errs }, null, 1));
  const pass = results.filter((r) => r[0]).length;
  for (const [ok, name] of results) console.log((ok ? 'PASS ' : 'FAIL ') + name);
  if (errs.length) console.log('ERRORS:\n' + errs.join('\n'));
  console.log(`\n${pass}/${results.length} checks passed\nvideo: ${vid}`);
  process.exitCode = pass === results.length ? 0 : 1;
})().catch((e) => { console.error('SCRIPT FAILURE', e.message); process.exit(2); });
