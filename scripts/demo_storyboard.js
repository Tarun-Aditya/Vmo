// The demo as story-boarded in DEMO.md, recorded as one video: the paper; the pipeline reading a folder of contracts live (Admin -> Pipeline), one
// document opened up with its sources, the folder again; then the data: repository, renewals, Ask over all documents and over the ones ticked.
// Needs: API on :8000 (SIMULATORS=1, SCHEDULER_ENABLED=0, hotel data), web on :5173, AUTH_MODE=off, pdftoppm and ffmpeg.
// Usage: node scripts/demo_storyboard.js [outDir]   -> outDir/contractiq-demo.mp4, one screenshot per step, report.md
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const OUT = path.resolve(process.argv[2] || 'reports/demo');
const U = process.env.WEB || 'http://localhost:5173', A = process.env.API || 'http://localhost:8000';
const DOCS = path.resolve(__dirname, '../data/realistic_hotel/docs');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [], errs = [];
let n = 0;

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  for (const f of fs.readdirSync(OUT)) if (/\.(png|webm|mp4|html)$/.test(f)) fs.unlinkSync(path.join(OUT, f));
  // act 1 shows the waste contract's renewal clause as it looks on paper (page 3 of the PDF)
  execFileSync('pdftoppm', ['-r', '110', '-png', '-f', '3', '-l', '3', path.join(DOCS, 'prairie_waste_services.pdf'), path.join(OUT, 'paper')]);
  const img = fs.readdirSync(OUT).find((f) => f.startsWith('paper') && f.endsWith('.png'));
  fs.writeFileSync(path.join(OUT, 'paper.html'), `<!doctype html><meta charset="utf-8"><body style="margin:0;background:#3b3f45;display:flex;justify-content:center">
    <img src="${img}" style="height:auto;width:900px;box-shadow:0 4px 24px rgba(0,0,0,.5);margin:24px 0">`);

  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1440, height: 860 }, recordVideo: { dir: OUT, size: { width: 1440, height: 860 } } });
  await ctx.addInitScript(() => { try { localStorage.removeItem('ciq_property'); } catch {} });
  const p = await ctx.newPage();
  p.on('pageerror', (e) => errs.push('pageerror: ' + e.message));
  p.on('response', (r) => { if (r.status() >= 500 && r.url().includes('/api/')) errs.push(r.status() + ' ' + new URL(r.url()).pathname); });
  const caption = (t) => p.evaluate((t) => {
    let el = document.getElementById('__cap');
    if (!el) { el = document.createElement('div'); el.id = '__cap';
      el.style.cssText = 'position:fixed;left:50%;bottom:24px;pointer-events:none;transform:translateX(-50%);z-index:99999;background:rgba(15,23,42,.94);color:#fff;padding:12px 22px;border-radius:10px;font:600 17px system-ui;max-width:90%;text-align:center;line-height:1.4';
      document.body.appendChild(el); }
    el.textContent = t; }, t).catch(() => {});
  const api = async (u, method = 'GET', body) => { const r = await p.request.fetch(A + u, { method, headers: { 'content-type': 'application/json' }, data: body ? JSON.stringify(body) : undefined }); try { return await r.json(); } catch { return null; } };
  const go = async (u) => { await p.goto(U + u); await p.waitForLoadState('networkidle').catch(() => {}); await sleep(900); };
  const step = async (title, fn, hold = 3500) => {
    n++;
    try { const note = await fn(); await caption(title + (note ? ` · ${note}` : '')); await sleep(hold); await p.screenshot({ path: `${OUT}/${String(n).padStart(2, '0')}.png` }); results.push([true, title, note || '']); }
    catch (e) { results.push([false, title, e.message.split('\n')[0]]); await caption(title + ' (step failed, continuing)'); await sleep(1000); }
  };
  const ask = async (q, wait = 5000) => { await p.fill('input[aria-label="Your question"]', q); await p.press('input[aria-label="Your question"]', 'Enter'); await sleep(wait); };

  await api('/api/admin/mode', 'PUT', { demo: true });
  await api('/api/admin/pipeline/samples', 'DELETE');

  // ---------------------------------------------------------------- act 1: the paper
  await p.goto('file://' + path.join(OUT, 'paper.html')); await sleep(600);
  await step('Act 1 · The paper: a waste hauler\'s contract for one hotel, six pages, in the supplier\'s own form', async () => '', 4500);
  await step('Section 2.2: it renews for another 3 years unless cancelled by certified mail 180 to 90 days before the end. Nobody calendared it; the window closed on 1 September.', async () => {
    await p.mouse.wheel(0, 500); await sleep(400); return ''; }, 6500);

  // ---------------------------------------------------------------- act 2: the pipeline
  await go('/admin');
  await step('Act 2 · Admin → Pipeline: contracts arrive from watched folders, drives, SharePoint, ERP and the mailbox, on a schedule or as files appear', async () => '', 5000);
  n++;
  try {
    await caption('Reading a folder of 11 contracts: each is read, its clauses recognised, terms extracted with page and confidence, indexed for search, and checked');
    await p.click('button:has-text("Put the folder in the inbox and read it")');
    const t0 = Date.now(); let shotAt = 0;
    const notes = ['Read: text and pages (a scan goes through OCR)', 'Structure: clauses found and recognised, wherever the supplier put them',
      'Extract: dates, renewal, notice, value, payment, cap, exit, law, personal data, signers', 'Index: every clause becomes a vector, searchable by meaning',
      'Check: against your standards: missing clauses, risky terms, the last day to act', 'Schedules and the scanned amendment are linked under their master agreement'];
    for (let i = 0; Date.now() - t0 < 600000; i++) {
      const live = await api('/api/admin/pipeline/live');
      if (live && live.status === 'completed' && Date.now() - t0 > 3000) break;
      if (i % 6 === 0) await caption('Live run · ' + notes[Math.floor(i / 6) % notes.length]);
      if (!shotAt && Date.now() - t0 > 30000) { await p.screenshot({ path: `${OUT}/${String(n).padStart(2, '0')}-running.png` }); shotAt = 1; }
      await sleep(1500);
    }
    const docs = Object.values((await api('/api/admin/pipeline/live')).docs);
    const acts = docs.map((d) => d.action);
    await caption(`Done: ${acts.filter((a) => a === 'new').length} contracts read, ${docs.filter((d) => d.parent).length} linked to their master agreement, 1 duplicate caught (same file, another name)`);
    await sleep(5000); await p.screenshot({ path: `${OUT}/${String(n).padStart(2, '0')}.png` });
    results.push([true, 'A folder of 11 contracts read live in the pipeline', `${Math.round((Date.now() - t0) / 1000)} s, ${acts.filter((a) => a === 'duplicate').length} duplicate`]);
  } catch (e) { results.push([false, 'A folder of 11 contracts read live', e.message.split('\n')[0]]); }

  await step('The scanned amendment: read by OCR, linked to the master agreement, and it changes the end date and payment terms', async () => {
    await p.click('td:has-text("meridian_amendment_1_scan.pdf")'); await sleep(800);
    await p.locator('td:has-text("meridian_amendment_1_scan.pdf")').scrollIntoViewIfNeeded(); return ''; }, 5500);
  await step('One document opened up: the waste contract\'s terms with page and confidence, the checks that failed, the last day to act', async () => {
    await p.click('td:has-text("meridian_amendment_1_scan.pdf")'); await sleep(300);
    await p.click('td:has-text("prairie_waste_services.pdf")'); await sleep(800);
    await p.locator('td:has-text("prairie_waste_services.pdf")').scrollIntoViewIfNeeded(); return ''; }, 6000);
  await step('Its contract page: the document beside the terms; click a term and the passage it came from is highlighted', async () => {
    await p.click('a:has-text("Open the contract with its sources")'); await p.waitForLoadState('networkidle').catch(() => {}); await sleep(1500);
    const row = p.locator('tr', { hasText: /Notice/ }).first(); await row.click(); await sleep(1200); return ''; }, 6000);
  await go('/admin');
  await step('The folder again: every file recognised by its fingerprint and skipped. Only new or changed documents are read.', async () => {
    await p.click('button:has-text("Put the folder in the inbox again")');
    for (let i = 0; i < 40; i++) { await sleep(700); const l = await api('/api/admin/pipeline/live'); if (l.status === 'completed' && Object.values(l.docs).every((d) => d.status === 'done' || d.status === 'error')) break; }
    await sleep(1500); return ''; }, 5000);

  // ---------------------------------------------------------------- act 3: the data
  await go('/contracts');
  await step('Act 3 · The repository: each agreement with its schedules, amendments and NDAs beneath it, and the terms that matter', async () => '', 5000);
  await step('The cleaning master agreement: 30-day payment and a 2029 end date come from the scanned amendment, not the original', async () => {
    await p.fill('input[placeholder="title or vendor"]', 'Meridian'); await sleep(1500); return ''; }, 6000);
  await go('/renewals');
  await step('Renewals: the last day to act, not the expiry date. The waste contract\'s notice passed; the HVAC contract has 17 days', async () => '', 6000);
  await go('/ask');
  await step('Ask, every document ticked: which auto-renewing contracts have already passed their notice deadline?', async () => {
    await ask('Which auto-renewing contracts have already passed their notice deadline?'); return ''; }, 6000);
  await step('Ask the whole portfolio: which vendors have uncapped liability?', async () => {
    await ask('Which vendors have uncapped liability?'); return ''; }, 5500);
  await p.click('button:has-text("+ New chat")').catch(() => {}); await sleep(600);
  await step('Narrow it: untick All documents, tick the cleaning contractor\'s five documents', async () => {
    await p.click('input[aria-label="All documents"]'); await p.fill('input[aria-label="Search documents"]', 'Meridian'); await sleep(500);
    await p.click('button:has-text("Tick shown")'); await p.fill('input[aria-label="Search documents"]', ''); await sleep(800); return ''; }, 4500);
  await step('Their start date, end date and payment terms, as a table, from those documents only (amended terms included)', async () => {
    await ask('Show start date, end date and payment terms'); return ''; }, 6500);
  await step('Their insurance requirements: the clauses themselves', async () => { await ask('What are the insurance requirements?'); return ''; }, 6000);
  await p.click('button:has-text("+ New chat")').catch(() => {}); await sleep(600);
  await step('One contract: what happens if we end the waste contract early? The liquidated-damages clause, with page and match', async () => {
    await p.click('button:has-text("Use all documents")').catch(() => {}); await sleep(300);
    await p.click('input[aria-label="All documents"]'); await p.fill('input[aria-label="Search documents"]', 'Waste and Recycling Service'); await sleep(500);
    await p.click('button:has-text("Tick shown")'); await p.fill('input[aria-label="Search documents"]', ''); await sleep(500);
    await ask('What happens if we end this contract early?'); return ''; }, 7000);
  await go('/');
  await step('Signed paper in, decisions out: every term traced to its source, the current terms after every amendment, searchable by meaning, checked, continuously', async () => '', 6000);

  const vid = p.video(); await ctx.close(); await b.close();
  const webm = await vid.path();
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-i', webm, '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '26', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', path.join(OUT, 'contractiq-demo.mp4')]);
  fs.unlinkSync(webm); fs.unlinkSync(path.join(OUT, 'paper.html')); fs.unlinkSync(path.join(OUT, img));
  const ok = results.filter((r) => r[0]).length;
  fs.writeFileSync(path.join(OUT, 'report.md'), `# Demo video (DEMO.md story) — ${ok}/${results.length} steps passed\n\n` + results.map(([g, t, m], i) => `${i + 1}. ${g ? 'PASS' : 'FAIL'} ${t}${m ? ` — ${m}` : ''}`).join('\n') + `\n\nErrors: ${errs.length ? errs.join('; ') : 'none'}\n`);
  console.log(`${ok}/${results.length} steps passed; errors: ${errs.length}; video: ${path.join(OUT, 'contractiq-demo.mp4')}`);
})();
