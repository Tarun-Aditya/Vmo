// Demo smoke test: walks every screen of the demo script and fails on any console/page error.
// Usage: NODE_PATH=$(npm root -g) node scripts/demo_smoke.js   (needs api on :8000 and web on :5173)
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1400, height: 900 }, deviceScaleFactor: 1 });
  const errs = [];
  p.on('pageerror', e => errs.push('PAGEERROR ' + e.message));
  p.on('console', m => { if (m.type() === 'error') errs.push('CONSOLE ' + m.text()); });
  const shot = async (n) => { await p.waitForTimeout(700); require('fs').mkdirSync('/tmp/demo-shots',{recursive:true}); await p.screenshot({ path: `/tmp/demo-shots/${n}.png`, fullPage: true }); };
  await p.goto('http://localhost:5173/'); await p.waitForSelector('text=Upcoming action dates'); await shot('dashboard');
  await p.goto('http://localhost:5173/contracts'); await p.waitForSelector('text=contracts'); await shot('contracts');
  await p.click('text=Master Services Agreement – Bluepeak Technologies'); await p.waitForSelector('text=Effective terms'); 
  await p.click('text=Governing law >> nth=0').catch(()=>{}); await p.click('tr:has-text("Payment terms") >> nth=0'); await shot('detail');
  await p.goto('http://localhost:5173/ask'); await p.waitForSelector('text=Which vendors have uncapped liability?');
  await p.click('button:has-text("Which contracts have a confidentiality")'); await p.waitForSelector('text=How I got this'); await shot('ask-clause');
  await p.click('button:has-text("Which auto-renewing contracts have uncapped")'); await p.waitForSelector('text=Step 2'); await shot('ask-mixed');
  await p.goto('http://localhost:5173/redline'); await p.waitForSelector('text=Re-run live'); await shot('redline');
  await p.click('button:has-text("clean control")'); await p.waitForSelector('text=No deviations found'); await shot('redline-clean');
  await p.goto('http://localhost:5173/templates'); await p.waitForSelector('text=Deviation heatmap'); await p.click('button:has-text("SaaS Subscription")'); await p.waitForTimeout(600); await shot('templates');
  await p.goto('http://localhost:5173/admin'); await p.waitForSelector('text=AI usage'); 
  await p.click('text=Dark'); await p.goto('http://localhost:5173/'); await p.waitForSelector('text=Upcoming action dates'); await shot('dashboard-dark');
  console.log(errs.length ? errs.join('\n') : 'no console errors'); if (errs.length) process.exitCode = 1;
  await b.close();
})();
