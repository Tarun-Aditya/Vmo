// Live Claude demo of the VMO-depth questions in the Ask chat: demo mode OFF, so every question goes to Claude (subscription or API key).
// Usage: NODE_PATH=$(npm root -g) node scripts/demo_claude.js [outDir]   (api :8000 with a Claude provider, web :5173)
const { chromium } = require('playwright');
const fs = require('fs');
const OUT = process.argv[2] || '/tmp/demo-claude-vmo';
const U = 'http://localhost:5173';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1280, height: 800 }, recordVideo: { dir: OUT, size: { width: 1280, height: 800 } } });
  const p = await ctx.newPage();
  const caption = (t) => p.evaluate((t) => { let el = document.getElementById('__cap'); if (!el) { el = document.createElement('div'); el.id = '__cap';
    el.style.cssText = 'position:fixed;left:50%;bottom:84px;pointer-events:none;transform:translateX(-50%);z-index:99999;background:rgba(15,23,42,.93);color:#fff;padding:10px 20px;border-radius:10px;font:600 16px system-ui;max-width:90%;text-align:center'; document.body.appendChild(el); } el.textContent = t; }, t);
  const settled = (n) => p.waitForFunction((k) => document.querySelectorAll('[data-msg="assistant"]').length > k && !document.querySelector('[data-streaming]'), n, { timeout: 180000 });
  const ask = async (q, shot) => {
    const n = await p.locator('[data-msg="assistant"]').count();
    await p.fill('form input', q); await p.click('form button:has-text("Ask")');
    await p.waitForSelector('[data-thinking="live"]'); await sleep(2500); await p.screenshot({ path: `${OUT}/${shot}_live.png` });
    await settled(n); await sleep(1200);
    await p.locator('[data-msg="assistant"]').last().scrollIntoViewIfNeeded(); await p.screenshot({ path: `${OUT}/${shot}.png` });
  };
  await p.goto(U + '/ask'); await p.waitForSelector('text=Ask your vendor portfolio'); await sleep(800);
  const badge = await p.locator('header span.rounded.text-xs, span.rounded.px-2.py-0\\.5.text-xs').first().innerText().catch(() => '');
  await p.locator('label:has-text("Demo mode") input').uncheck();                    // no cache: every answer is produced live
  await caption('Claude live (demo mode off): every question goes to the model, which writes SQL over the extracted data'); await sleep(2500);
  await caption('1 · Which obligations are overdue, and which contract does each belong to?'); await ask('Which obligations are overdue, and which contract does each belong to?', '1_overdue');
  await caption('2 · Spend vs contract: billed per vendor and the exceptions'); await ask('How much has each vendor billed us, and how much of that is flagged as a spend exception?', '2_spend');
  await sleep(2500);
  await caption('3 · Follow-up: vendor risk, using the earlier answer as context'); await ask('Which of those vendors have the highest risk score and what drives it?', '3_risk');
  await sleep(2500);
  await p.click('button:has-text("+ New chat")');
  await p.click('[role=radio]:has-text("Selected documents")');
  await p.fill('input[aria-label="Search documents"]', 'delmont'); await sleep(500);
  await p.locator('ul[aria-label="Documents"] label:has-text("Master Services Agreement – Delmont") input').check(); await sleep(500);
  await caption('4 · Ask about one selected contract: its obligations'); await ask('What obligations does the supplier have under this contract, and by when?', '4_scoped');
  await sleep(2500);
  console.log('badge:', badge);
  const page = await p.video().path();
  await ctx.close(); await b.close(); console.log('video:', page);
})();
