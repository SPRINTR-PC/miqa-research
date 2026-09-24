// PROTOTYPE smoke driver for #191: loads each variant, exercises tools, reports.
import { chromium } from "playwright";

const BASE = "http://127.0.0.1:8765/static/js/webcomponents/prototype-viewer-shadow-dom.html";
const variants = process.argv.slice(2).length ? process.argv.slice(2) : ["shadow", "light", "shadow-mirrored"];
const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });

for (const v of variants) {
  const page = await browser.newPage({ viewport: { width: 1300, height: 1500 } });
  const consoleErrs = [];
  page.on("console", (m) => { if (["error", "warning"].includes(m.type())) consoleErrs.push(`${m.type()}: ${m.text().slice(0, 300)}`); });
  page.on("pageerror", (e) => consoleErrs.push(`pageerror: ${e.message}`));
  const failed = [];
  page.on("requestfailed", (r) => failed.push(`${r.url()} ${r.failure()?.errorText}`));
  page.on("response", (r) => { if (r.status() >= 400) failed.push(`${r.status()} ${r.url()}`); });
  await page.goto(`${BASE}?variant=${v}`);
  await page.waitForFunction(() => /\] WSI:/.test(document.getElementById("log").textContent), null, { timeout: 180000 });
  await page.waitForTimeout(6000); // let volume stream + WSI tiles
  const log = await page.$eval("#log", (e) => e.innerText);

  const probe = () => page.evaluate(() => {
    const { engine, el } = window.__proto;
    const root = el.renderRoot;
    const cs = window.cornerstoneTools;
    const r = {};
    const st = engine.getViewport("stack");
    r.stackIndex = st.getCurrentImageIdIndex();
    r.stackZoom = +st.getZoom().toFixed(3);
    r.stackVOI = st.getProperties().voiRange;
    const ax = engine.getViewport("ax"), sag = engine.getViewport("sag"), cor = engine.getViewport("cor");
    r.sagFocal = sag.getCamera().focalPoint.map((x) => +x.toFixed(1));
    r.corFocal = cor.getCamera().focalPoint.map((x) => +x.toFixed(1));
    r.axFocal = ax.getCamera().focalPoint.map((x) => +x.toFixed(1));
    r.svgLayers = [...root.querySelectorAll(".svg-layer")].length;
    r.svgChildren = [...root.querySelectorAll(".svg-layer")].map((s) => s.querySelectorAll("*").length);
    r.canvases = [...root.querySelectorAll("canvas")].map((c) => `${c.width}x${c.height}`);
    const w = root.querySelector("#wsi");
    r.wsiChildren = w.querySelectorAll("*").length;
    r.wsiOlControls = [...w.querySelectorAll("[class*=ol-]")].slice(0, 12).map((e) => {
      const s = getComputedStyle(e);
      return `${e.className.toString().slice(0, 40)} pos=${s.position} ${s.display}`;
    });
    const wv = engine.getViewport("wsi");
    try { r.wsiZoom = +wv.getZoom().toFixed(4); r.wsiPan = wv.getPan?.()?.map((x) => +x.toFixed(1)); } catch (e) { r.wsiZoom = `err ${e.message}`; }
    r.headStyles = [...document.head.querySelectorAll("style:not([data-page])")].map((s) => s.id || s.textContent.slice(0, 60));
    r.headLinks = [...document.head.querySelectorAll("link[rel=stylesheet]")].map((l) => l.href);
    r.bodyDirectChildren = [...document.body.children].map((c) => c.tagName + (c.id ? "#" + c.id : ""));
    return r;
  });

  const box = async (id) => page.evaluate((id) => {
    const b = window.__proto.el.renderRoot.querySelector("#" + id).getBoundingClientRect();
    return { x: b.x, y: b.y, w: b.width, h: b.height };
  }, id);
  const before = await probe();
  const acts = [];
  const act = async (name, fn) => { try { await fn(); acts.push(`${name}: done`); } catch (e) { acts.push(`${name}: THREW ${e.message}`); } };

  // Stack: wheel scroll, W/L drag, shift+drag Length
  const s = await box("stack");
  await act("stack wheel", async () => { await page.mouse.move(s.x + s.w / 2, s.y + s.h / 2); for (let i = 0; i < 5; i++) { await page.mouse.wheel(0, 120); await page.waitForTimeout(100); } });
  await act("stack W/L drag", async () => { await page.mouse.move(s.x + 100, s.y + 100); await page.mouse.down(); await page.mouse.move(s.x + 180, s.y + 150, { steps: 10 }); await page.mouse.up(); });
  await act("stack length (shift+drag)", async () => { await page.keyboard.down("Shift"); await page.mouse.move(s.x + 80, s.y + 250); await page.mouse.down(); await page.mouse.move(s.x + 250, s.y + 300, { steps: 10 }); await page.mouse.up(); await page.keyboard.up("Shift"); });
  await act("stack zoom (right drag)", async () => { await page.mouse.move(s.x + 190, s.y + 190); await page.mouse.down({ button: "right" }); await page.mouse.move(s.x + 190, s.y + 120, { steps: 10 }); await page.mouse.up({ button: "right" }); });
  // Crosshairs: click-drag in axial moves the centre -> sag/cor focal points change
  const a = await box("ax");
  await act("crosshairs drag in axial", async () => { await page.mouse.move(a.x + a.w / 2 + 40, a.y + a.h / 2 + 30); await page.mouse.down(); await page.mouse.move(a.x + a.w / 2 - 60, a.y + a.h / 2 - 50, { steps: 15 }); await page.mouse.up(); });
  // WSI: middle-drag pan, right-drag zoom, wheel
  const w = await box("wsi");
  await act("wsi pan (middle drag)", async () => { await page.mouse.move(w.x + 300, w.y + 250); await page.mouse.down({ button: "middle" }); await page.mouse.move(w.x + 420, w.y + 300, { steps: 10 }); await page.mouse.up({ button: "middle" }); });
  await act("wsi wheel", async () => { await page.mouse.move(w.x + 390, w.y + 260); for (let i = 0; i < 3; i++) { await page.mouse.wheel(0, -200); await page.waitForTimeout(150); } });
  await act("wsi length drag", async () => { await page.mouse.move(w.x + 200, w.y + 200); await page.mouse.down(); await page.mouse.move(w.x + 400, w.y + 350, { steps: 10 }); await page.mouse.up(); });
  await page.waitForTimeout(3000);
  const after = await probe();
  const annotations = await page.evaluate(() => {
    const { annotation } = window.cornerstoneTools ?? {};
    return annotation ? annotation.state.getAllAnnotations().map((a) => `${a.metadata.toolName}@${a.metadata.viewportId ?? ""}`) : "cornerstoneTools not on window";
  });
  await page.screenshot({ path: `shot-${v}.png`, fullPage: true });
  console.log(JSON.stringify({ variant: v, log, consoleErrs: [...new Set(consoleErrs)].slice(0, 25), failed: failed.slice(0, 15), before, after, acts, annotations }, null, 1));
  await page.close();
}
await browser.close();
