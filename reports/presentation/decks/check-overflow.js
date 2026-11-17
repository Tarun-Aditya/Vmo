const { chromium } = require('playwright'); const fs = require('fs');
(async () => { const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1920, height: 1080 } });
  const order = JSON.parse(fs.readFileSync('project/deck.json')).order;
  for (const id of order) {
    const html = fs.readFileSync(`project/slides/${id}.html`, 'utf8').replace(/<aside>[\s\S]*?<\/aside>/, '');
    await p.setContent(`<html><head><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600;700&family=DM+Sans:wght@400;500;700&display=swap"><style>body{margin:0} section{width:1920px;height:1080px;box-sizing:border-box;overflow:hidden} h1,h2,h3,p{margin:0}</style></head><body>${html}</body></html>`);
    await p.waitForTimeout(600);
    const r = await p.evaluate(() => { const s = document.querySelector('section'); let max = 0, n = 0; s.querySelectorAll('*').forEach((e) => { n++; const b = e.getBoundingClientRect(); if (b.height > 0) max = Math.max(max, b.bottom); }); return { max: Math.round(max), n }; });
    await p.screenshot({ path: `prev-${id}.png` });
    console.log(id.padEnd(10), 'bottom', r.max, r.max > 952 ? 'OVER' : 'ok', 'elements', r.n);
  } await b.close(); })();
