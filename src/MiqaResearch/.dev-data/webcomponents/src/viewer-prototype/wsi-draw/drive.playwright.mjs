// PROTOTYPE driver for #214: per variant × tool, draw N times, count ROIs that land; pan/zoom; screenshot.
// usage (from .dev-data/webcomponents): node src/viewer-prototype/wsi-draw/drive.playwright.mjs [N]
import { chromium } from "playwright";
const BASE = "http://127.0.0.1:8766/static/js/webcomponents/prototype-wsi-draw.html";
const N = +(process.argv[2] ?? 5);
const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
const results = [];
for (const v of ["cs3d", "dmv"]) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 860 } });
  const errs = [];
  page.on("pageerror", (e) => errs.push(`pageerror: ${e.message.slice(0, 160)}`));
  page.on("console", (m) => { if (m.type() === "error") errs.push(m.text().slice(0, 160)); });
  await page.goto(`${BASE}?variant=${v}`);
  await page.waitForFunction(() => document.body.dataset.ready === "1", null, { timeout: 180000 });
  await page.waitForTimeout(4000);
  const b = await page.evaluate(() => { const r = document.getElementById("vp").getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; });
  const tools = await page.evaluate(() => [...document.querySelectorAll("#rail button[data-t]")].filter((x) => !x.disabled).map((x) => x.dataset.t));
  const m = page.mouse;
  // fully zoomed out the slide fills the view and cannot pan: zoom in first (wheel = dmv zoom)
  await m.move(b.x + b.w / 2, b.y + b.h / 2); await m.wheel(0, -600); await page.waitForTimeout(1500);
  for (const tool of tools) {
    await page.evaluate(() => window.__spike.clear());
    await page.evaluate((t) => window.__spike.setTool(t), tool);
    let ok = 0;
    for (let i = 0; i < N; i++) {
      const before = await page.evaluate(() => window.__spike.rois().length);
      const x = b.x + 150 + (i % 5) * 140, y = b.y + 120 + Math.floor(i / 5) * 140 + (tools.indexOf(tool) % 3) * 40;
      const click = async (px, py) => { await m.move(px, py); await m.down(); await m.up(); await page.waitForTimeout(120); };
      const drag = async (pts) => { await m.move(...pts[0]); await m.down(); for (const p of pts.slice(1)) await m.move(...p, { steps: 4 }); await m.up(); };
      if (tool === "Point") await click(x, y);
      else if (v === "cs3d" && tool === "Freehand") await drag([[x, y], [x + 80, y], [x + 80, y + 70], [x, y + 70], [x, y + 2]]);
      else if (v === "cs3d") await drag([[x, y], [x + 90, y + 60]]);
      else if (tool === "Length") { await click(x, y); await click(x + 90, y + 60); }
      else if (tool === "Polyline") { await click(x, y); await click(x + 50, y + 40); await m.dblclick(x + 100, y + 10); }
      else if (tool === "Rectangle" || tool === "Ellipse") { await click(x, y); await m.move(x + 60, y + 50, { steps: 4 }); await click(x + 60, y + 50); }
      else if (tool === "Polygon") { await click(x, y); await click(x + 80, y); await click(x + 60, y + 70); await click(x, y); }
      else if (tool === "Freehand") await drag([[x, y], [x + 80, y], [x + 80, y + 70], [x, y + 70], [x, y + 2]]);
      await page.waitForTimeout(400);
      if ((await page.evaluate(() => window.__spike.rois().length)) > before) ok++;
    }
    // stray: does a middle- or right-drag (pan/zoom) create a ROI with this tool active?
    const n0 = await page.evaluate(() => window.__spike.rois().length);
    for (const button of ["middle", "right"]) { await m.move(b.x + b.w - 200, b.y + b.h - 200); await m.down({ button }); await m.move(b.x + b.w - 150, b.y + b.h - 170, { steps: 6 }); await m.up({ button }); await page.waitForTimeout(300); }
    const stray = (await page.evaluate(() => window.__spike.rois().length)) - n0;
    results.push({ v, tool, ok: `${ok}/${N}`, strayFromPanZoom: stray });
    await page.screenshot({ path: `src/viewer-prototype/wsi-draw/shot-${v}-${tool}.png` });
  }
  // middle-drag pan + right-drag zoom: do the ROIs stay anchored? (screenshots before/after)
  await page.evaluate(() => window.__spike.setTool("Length"));
  await page.screenshot({ path: `src/viewer-prototype/wsi-draw/shot-${v}-drawn.png` });
  const cam0 = await page.evaluate(() => window.__spike.camera());
  await m.move(b.x + b.w / 2, b.y + b.h / 2); await m.down({ button: "middle" }); await m.move(b.x + b.w / 2 + 120, b.y + b.h / 2 + 60, { steps: 10 }); await m.up({ button: "middle" });
  await m.down({ button: "right" }); await m.move(b.x + b.w / 2 + 120, b.y + b.h / 2 - 60, { steps: 10 }); await m.up({ button: "right" });
  await page.waitForTimeout(1500);
  const cam1 = await page.evaluate(() => window.__spike.camera());
  await page.screenshot({ path: `src/viewer-prototype/wsi-draw/shot-${v}-panzoom.png` });
  const sample = await page.evaluate(() => window.__spike.rois().slice(0, 3));
  const events = await page.evaluate(() => window.__spike.events.slice(-8));
  results.push({ v, cam0, cam1, sample, events, errs: [...new Set(errs)].slice(0, 6) });
  await page.close();
}
for (const r of results) console.log(JSON.stringify(r));
await browser.close();
