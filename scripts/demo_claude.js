// Live Claude demo of the Ask chat: demo mode OFF, so every question goes to Claude (subscription or API key).
// Usage: NODE_PATH=$(npm root -g) node scripts/demo_claude.js [outDir]   (api :8000 with a Claude provider, web :5173)
const { chromium } = require('playwright');
const fs = require('fs');
const OUT = process.argv[2] || '/tmp/demo-claude';
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
  await caption('1 · Which vendors have uncapped liability?'); await ask('Which vendors have uncapped liability?', '1_uncapped');
  await caption('2 · Aggregate: headline tiles, a group-by table, then the list'); await ask('How many contracts does each vendor have, and what is the total annual value per vendor?', '2_aggregate');
  await sleep(2500);
  await caption('3 · A follow-up in the same conversation — Claude sees the earlier turns'); await ask('Now only the vendors with auto-renewing contracts', '3_followup');
  await sleep(2500);
  await p.click('button:has-text("+ New chat")');
  await p.click('[role=radio]:has-text("Selected documents")');
  await p.fill('input[aria-label="Search documents"]', 'delmont'); await sleep(500);
  await p.locator('ul[aria-label="Documents"] label:has-text("Master Services Agreement – Delmont") input').check(); await sleep(500);
  await caption('4 · Ask about one selected document: Claude reads only that contract'); await ask('What does the indemnity clause say, and who signed this contract?', '4_scoped');
  await sleep(2500);
  console.log('badge:', badge);
  const page = await p.video().path();
  await ctx.close(); await b.close(); console.log('video:', page);
})();
