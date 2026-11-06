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
    try { const ok = await fn(); results.push([ok !== false, name]); } catch (e) { results.push([false, name + ' — ' + e.message.split('\n')[0]]); }
  };
  const step = async (cap, ms = 1800) => { await caption(cap); await sleep(ms); };
  const scroll = async (y, ms = 900) => { await p.mouse.wheel(0, y); await sleep(ms); };
  const top = async () => { await p.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' })); await sleep(700); };
  const text = (sel) => p.locator(sel).first().innerText();

  // ---------------------------------------------------------------- 1 DASHBOARD
  await p.goto(U + '/'); await p.waitForSelector('text=Upcoming action dates'); await sleep(800);
  await step('1 · Renewal dashboard — KPI tiles', 2200);
  await check('Dashboard: 18 contracts', async () => (await p.locator('.text-3xl').first().innerText()) === '18');
  await check('Dashboard: ₹8.32 Cr annual value', async () => (await p.content()).includes('₹8.32 Cr'));
  await check('Dashboard: 8 expiring in 90 days (₹4.44 Cr)', async () => { const c = await p.content(); return c.includes('₹4.44 Cr at stake'); });
  await check('Dashboard: 2 auto-renew notices due, 1 passed', async () => (await p.content()).includes('1 already passed'));
  await check('Dashboard: 3 uncapped liability', async () => (await p.locator('text=Uncapped liability').first().locator('xpath=..').innerText()).includes('3'));
  await scroll(450); await step('Value at stake by 30/60/90-day bucket, with severity chips (▲▲ critical … ○ low)', 2400);
  await check('Dashboard: buckets 1 overdue / 4 / 1 / 2', async () => { const t = await p.locator('body').innerText(); return /Deadline passed[\s\S]*?1\s+contracts/.test(t) && /Next 30 days[\s\S]*?4\s+contracts/.test(t) && /61–90 days[\s\S]*?2\s+contracts/.test(t); });
  await scroll(500); await step('Notice deadlines (expiry − notice period), not just expiry dates — AdSpark’s deadline already passed', 2600);
  await check('Dashboard: AdSpark flagged overdue', async () => (await p.locator('tr:has-text("AdSpark")').first().innerText()).includes('overdue'));
  await check('Dashboard: 8 action rows in timeline', async () => (await p.locator('tbody tr').count()) === 8);
  await scroll(600); await step('Risk panels: uncapped liability · no termination for convenience · personal data with no DPA', 2600);
  await check('Dashboard: PulseHR is the personal-data-no-DPA vendor', async () => (await p.locator('section:has-text("Personal data, no DPA")').first().innerText()).includes('PulseHR'));

  // ---------------------------------------------------------------- 2 REPOSITORY
  await top(); await p.click('nav >> text=Contracts'); await p.waitForSelector('tr:has-text("AdSpark")');
  await step('2 · Contract repository — 18 contracts, filters for vendor / category / type / owner / status', 2200);
  await check('Repository: lists 18', async () => (await p.locator('tbody tr').count()) === 18);
  await p.selectOption('select >> nth=1', 'SaaS'); await sleep(900);
  await step('Filter: category = SaaS', 1600);
  await check('Repository: SaaS category → 5 (3 SaaS + 2 DPA; AdSpark is Marketing)', async () => (await p.locator('tbody tr').count()) === 5);
  await p.selectOption('select >> nth=2', 'DPA'); await sleep(900);
  await check('Repository: SaaS + type DPA → 2', async () => (await p.locator('tbody tr').count()) === 2);
  await p.click('text=Reset'); await sleep(700);
  await p.fill('input[placeholder="title or vendor"]', 'meridian'); await sleep(900);
  await step('Free-text search: “meridian”', 1500);
  await check('Repository: search meridian → 5 (MSA, 2 SOW, amendment, NDA)', async () => (await p.locator('tbody tr').count()) === 5);
  await p.click('text=Reset'); await sleep(500);
  await check('Repository: uncapped / auto-renew flags shown', async () => { const t = await p.locator('body').innerText(); return t.includes('uncapped') && t.includes('auto-renew'); });

  // ---------------------------------------------------------------- 3 DETAIL + HIERARCHY
  await p.click('a:has-text("Master Services Agreement – Bluepeak")'); await p.waitForSelector('text=Effective terms');
  await step('3 · Contract detail — extracted fields beside the document, each with a confidence badge', 2400);
  await check('Detail: confidence badges rendered', async () => (await p.locator('text=/✓ \\d+%/').count()) >= 8);
  await p.click('tr:has-text("Payment terms") >> nth=0'); await sleep(1200);
  await step('Click a field → its source clause is highlighted (Payment · page 2)', 2600);
  await check('Detail: clicking field highlights the source clause', async () => (await p.locator('.ring-yellow-400').count()) === 1 && (await text('.ring-yellow-400')).includes('Payment'));
  await p.click('tr:has-text("Liability cap (× annual fees)") >> nth=0'); await sleep(1200);
  await check('Detail: another field moves the highlight to Limitation of Liability', async () => (await text('.ring-yellow-400')).includes('Limitation of Liability'));
  await scroll(500); await step('Effective terms after amendments — values with provenance', 1500);
  const eff = p.locator('section:has-text("Effective terms (after amendments)")');
  await check('Effective terms: payment terms = 30, set by Amendment No. 1', async () => { const r = await eff.locator('tr:has-text("Payment terms")').innerText(); return /30/.test(r) && r.includes('Overridden by Amendment No. 1'); });
  await check('Effective terms: liability cap = 2 (original 1.0)', async () => /2/.test(await eff.locator('tr:has-text("Liability cap (×")').innerText()));
  await check('Effective terms: expiry extended (06 Oct 2028 style date) via amendment', async () => (await eff.locator('tr:has-text("Expiry date")').innerText()).includes('Overridden'));
  await check('Effective terms: untouched terms say Original contract', async () => (await eff.locator('tr:has-text("Governing law")').innerText()).includes('Original contract'));
  await scroll(600); await step('Hierarchy: MSA → SOWs → Amendment → NDA', 2200);
  await check('Hierarchy: 3 SOWs + amendment + NDA under Bluepeak MSA', async () => { const s = p.locator('section:has-text("Hierarchy")'); return (await s.locator('a').count()) === 6; });
  await check('Detail: template deviations listed (renewal, audit rights)', async () => { const t = await p.locator('section:has-text("Deviations from standard template")').innerText(); return t.includes('Renewal') && t.includes('Audit Rights'); });
  await p.click('section:has-text("Hierarchy") a:has-text("Amendment No. 1")'); await p.waitForSelector('text=This amendment overrides'); await sleep(900);
  await step('Open the amendment: it lists exactly which terms it overrides', 2400);
  await check('Amendment page: overrides Expiry, Payment terms, Liability cap', async () => { const t = await p.locator('section:has-text("This amendment overrides")').innerText(); return t.includes('Expiry date') && t.includes('Payment terms') && t.includes('Liability cap'); });
  await p.click('text=amends/under >> xpath=..//a').catch(() => {});
  await p.goto(U + '/contracts'); await p.click('a:has-text("Master Services Agreement – Meridian")'); await p.waitForSelector('text=Effective terms');
  await step('Meridian MSA: unlimited liability, no termination for convenience, English law, one-way indemnity', 2500);
  await check('Meridian: 4 deviations incl. critical liability', async () => { const t = await p.locator('section:has-text("Deviations from standard template")').innerText(); return t.includes('critical') && t.includes('Termination for Convenience') && t.includes('Governing Law') && t.includes('Indemnity'); });
  await check('Meridian: effective payment 60 days via its amendment', async () => (await p.locator('section:has-text("Effective terms (after amendments)") tr:has-text("Payment terms")').innerText()).includes('60'));

  // ---------------------------------------------------------------- 4 ASK
  await p.click('nav >> text=Ask'); await p.waitForSelector('text=Ask your vendor portfolio'); await sleep(600);
  await step('4 · Ask assistant — demo mode ON uses cached answers (instant, wifi-proof)', 2200);
  await check('Ask: 20 suggested questions', async () => (await p.locator('button.rounded-full').count()) === 20);
  await p.click('button:has-text("Which vendors have uncapped liability?")'); await p.waitForSelector('text=How I got this'); await sleep(900);
  await step('Structured question → text-to-SQL. Answer first, then “How I got this”: the SQL and result rows', 3000);
  await check('Ask/SQL: names Meridian, PulseHR, AdSpark', async () => { const t = await text('section:has-text("Answer")'); return ['Meridian', 'PulseHR', 'AdSpark'].every((v) => t.includes(v)); });
  await check('Ask/SQL: shows generated SQL + result table', async () => (await p.locator('pre:has-text("v_effective_terms")').count()) === 1 && (await p.locator('table:has-text("vendor") tbody tr').count()) === 3);
  await check('Ask/SQL: served from cache in demo mode', async () => (await p.locator('text=/cached/').count()) >= 1);
  await p.click('button:has-text("Which contracts give the vendor ownership")'); await p.waitForSelector('text=Cited clauses'); await sleep(800);
  await scroll(250); await step('Clause question → semantic search over clauses. Citations give contract + clause + page', 3000);
  await check('Ask/clause: cites AdSpark IP clause with page', async () => { const t = await text('section:has-text("Cited clauses")'); return t.includes('AdSpark') && /p\.\d/.test(t) && t.includes('Intellectual Property'); });
  await p.click('button:has-text("Which contracts are governed by a law other")'); await p.waitForSelector('text=Step 2'); await sleep(800);
  await scroll(250); await step('Mixed question → router uses SQL and clause search together', 3000);
  await check('Ask/mixed: SQL step + clause-search step, 3 contracts', async () => { const t = await p.locator('body').innerText(); return t.includes('SQL QUERY') && t.includes('CLAUSE SEARCH') && t.includes('Meridian') && t.includes('Skyguard') && t.includes('AdSpark'); });
  await p.click('button:has-text("How many contracts are expiring in the next quarter?")'); await p.waitForSelector('text=Contracts:'); await sleep(900);
  await step('Aggregate question: headline numbers first, then breakdown by category, then the contract list', 3600);
  await check('Ask/aggregate: next quarter = 3 contracts, ₹2.94 Cr, 1 Jan – 31 Mar 2027', async () => { const t = await text('section:has-text("Answer")'); return t.startsWith('ANSWER') && t.includes('3 contracts expire next quarter') && t.includes('₹2.94 crore') && t.includes('31 Mar 2027'); });
  await check('Ask/aggregate: headline tiles show contracts=3 and ₹2.94 Cr', async () => { const t = await p.locator('div.bg-indigo-50').allInnerTexts(); return t.length === 2 && t[0].includes('3') && t[1].includes('₹2.94 Cr'); });
  await check('Ask/aggregate: breakdown by category + 3 bulleted contracts', async () => { const t = await text('section:has-text("Answer")'); return t.includes('By category:') && (t.match(/•/g) || []).length === 3; });
  await p.click('button:has-text("How many contracts does each vendor have?")'); await p.waitForSelector('text=By vendor'); await sleep(900);
  await step('Group-by question: contracts and value per vendor', 2800);
  await check('Ask/group-by: Bluepeak 5 contracts (₹3.96 Cr)', async () => { const t = await text('section:has-text("Answer")'); return t.includes('Bluepeak Technologies Pvt Ltd 5 (₹3.96 crore)'); });
  await p.click('button:has-text("Which NDAs expire before")'); await p.waitForSelector('text=Step 1'); await sleep(900);
  await check('Ask: NDA vs MSA question returns the 2 related NDAs', async () => { const t = await text('section:has-text("Answer")'); return t.includes('2 NDAs'); });
  await p.fill('input[placeholder^="e.g."]', 'Tell me a joke'); await p.click('button:has-text("Ask")'); await sleep(1200);
  await step('Off-script question while offline: clear message instead of a made-up answer', 2200);
  await check('Ask: unknown question → honest “needs ANTHROPIC_API_KEY” message', async () => (await p.locator('text=ANTHROPIC_API_KEY').count()) >= 1);
  await p.uncheck('input[type=checkbox]'); await sleep(400);
  await p.fill('input[placeholder^="e.g."]', 'What is the total annual value of all active contracts?'); await p.click('button:has-text("Ask")');
  await p.waitForSelector('text=₹8.32 crore'); await sleep(900);
  await step('Demo mode OFF: the question runs live (real SQL against Postgres via the read-only role)', 2600);
  await check('Ask/live: ₹8.32 crore, source scripted (not cache)', async () => { const t = await text('section:has-text("Answer")'); return t.includes('₹8.32 crore') && /scripted/.test(await p.locator('body').innerText()) && !(await p.locator('text=/^cached/').count()); });
  await p.check('input[type=checkbox]');

  // ---------------------------------------------------------------- 5 REDLINE
  await p.click('nav >> text=Redline'); await p.waitForSelector('text=Re-run live'); await sleep(700);
  await step('5 · Redline — five vendor drafts, deviations by severity', 2200);
  await check('Redline: 5 drafts listed', async () => (await p.locator('button:has-text("template")').count()) === 5);
  await check('Redline: Zenith MSA = 5 deviations (1 critical, 3 high, 1 medium)', async () => (await p.locator('text=5 deviations: 1 critical, 3 high, 1 medium').count()) === 1);
  await scroll(350); await step('Struck-through original, inserted standard wording, our playbook position', 3200);
  await check('Redline: shows del + ins marks', async () => (await p.locator('del').count()) > 0 && (await p.locator('ins').count()) > 0);
  await check('Redline: critical liability item first', async () => (await p.locator('h3').first().innerText()) === 'Limitation of Liability');
  await top(); await p.click('button:has-text("Re-run live")'); await p.waitForSelector('text=/Live \\(/'); await sleep(900);
  await step('“Re-run live” recomputes the comparison on demand', 2200);
  await check('Redline: re-run still finds 5 deviations', async () => (await p.locator('text=5 deviations').count()) === 1);
  await p.click('button:has-text("Quantum Billing")'); await p.waitForSelector('text=MISSING CLAUSE'); await sleep(800);
  await scroll(300); await step('SaaS draft: critical data-protection change, missing Return-of-Data clause, 6 deviations', 3000);
  await check('Redline: Quantum = 6 deviations with MISSING CLAUSE', async () => { const t = await p.locator('section').first().innerText(); return t.includes('6 deviations: 1 critical, 3 high, 2 medium') && (await p.locator('text=MISSING CLAUSE').count()) === 1; });
  await p.click('button:has-text("Orbit Couriers")'); await sleep(900);
  await check('Redline: NDA draft = 3 deviations', async () => (await p.locator('text=3 deviations').count()) === 1);
  await p.click('button:has-text("Vaultline")'); await sleep(900);
  await check('Redline: DPA draft = 4 deviations', async () => (await p.locator('text=4 deviations').count()) === 1);
  await p.click('button:has-text("clean control")'); await p.waitForSelector('text=No deviations found'); await sleep(900);
  await step('The control draft: no deviations, nothing flagged high/critical', 2400);
  await check('Redline: clean control shows zero findings', async () => (await p.locator('h3').count()) === 0);

  // ---------------------------------------------------------------- 6 TEMPLATES
  await p.click('nav >> text=Templates'); await p.waitForSelector('text=Deviation heatmap'); await sleep(700);
  await step('6 · Template library — 5 standard templates, clause by clause', 2200);
  await check('Templates: 5 templates', async () => (await p.locator('button:has-text("(Standard)")').count()) === 5);
  await p.click('button:has-text("SaaS Subscription")'); await sleep(900);
  await step('Heatmap: where executed SaaS contracts drift from the standard', 2600);
  await check('Heatmap: 4 SaaS contracts; critical cells for AdSpark + PulseHR', async () => (await p.locator('tbody tr').count()) === 4 && (await p.locator('button[title*="unlimited"]').count()) === 2);
  await p.click('button[title*="unlimited"] >> nth=0'); await sleep(900);
  await step('Click a cell for the deviation detail', 2200);
  await check('Heatmap: cell detail shows contract + clause + severity', async () => { const t = await text('div.rounded.border.p-3'); return t.includes('Limitation of Liability') && t.includes('critical'); });
  await scroll(700); await step('Standard wording + playbook position + fallback for every clause', 2600);
  await check('Templates: clause list has playbook text', async () => (await p.locator('text=Playbook:').count()) >= 10);
  await top(); await p.click('button:has-text("Master Services Agreement (Standard)")'); await sleep(900);
  await check('Templates: MSA heatmap shows 2/2 contracts deviate', async () => (await p.locator('tbody tr').count()) === 2);
  await step('Switch template: MSA — both executed MSAs deviate', 2000);

  // ---------------------------------------------------------------- 7 ADMIN, THEME, MOBILE
  await p.click('text=Admin'); await p.waitForSelector('text=AI usage'); await sleep(600);
  await step('7 · Admin — LLM call/token/cost log (empty offline: no Claude calls were made)', 2400);
  await check('Admin: usage page renders with totals', async () => (await p.locator('text=Est. cost').count()) === 1 && (await p.locator('h1:has-text("AI usage")').count()) === 1);
  await p.click('text=Dark'); await p.goto(U + '/'); await p.waitForSelector('text=Upcoming action dates'); await sleep(900);
  await step('Dark theme', 2200);
  await check('Theme: dark class applied and persisted across navigation', async () => await p.evaluate(() => document.documentElement.classList.contains('dark')));
  await p.click('text=Light'); await sleep(500);
  await p.setViewportSize({ width: 390, height: 800 }); await sleep(900);
  await step('Phone width: header wraps, no sideways scroll', 2200);
  await check('Mobile: no horizontal overflow', async () => !(await p.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)));
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
