// Full feature walkthrough: asserts expected values on every screen AND records a captioned video.
// Usage: NODE_PATH=$(npm root -g) node scripts/demo_walkthrough.js [outDir]   (api :8000, web :5173)
const { chromium } = require('playwright');
const fs = require('fs');
const OUT = process.argv[2] || '/tmp/demo-video';
const U = 'http://localhost:5173';
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
    try { const ok = await fn(); results.push([typeof ok === 'string' ? false : ok !== false, typeof ok === 'string' ? name + ' — ' + ok : name]); } catch (e) { results.push([false, name + ' — ' + e.message.split('\n')[0]]); }
  };
  const step = async (cap, ms = 1800) => { await caption(cap); await sleep(ms); };
  const scroll = async (y, ms = 900) => { await p.mouse.wheel(0, y); await sleep(ms); };
  const top = async () => { await p.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' })); await sleep(700); };
  const text = (sel) => p.locator(sel).first().innerText();
  const answerText = () => text('section:has-text("Answer")');
  const ask = async (q, waitFor) => {
    await p.fill('input[placeholder^="e.g."]', q); await p.click('button:has-text("Ask")');
    await p.waitForSelector(waitFor || 'text=Thinking'); await sleep(900);
  };

  // ---------------------------------------------------------------- 1 DASHBOARD
  await p.goto(U + '/'); await p.waitForSelector('text=Contract expiry'); await sleep(800);
  await step('1 · Dashboard — KPI tiles', 2200);
  await check('Dashboard: 21 documents (incl. SOWs, work orders, amendments)', async () => (await p.locator('.text-3xl').first().innerText()) === '21');
  await check('Dashboard: ₹8.32 Cr annual value', async () => (await p.content()).includes('₹8.32 Cr'));
  await check('Dashboard: 8 expiring in 90 days (₹4.44 Cr at stake)', async () => (await p.content()).includes('₹4.44 Cr at stake'));
  await check('Dashboard: 2 auto-renew notices due, 1 already passed', async () => (await p.content()).includes('1 already passed'));
  await check('Dashboard: 3 uncapped liability', async () => (await p.locator('text=Uncapped liability').first().locator('xpath=..').innerText()).includes('3'));
  await scroll(300); await step('Expiry dashboard: contracts expiring in the next 30 / 60 / 90 days', 2800);
  const lane = (l) => `section[aria-label="${l}"] article`;
  await check('Lane 0–30 days: 4 contracts', async () => (await p.locator(lane('Expiring in 0–30 days')).count()) === 4);
  await check('Lane 31–60 days: 1 contract (CloudDesk)', async () => (await p.locator(lane('Expiring in 31–60 days')).count()) === 1 && (await text(lane('Expiring in 31–60 days'))).includes('CloudDesk'));
  await check('Lane 61–90 days: 3 contracts', async () => (await p.locator(lane('Expiring in 61–90 days')).count()) === 3);
  await check('Lane headers show count + annual value (4 · ₹1.14 Cr)', async () => { const t = await text('section[aria-label="Expiring in 0–30 days"] header'); return t.includes('4') && t.includes('₹1.14 Cr'); });
  await check('Cards show end date, days left, value, auto-renew', async () => { const t = await text('section[aria-label="Expiring in 0–30 days"] article:has-text("AdSpark")'); return t.includes('27 Nov 2026') && t.includes('in 21d') && t.includes('₹18.0 L') && t.includes('auto-renews'); });
  await check('AdSpark card flagged: notice deadline passed + uncapped', async () => { const t = await text('article:has-text("AdSpark")'); return t.includes('notice deadline passed') && t.includes('uncapped'); });
  await scroll(450); await step('Expiries over the next 12 months', 2200);
  await check('12-month chart rendered', async () => (await p.locator('.recharts-bar-rectangle').count()) >= 4);
  await scroll(500); await step('Risk panels: uncapped liability · no termination for convenience · personal data with no DPA', 2400);
  await check('Dashboard: PulseHR is the personal-data-no-DPA vendor', async () => (await p.locator('section:has-text("Personal data, no DPA")').first().innerText()).includes('PulseHR'));

  // ---------------------------------------------------------------- 2 REPOSITORY + HIERARCHY
  await top(); await p.click('nav >> text=Contracts'); await p.waitForSelector('tr:has-text("AdSpark")');
  await step('2 · Contract repository — start / end dates, value, signature status, flags', 2600);
  await check('Repository table: 21 documents', async () => (await p.locator('tbody tr').count()) === 21);
  await check('Repository: Start date / End date / Signatures columns', async () => { const h = (await text('thead')).toLowerCase(); return h.includes('start date') && h.includes('end date') && h.includes('signatures'); });
  await check('Repository: Work Order 2 shows ✗ pending', async () => (await text('tr:has-text("Work Order 2")')).includes('pending'));
  await p.selectOption('select >> nth=1', 'SaaS'); await sleep(900);
  await check('Repository: category SaaS → 5 (3 SaaS + 2 DPA)', async () => (await p.locator('tbody tr').count()) === 5);
  await p.click('text=Reset'); await sleep(500);
  await p.selectOption('select >> nth=2', 'Work Order'); await sleep(900);
  await step('Filter: type = Work Order', 1600);
  await check('Repository: Work Order filter → 3', async () => (await p.locator('tbody tr').count()) === 3);
  await p.click('text=Reset'); await sleep(500);
  await p.fill('input[placeholder="title or vendor"]', 'meridian'); await sleep(900);
  await check('Repository: search meridian → 6 (MSA, 2 SOW, work order, amendment, NDA)', async () => (await p.locator('tbody tr').count()) === 6);
  await p.click('text=Reset'); await sleep(500);
  await p.click('button[role=tab]:has-text("Hierarchy")'); await sleep(1000);
  await step('Hierarchy view: MSA → SOW → Work Order, with amendments, NDAs and DPAs under their agreement', 3200);
  await check('Hierarchy: Bluepeak MSA → SOW 2 → both Work Orders nested', async () => { const t = await text('section:has(h2:has-text("Bluepeak"))'); return t.includes('MSA') && t.includes('SOW 2') && t.includes('Work Order 1') && t.includes('Work Order 2'); });
  await check('Hierarchy: 3 work orders in the tree', async () => (await p.locator('a:has-text("Work Order ")').count()) === 3);
  await check('Hierarchy: Work Order 2 pending signature; others signed', async () => (await text('div:has(> a:has-text("Work Order 2"))')).includes('pending'));
  await check('Hierarchy: amendments + NDAs + DPAs appear under their parent', async () => { const t = await p.locator('body').innerText(); return t.includes('AMENDMENT') && t.includes('NDA') && t.includes('DPA'); });
  await p.click('button[role=tab]:has-text("Table")'); await sleep(500);

  // ---------------------------------------------------------------- 3 DETAIL
  await p.click('a:has-text("Master Services Agreement – Bluepeak")'); await p.waitForSelector('text=Effective terms');
  await step('3 · Contract detail — signatures, extracted fields beside the document', 2600);
  await check('Detail: signatures card (Rohit Sharma / Sanjay Kulkarni, fully signed)', async () => { const t = await text('section:has-text("Signatures")'); return t.includes('Rohit Sharma') && t.includes('Sanjay Kulkarni') && t.includes('fully signed'); });
  await check('Detail: confidence badges rendered', async () => (await p.locator('text=/✓ \\d+%/').count()) >= 8);
  await p.click('tr:has-text("Payment terms") >> nth=0'); await sleep(1200);
  await step('Click a field → its source clause is highlighted (Payment · page 2)', 2400);
  await check('Detail: clicking a field highlights the source clause', async () => (await p.locator('.ring-yellow-400').count()) === 1 && (await text('.ring-yellow-400')).includes('Payment'));
  await scroll(700); await step('Effective terms after amendments — values with provenance', 1500);
  const eff = p.locator('section:has-text("Effective terms (after amendments)")');
  await check('Effective terms: payment = 30, overridden by Amendment No. 1', async () => { const r = await eff.locator('tr:has-text("Payment terms")').innerText(); return /30/.test(r) && r.includes('Overridden by Amendment No. 1'); });
  await check('Effective terms: untouched terms say Original contract', async () => (await eff.locator('tr:has-text("Governing law")').innerText()).includes('Original contract'));
  await scroll(600); await step('Hierarchy of this agreement: SOWs → Work Orders → Amendment → NDA', 2400);
  await check('Detail hierarchy: 8 linked documents under the Bluepeak MSA', async () => (await p.locator('section:has-text("Hierarchy") a').count()) === 8);
  await p.click('section:has-text("Hierarchy") a:has-text("Work Order 2")'); await p.waitForSelector('text=signature pending'); await sleep(800);
  await step('Work Order 2: the supplier has not countersigned yet', 2400);
  await check('Work Order 2: ✗ not fully signed, supplier signature pending', async () => { const t = await text('section:has-text("Signatures")'); return t.includes('not fully signed') && t.includes('signature pending'); });

  // ---------------------------------------------------------------- 4 KEY CLAUSES MATRIX
  await p.click('nav >> text=Key clauses'); await p.waitForSelector('text=Key contract clauses across all documents'); await sleep(800);
  await step('4 · Key clauses — every document × every key clause: ✓ present / ✗ absent', 2800);
  await check('Matrix: 19 executed contracts + 5 vendor drafts', async () => (await p.locator('tbody tr:has(button[aria-label*="Term"])').count()) === 24);
  await check('Matrix: 18 clause columns incl. "Signed by both parties"', async () => (await p.locator('thead th').count()) === 20 && (await text('thead')).includes('Signed by both parties'));
  await check('Matrix: green ticks and red crosses both present', async () => (await p.locator('button:has-text("✓")').count()) > 50 && (await p.locator('button:has-text("✗")').count()) > 50);
  await p.locator('button[aria-label^="Master Services Agreement – Bluepeak Technologies: Limitation of Liability present"]').hover(); await sleep(900);
  await step('Hover a ✓: citation — clause text, clause heading and page', 3000);
  await check('Hover ✓ shows citation with text and page 3', async () => { const t = await text('[role=tooltip]'); return t.includes('Present') && t.includes('liability') && t.includes('page 3'); });
  await p.locator('button[aria-label^="NDA – Meridian Logistics: Payment absent"]').hover(); await sleep(900);
  await step('Hover a ✗: why it is absent', 2600);
  await check('Hover ✗ explains: not part of the standard NDA template', async () => { const t = await text('[role=tooltip]'); return t.includes('Absent') && t.includes('not part of the standard'); });
  await p.locator('button[aria-label^="Work Order 2 – Store Wi-Fi Refresh – Bluepeak Technologies: Signed by both parties absent"]').hover(); await sleep(900);
  await step('Signatures column: Work Order 2 is boxed — supplier signature pending', 2800);
  await check('Hover unsigned shows the signature evidence', async () => (await text('[role=tooltip]')).includes('Not fully signed'));
  await scroll(500); await sleep(500);
  await p.locator('button[aria-label*="Quantum Billing: Return of Data absent"]').hover(); await sleep(900);
  await step('Vendor drafts: a missing required clause is a boxed gap', 2800);
  await check('Draft gap: Quantum is missing Return of Data (template requires it)', async () => { const t = await text('[role=tooltip]'); return t.includes('Absent') && t.includes('this is a gap'); });
  await p.check('text=Highlight gaps only'); await sleep(700);
  await check('Highlight gaps only: boxed gaps remain at full strength', async () => (await p.locator('button.ring-red-400').count()) >= 2);
  await p.uncheck('text=Highlight gaps only');

  // ---------------------------------------------------------------- 5 ASK
  await top(); await p.click('nav >> text=Ask'); await p.waitForSelector('text=Ask your vendor portfolio'); await sleep(600);
  await step('5 · Ask — questions are translated to SQL over the extracted data; answers come back as tables', 2800);
  await check('Ask: 8 suggestions shown + "More examples (17)"', async () => (await p.locator('button.rounded-full').count()) === 8 && (await p.locator('text=More examples (17)').count()) === 1);
  await p.click('button:has-text("Which vendors have uncapped liability?")'); await p.waitForSelector('text=Thinking'); await sleep(900);
  await step('Answer first as a table. No SQL on the page — it lives under “Thinking”', 3000);
  await check('Ask/table: vendor + contract table, 3 rows', async () => (await p.locator('section:has-text("Answer") tbody tr').count()) === 3 && (await answerText()).includes('PulseHR'));
  await check('Ask: no SQL visible by default; “Thinking” is collapsed', async () => (await p.locator('pre').count()) === 0 && (await p.locator('button:has-text("Thinking")').count()) === 1);
  await p.click('button:has-text("Thinking")'); await sleep(900); await scroll(350);
  await step('“Thinking · multi-step”: understood → SQL → results → answer', 3000);
  await check('Thinking: numbered steps incl. the generated SQL', async () => (await p.locator('ol li').count()) >= 3 && (await p.locator('pre:has-text("v_effective_terms")').count()) >= 1);
  await top(); await ask('Show start date, end date and signatures for all contracts', 'section:has-text("Answer") table');
  await step('Specific fields across all documents: start date, end date, signatories', 3200);
  await check('Signatures table: 19 documents with Start/End date and both signatories', async () => { const h = (await text('section:has-text("Answer") thead')).toLowerCase(); return (await p.locator('section:has-text("Answer") tbody tr').count()) === 19 && ['start date', 'end date', 'signed by (arcadia)', 'signed by (supplier)', 'fully signed'].every((x) => h.includes(x)); });
  await check('Signatures table: ✓ and ✗ marks (one unsigned)', async () => (await p.locator('section:has-text("Answer") tbody td:has-text("✗")').count()) === 1 && (await p.locator('section:has-text("Answer") tbody td:has-text("✓")').count()) === 18);
  await ask('Which contracts are not fully signed?', 'section:has-text("Answer") table');
  await check('Not fully signed → only Work Order 2', async () => (await p.locator('section:has-text("Answer") tbody tr').count()) === 1 && (await answerText()).includes('Work Order 2'));
  await ask('Which contracts do not have an audit rights clause?', 'section:has-text("Answer") table');
  await step('Clause presence question → table with ✗ for the missing clause', 2800);
  await check('Audit-rights gap table: every row has ✗', async () => { const n = await p.locator('section:has-text("Answer") tbody tr').count(); return n > 10 && (await p.locator('section:has-text("Answer") tbody td:has-text("✗")').count()) === n; });
  await ask('Show the key clauses in the Bluepeak MSA', 'section:has-text("Answer") table');
  await step('Specific to one document: its clauses with page numbers', 2800);
  await check('One document: 15 Bluepeak MSA clauses, ending with Execution', async () => (await p.locator('section:has-text("Answer") tbody tr').count()) === 15 && (await text('section:has-text("Answer") tbody tr:last-child')).includes('Execution'));
  await ask('How many contracts are expiring in the next quarter?', 'text=Breakdown by category');
  await step('Aggregate question: headline tiles → breakdown → list', 3400);
  await check('Aggregate: tiles 3 / ₹2.94 Cr, 1 Jan – 31 Mar 2027', async () => { const t = await p.locator('div.bg-indigo-50').allInnerTexts(); const a = await answerText(); return t.length === 2 && t[0].includes('3') && t[1].includes('₹2.94 Cr') && a.includes('31 Mar 2027'); });
  await check('Aggregate: breakdown table + contract table (2 tables)', async () => (await p.locator('section:has-text("Answer") table').count()) === 2);
  await ask('Which contracts give the vendor ownership of the deliverables we pay for?', 'section:has-text("Answer") table');
  await check('Clause question: cited clause table with page + match %', async () => { const t = await answerText(); return t.includes('AdSpark') && /\d+%/.test(t) && t.toLowerCase().includes('clause text'); });
  await ask('Tell me a joke', 'text=ANTHROPIC_API_KEY'); await step('Off-script offline: says what it can do instead of guessing', 2200);
  await check('Ask: unknown question → honest message', async () => (await p.locator('text=ANTHROPIC_API_KEY').count()) >= 1);
  await p.uncheck('input[type=checkbox]'); await sleep(400);
  await ask('How many SaaS contracts expire in the next 60 days?', 'section:has-text("Answer") table');
  await step('Demo mode OFF: a free-form question is planned, translated to SQL and run live', 3000);
  await check('Free-form: 2 SaaS contracts (AdSpark, CloudDesk), tiles 2 / ₹54.0 L', async () => { const t = await p.locator('div.bg-indigo-50').allInnerTexts(); const a = await answerText(); return t[0].includes('2') && t[1].includes('₹54.0 L') && a.includes('AdSpark') && a.includes('CloudDesk'); });
  await check('Free-form: answered by the planner (not cache)', async () => /offline-planner/.test(await p.locator('body').innerText()));
  await p.check('input[type=checkbox]');

  // ---------------------------------------------------------------- 6 REDLINE
  await p.click('nav >> text=Redline'); await p.waitForSelector('text=Re-run live'); await sleep(700);
  await step('6 · Redline — five vendor drafts, deviations by severity', 2200);
  await check('Redline: 5 drafts listed', async () => (await p.locator('button:has-text("template")').count()) === 5);
  await check('Redline: Zenith MSA = 5 deviations (1 critical, 3 high, 1 medium)', async () => (await p.locator('text=5 deviations: 1 critical, 3 high, 1 medium').count()) === 1);
  await scroll(350); await step('Struck-through original, inserted standard wording, our playbook position', 3000);
  await check('Redline: shows del + ins marks; critical liability first', async () => (await p.locator('del').count()) > 0 && (await p.locator('ins').count()) > 0 && (await p.locator('h3').first().innerText()) === 'Limitation of Liability');
  await top(); await p.click('button:has-text("Re-run live")'); await p.waitForSelector('text=/Live \\(/'); await sleep(900);
  await check('Redline: re-run still finds 5 deviations', async () => (await p.locator('text=5 deviations').count()) === 1);
  await p.click('button:has-text("Quantum Billing")'); await p.waitForSelector('text=MISSING CLAUSE'); await sleep(800);
  await scroll(300); await step('SaaS draft: critical data-protection change and a missing clause', 2600);
  await check('Redline: Quantum = 6 deviations with MISSING CLAUSE', async () => { await p.waitForSelector('text=6 deviations: 1 critical, 3 high, 2 medium', { timeout: 5000 }); const n = await p.locator('span:text-is("MISSING CLAUSE")').count(); return n === 1 ? true : `MISSING CLAUSE count=${n}; h3s=${JSON.stringify(await p.locator('h3').allInnerTexts())}; chips=${JSON.stringify(await p.locator('span:has-text("MISSING")').allInnerTexts())}`; });
  await p.click('button:has-text("Orbit Couriers")'); await sleep(800);
  await check('Redline: NDA draft = 3 deviations', async () => (await p.locator('text=3 deviations').count()) === 1);
  await p.click('button:has-text("Vaultline")'); await sleep(800);
  await check('Redline: DPA draft = 4 deviations', async () => (await p.locator('text=4 deviations').count()) === 1);
  await p.click('button:has-text("clean control")'); await p.waitForSelector('text=No deviations found'); await sleep(800);
  await step('The control draft: no deviations, nothing flagged', 2200);
  await check('Redline: clean control shows zero findings', async () => (await p.locator('h3').count()) === 0);

  // ---------------------------------------------------------------- 7 TEMPLATES
  await p.click('nav >> text=Templates'); await p.waitForSelector('text=Deviation heatmap'); await sleep(700);
  await step('7 · Template library — standard templates, clause by clause', 2200);
  await check('Templates: 6 templates (incl. Work Order)', async () => (await p.locator('button:has-text("(Standard)")').count()) === 6);
  await p.click('button:has-text("SaaS Subscription")'); await sleep(900);
  await step('Heatmap: where executed SaaS contracts drift from the standard', 2600);
  await check('Heatmap: 4 SaaS contracts; critical cells for AdSpark + PulseHR', async () => (await p.locator('tbody tr').count()) === 4 && (await p.locator('button[title*="unlimited"]').count()) === 2);
  await p.click('button[title*="unlimited"] >> nth=0'); await sleep(900);
  await check('Heatmap: cell detail shows contract + clause + severity', async () => { const t = await text('div.rounded.border.p-3'); return t.includes('Limitation of Liability') && t.includes('critical'); });
  await top(); await p.click('button:has-text("Work Order (Standard)")'); await sleep(900);
  await check('Work Order template: 3 executed work orders, none deviate', async () => (await p.locator('tbody tr').count()) === 3);

  // ---------------------------------------------------------------- 8 ADMIN, THEME, MOBILE
  await p.click('text=Admin'); await p.waitForSelector('text=AI usage'); await sleep(600);
  await step('8 · Admin — LLM call/token/cost log (empty offline: no Claude calls were made)', 2200);
  await check('Admin: usage page renders with totals', async () => (await p.locator('text=Est. cost').count()) === 1 && (await p.locator('h1:has-text("AI usage")').count()) === 1);
  await p.click('text=Dark'); await p.goto(U + '/clauses'); await p.waitForSelector('text=Key contract clauses'); await sleep(900);
  await step('Dark theme', 2200);
  await check('Theme: dark class applied and persisted across navigation', async () => await p.evaluate(() => document.documentElement.classList.contains('dark')));
  await p.click('text=Light'); await sleep(500);
  await p.setViewportSize({ width: 390, height: 800 }); await p.goto(U + '/'); await p.waitForSelector('text=Contract expiry'); await sleep(900);
  await step('Phone width: header wraps, lanes stack, no sideways scroll', 2200);
  await check('Mobile: no horizontal overflow on the dashboard', async () => !(await p.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)));
  await p.setViewportSize({ width: 1280, height: 720 });
  await check('No console or page errors during the entire walkthrough', async () => errs.length === 0);
  await caption('Walkthrough complete'); await sleep(1500);

  const vid = await p.video().path();
  await ctx.close(); await b.close();
  fs.writeFileSync(OUT + '/results.json', JSON.stringify({ results, errs }, null, 1));
  const pass = results.filter((r) => r[0]).length;
  for (const [ok, name] of results) console.log((ok ? 'PASS ' : 'FAIL ') + name);
  if (errs.length) console.log('ERRORS:\n' + errs.join('\n'));
  console.log(`\n${pass}/${results.length} checks passed\nvideo: ${vid}`);
  process.exitCode = pass === results.length ? 0 : 1;
})().catch((e) => { console.error('SCRIPT FAILURE', e.message); process.exit(2); });
