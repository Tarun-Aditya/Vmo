// The leadership presentation's demo, recorded as one video: the "From paper to rows" page (one contract, then a folder of ten, becoming rows,
// with a document opened), then the product reading the same rows (renewals, the repository, Ask).
// Needs: API on :8000 (hotel data with the sample folder read, Demo mode, SIMULATORS=1, SCHEDULER_ENABLED=0), web on :5173, AUTH_MODE=off, ffmpeg.
// Usage: node scripts/presentation_storyboard.js [outDir]   -> outDir/paper-to-rows-demo.mp4, one screenshot per step, report.md
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const OUT = path.resolve(process.argv[2] || 'reports/presentation/video');
const PAGE = 'file://' + path.resolve(__dirname, '../reports/presentation/paper-to-rows.local.html');
const U = process.env.WEB || 'http://localhost:5173', A = process.env.API || 'http://localhost:8000';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
// Voice-over (optional): outDir/narration/NN.wav and durations.json from scripts/make_narration.py. Each step lasts at least as long as its
// line, and the lines are mixed into the video at the moment their step starts.
const NAR = path.join(OUT, 'narration');
const DUR = fs.existsSync(path.join(NAR, 'durations.json')) ? JSON.parse(fs.readFileSync(path.join(NAR, 'durations.json'), 'utf8')) : [];
const marks = [];
const results = [], errs = [];
let n = 0;

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  for (const f of fs.readdirSync(OUT)) if (/\.(png|webm|mp4)$/.test(f)) fs.unlinkSync(path.join(OUT, f));
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, recordVideo: { dir: OUT, size: { width: 1440, height: 900 } } });
  await ctx.addInitScript(() => { try { localStorage.removeItem('ciq_property'); } catch {} });
  const p = await ctx.newPage();
  const T0 = Date.now();          // the video starts with the page
  p.on('pageerror', (e) => errs.push('pageerror: ' + e.message));
  p.on('response', (r) => { if (r.status() >= 500 && r.url().includes('/api/')) errs.push(r.status() + ' ' + new URL(r.url()).pathname); });
  const caption = (t) => p.evaluate((t) => {
    let el = document.getElementById('__cap');
    if (!el) { el = document.createElement('div'); el.id = '__cap';
      el.style.cssText = 'position:fixed;left:50%;bottom:20px;pointer-events:none;transform:translateX(-50%);z-index:99999;background:rgba(15,23,42,.94);color:#fff;padding:12px 22px;border-radius:10px;font:500 17px/1.4 system-ui,sans-serif;max-width:1180px;text-align:center;box-shadow:0 6px 24px rgba(0,0,0,.3)';
      document.body.appendChild(el); }
    el.textContent = t; }, t).catch(() => {});
  const api = async (u, method = 'GET', body) => { const r = await p.request.fetch(A + u, { method, headers: { 'content-type': 'application/json' }, data: body ? JSON.stringify(body) : undefined }); try { return await r.json(); } catch { return null; } };
  const step = async (title, fn, hold = 4500) => {
    n++;
    const t = Date.now();
    marks.push(t - T0);
    const voice = (DUR[n - 1] || 0) * 1000;
    await caption(title);
    try {
      const note = await fn(); await caption(title + (note ? ` · ${note}` : ''));
      await sleep(Math.max(hold, voice + 700 - (Date.now() - t)));
      await p.screenshot({ path: `${OUT}/${String(n).padStart(2, '0')}.png` }); results.push([true, title, note || '']);
    } catch (e) { results.push([false, title, e.message.split('\n')[0]]); await caption(title + ' (step failed, continuing)'); await sleep(Math.max(1000, voice + 700 - (Date.now() - t))); }
  };
  const hash = async (h) => { await p.evaluate((h) => { location.hash = h; }, h); await sleep(500); };
  const docScroll = (sel, y) => p.evaluate(([s, y]) => { const e = document.querySelector(s); if (e) e.scrollTo({ top: y, behavior: 'smooth' }); }, [sel, y]);
  const ask = async (q, wait = 5500) => { await p.fill('input[aria-label="Your question"]', q); await p.press('input[aria-label="Your question"]', 'Enter'); await sleep(wait); };

  await api('/api/admin/mode', 'PUT', { demo: true });

  // ---------------------------------------------------------------- part 1: one document
  await p.goto(PAGE + '#one1'); await sleep(1200);
  await step('One document: a signed PDF. The answers the business needs are in it, but only a person can read it', async () => '', 6000);
  await step('Watch the pipeline read it: read the pages, split into typed clauses, extract each term with its source, index, check', async () => {
    await hash('one2');
    await p.waitForSelector('#done1:not([hidden])', { timeout: 30000 }); return ''; }, 4000);
  await step('Clauses: 20 of them, each typed and stored as a row with a vector for search by meaning', async () => { await hash('one3'); return ''; }, 5000);
  await step('Each term found in its sentence: click a value and the page shows the words it came from', async () => {
    await hash('one4');
    for (const f of ['auto_renew', 'notice_period_days', 'liability_cap_text']) { await p.click(`.fchip[data-f="${f}"]`); await sleep(1800); }
    return ''; }, 2500);
  await step('Stored as rows in tables, joined by keys: the contract, its terms with sources, duties and failed checks', async () => {
    await hash('one5'); await sleep(2500); await p.mouse.wheel(0, 600); return ''; }, 4500);
  await step('What the rows say: the last day to give notice was 1 September. It renews for 36 months, uncapped, with no exit', async () => {
    await p.mouse.wheel(0, -2000); await hash('one6'); return ''; }, 6500);

  // ---------------------------------------------------------------- part 2: ten documents
  await step('Ten documents: a real folder. PDF, Word, a scanned amendment, and a renamed copy of one contract', async () => { await hash('ten1'); return ''; }, 5500);
  await step('The same five steps for every file; the contracts table fills row by row; the copy is caught by its fingerprint', async () => {
    await hash('ten2');
    await p.waitForFunction(() => /All 11 files read/.test(document.querySelector('#live')?.innerText || ''), null, { timeout: 40000 }); return ''; }, 3500);
  await step('Open any document: the scanned amendment, read by OCR, split into clauses, its values highlighted', async () => {
    await p.click('#file-4'); await sleep(1200);
    await p.click('#dr-fields .fchip:nth-child(1)'); await sleep(1500);
    await p.click('#dr-fields .fchip:nth-child(2)'); return ''; }, 4000);
  await step('The cleaning master agreement: every value with its page and confidence; click one to find it', async () => {
    await p.keyboard.press('Escape'); await sleep(500);
    await p.click('#file-1'); await sleep(1200);
    await p.click('#dr-fields .fchip[data-f="auto_renew"]'); return ''; }, 4500);
  await step('Connected: schedules and the NDA link to their master; the amendment moves payment from 45 to 30 days', async () => {
    await p.keyboard.press('Escape'); await sleep(400); await hash('ten3'); return ''; }, 6500);
  await step('The business runs on the rows: four questions, each one query over all ten contracts', async () => {
    await hash('ten4'); await sleep(3000); await p.mouse.wheel(0, 500); return ''; }, 5000);
  await step('Once the data exists, every contract process can run on it. Now the product, on the same rows', async () => {
    await p.mouse.wheel(0, -2000); await hash('ten5'); return ''; }, 5500);

  // ---------------------------------------------------------------- part 3: the product on the same rows
  await p.goto(U + '/renewals'); await p.waitForLoadState('networkidle').catch(() => {}); await sleep(1200);
  await step('The product · Renewals: the last day to act for every contract, not the expiry date', async () => '', 6000);
  await p.goto(U + '/contracts'); await p.waitForLoadState('networkidle').catch(() => {}); await sleep(1000);
  await step('The repository: the cleaning master agreement with its schedules, NDA and amendment beneath it', async () => {
    await p.fill('input[placeholder="title or vendor"]', 'Meridian'); await sleep(1500); return ''; }, 6000);
  await p.goto(U + '/ask'); await p.waitForLoadState('networkidle').catch(() => {}); await sleep(1000);
  await step('Ask in plain English: which auto-renewing contracts have already passed their notice deadline?', async () => {
    await ask('Which auto-renewing contracts have already passed their notice deadline?'); return ''; }, 6000);
  await step('Which vendors have uncapped liability? The valet and waste contracts from the page, and a food supplier elsewhere in the portfolio', async () => {
    await ask('Which vendors have uncapped liability?'); return ''; }, 6000);

  const vid = p.video(); await ctx.close(); await b.close();
  const webm = await vid.path();
  const enc = ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '26', '-pix_fmt', 'yuv420p', '-movflags', '+faststart'];
  const lines = marks.map((at, i) => [at, path.join(NAR, `${String(i + 1).padStart(2, '0')}.wav`)]).filter(([, f]) => DUR.length && fs.existsSync(f));
  if (lines.length) {
    const inputs = lines.flatMap(([, f]) => ['-i', f]);
    const delays = lines.map(([at], i) => `[${i + 1}:a]adelay=${at}|${at}[a${i}]`).join(';');
    const mix = `${delays};${lines.map((_, i) => `[a${i}]`).join('')}amix=inputs=${lines.length}:normalize=0,apad[aout]`;
    execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-i', webm, ...inputs, '-filter_complex', mix, '-map', '0:v', '-map', '[aout]', ...enc,
      '-c:a', 'aac', '-b:a', '128k', '-shortest', path.join(OUT, 'paper-to-rows-demo.mp4')]);
  } else {
    execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-i', webm, ...enc, path.join(OUT, 'paper-to-rows-demo.mp4')]);
  }
  fs.unlinkSync(webm);
  const ok = results.filter((r) => r[0]).length;
  fs.writeFileSync(path.join(OUT, 'report.md'), `# Presentation demo video — ${ok}/${results.length} steps passed\n\nRecorded by \`node scripts/presentation_storyboard.js\`: the *From paper to rows* page (local copy), then the product in Demo mode.\n\n` +
    results.map(([g, t, m], i) => `${i + 1}. ${g ? 'PASS' : 'FAIL'} ${t}${m ? ` — ${m}` : ''}`).join('\n') + `\n\nErrors: ${errs.length ? errs.join('; ') : 'none'}\n`);
  console.log(`${ok}/${results.length} steps passed; errors: ${errs.length}; video: ${path.join(OUT, 'paper-to-rows-demo.mp4')}`);
})();
