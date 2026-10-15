// #278 tracer bullet: a CT series from our WADO renders, scrolls and windows in headless Chromium.
import { readdirSync } from "node:fs";

import { expect, seed, test } from "./fixtures.ts";

const VIEWER_ASSETS = new URL("../../../static/js/viewer/assets/", import.meta.url);

test("CT stack renders the first image with the series window", async ({ viewerPage }) => {
  const { ct } = seed();

  await viewerPage.open(ct);

  await expect(viewerPage.viewer).toHaveAttribute("state", "ready");
  await expect(viewerPage.page.locator("mires-viewer .overlay")).toHaveText(`Image 1 / ${ct.imageCount} · W 400 L 40`);
  expect(await viewerPage.canvasSignature()).toBeGreaterThan(0);
});

test("mouse wheel scrolls through the stack", async ({ viewerPage }) => {
  const { ct } = seed();
  await viewerPage.open(ct);
  await expect(viewerPage.page.locator("mires-viewer .overlay")).toContainText("Image 1 /");
  const first = await viewerPage.canvasSignature();

  await viewerPage.viewport.hover();
  for (let i = 0; i < 4; i++) await viewerPage.page.mouse.wheel(0, 120);

  await expect.poll(async () => (await viewerPage.stackState()).imageIndex).toBeGreaterThanOrEqual(2);
  await expect.poll(() => viewerPage.canvasSignature()).not.toBe(first);
});

test("left-drag changes the window", async ({ viewerPage }) => {
  const { ct } = seed();
  await viewerPage.open(ct);
  await expect(viewerPage.page.locator("mires-viewer .overlay")).toContainText("W 400 L 40");
  const before = await viewerPage.canvasSignature();

  const box = (await viewerPage.viewport.boundingBox())!;
  const { mouse } = viewerPage.page;
  await mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await mouse.down();
  await mouse.move(box.x + box.width / 2 + 80, box.y + box.height / 2 + 60, { steps: 8 });
  await mouse.up();

  await expect(viewerPage.page.locator("mires-viewer .overlay")).not.toContainText("W 400 L 40");
  await expect.poll(() => viewerPage.canvasSignature()).not.toBe(before);
});

test("a series the user can't see shows an error instead of an image", async ({ viewerPage }) => {
  await viewerPage.open({ studyUid: "2.25.1", seriesUid: "2.25.2" });

  await expect(viewerPage.viewer).toHaveAttribute("state", "error");
  // The dev page leaves out series the user can't see (#279), so there is nothing to open.
  await expect(viewerPage.page.locator("mires-viewer [role=alert]")).toContainText("No series to open");
});

test("static server serves the codec WASM as application/wasm", async ({ request }) => {
  const wasm = readdirSync(VIEWER_ASSETS).find((f) => f.endsWith(".wasm"));
  expect(wasm, "build the viewer first: npm run build:viewer").toBeTruthy();

  const response = await request.get(`/static/js/viewer/assets/${wasm}`);

  expect(response.status()).toBe(200);
  expect(response.headers()["content-type"]).toBe("application/wasm");
});
