// PROTOTYPE smoke driver for #201: each variant x mode → screenshot + a few interactions.
import { chromium } from "playwright";
const BASE = "http://127.0.0.1:8765/static/js/webcomponents/prototype-viewer-toolbar.html";
const combos = process.argv.slice(2).length ? process.argv.slice(2) : ["A:mpr", "B:mpr", "C:mpr", "A:stack", "A:fusion", "A:wsi"];
const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
for (const c of combos) {
  const [v, mode, extra = ""] = c.split(":");
  const page = await browser.newPage({ viewport: { width: 1440, height: 860 } });
  const errs = [];
  page.on("console", (m) => { if (["error", "warning"].includes(m.type())) errs.push(`${m.type()}: ${m.text().slice(0, 200)}`); });
  page.on("pageerror", (e) => errs.push(`pageerror: ${e.message}`));
  await page.goto(`${BASE}?variant=${v}&mode=${mode}${extra ? "&" + extra : ""}`);
  await page.waitForFunction(() => { const el = document.querySelector("mires-viewer-toolbar-prototype"); return el && /ready|FAIL/.test(el.shadowRoot?.querySelector(".status")?.textContent ?? ""); }, null, { timeout: 180000 });
  await page.waitForTimeout(5000);
  const box = (id) => page.evaluate((id) => { const b = document.querySelector("mires-viewer-toolbar-prototype").shadowRoot.querySelector("#" + id).getBoundingClientRect(); return { x: b.x, y: b.y, w: b.width, h: b.height }; }, id);
  const cam = (id) => page.evaluate((id) => { const c = window.__tb.engine.getViewport(id).getCamera(); return { fp: c.focalPoint.map((x) => +x.toFixed(1)), ps: +c.parallelScale.toFixed(2) }; }, id);
  const out = { combo: c };
  const first = mode === "stack" ? "stack" : mode === "wsi" ? "wsi" : "ax";
  const b = await box(first);
  out.before = await cam(first);
  // middle-drag pan
  await page.mouse.move(b.x + b.w / 2, b.y + b.h / 2); await page.mouse.down({ button: "middle" }); await page.mouse.move(b.x + b.w / 2 + 80, b.y + b.h / 2 + 40, { steps: 10 }); await page.mouse.up({ button: "middle" });
  await page.waitForTimeout(500);
  out.afterMiddlePan = await cam(first);
  // keyboard: select Length (L) and draw
  await page.keyboard.press("l");
  await page.mouse.move(b.x + 60, b.y + 60); await page.mouse.down(); await page.mouse.move(b.x + 200, b.y + 120, { steps: 8 }); await page.mouse.up();
  await page.waitForTimeout(500);
  out.primary = await page.evaluate(() => window.__tb.primary);
  out.annotations = await page.evaluate(() => window.cornerstoneTools?.annotation?.state.getAllAnnotations().map((a) => a.metadata.toolName) ?? "n/a");
  if (mode === "mpr") { await page.keyboard.press("v"); await page.waitForTimeout(2500); out.afterV = await page.evaluate(() => [window.__tb.layout, window.__tb.orientation, window.__tb.viewportIds()]); }
  if (mode !== "wsi") { await page.keyboard.press("2"); await page.waitForTimeout(500); out.info = await page.evaluate(() => window.__tb.info().map((i) => `${i.id}:${i.voi}:${i.badge}`)); }
  out.status = await page.evaluate(() => document.querySelector("mires-viewer-toolbar-prototype").shadowRoot.querySelector(".status").textContent);
  out.errs = [...new Set(errs)].slice(0, 12);
  await page.screenshot({ path: `src/viewer-prototype/toolbar/shot-${v}-${mode}${extra ? "-" + extra.replace(/[=&]/g, "_") : ""}.png` });
  console.log(JSON.stringify(out));
  await page.close();
}
await browser.close();
