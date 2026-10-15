// #290 Results tree in a real browser: show / hide a saved SR and SEG from the series list (CS3D import from
// WADO /metadata, SEG frames from /frames), bringing a source series that isn't in view in, Retire, the
// Blinded Annotation lock row and Blinding Reveal, and the view-only state.
// The harness database is kept between runs: each test finds the objects it saved by chain id.
import type { Locator, Page } from "@playwright/test";

import { expect, seed, test, type SeriesRef, type ViewerPage } from "./fixtures.ts";

interface Version {
  id: string;
  chain_id: string;
  version: number;
}

const row = (v: ViewerPage, chainId: string) => v.page.locator(`mires-viewer .result[data-chain="${chainId}"]`);
const chip = (v: ViewerPage, chainId: string) => v.page.locator(`mires-viewer .chip[data-chain="${chainId}"]`);

async function openReady(v: ViewerPage, series: SeriesRef, related: SeriesRef[] = []) {
  await v.open(series, related);
  await expect(v.viewer).toHaveAttribute("state", "ready");
}

async function drawLength(v: ViewerPage) {
  const before = (await v.stackState()).annotationCount;
  await v.press("l");
  await v.drag("left", 100, 0);
  await expect.poll(async () => (await v.stackState()).annotationCount).toBe(before + 1);
}

/** Click Save of `kind`; the 201 body. */
async function save(v: ViewerPage, kind: "annotation" | "segmentation"): Promise<Version> {
  const saved = v.page.waitForResponse((r) => r.url().endsWith("/api/v1/viewer/objects") && r.request().method() === "POST");
  await v.page.locator(`mires-viewer [data-save="${kind}"]`).click();
  const response = await saved;
  expect(response.status()).toBe(201);
  return response.json();
}

/** Save a Length (SR) and a painted segment (SEG) on the CT. */
async function saveSrAndSeg(v: ViewerPage): Promise<{ sr: Version; seg: Version }> {
  const { ct } = seed();
  await openReady(v, ct);
  await drawLength(v);
  const sr = await save(v, "annotation");
  await v.press("g");
  await expect.poll(async () => (await v.stackState()).activeTool).toBe("Brush");
  await v.drag("left", 120, 0);
  const seg = await save(v, "segmentation");
  return { sr, seg };
}

const segVoxels = (page: Page) =>
  page.locator("mires-viewer").evaluate((el) => {
    const state = (el as unknown as { segmentationState?: { voxels: Record<number, number> } }).segmentationState;
    return state ? Object.values(state.voxels).reduce((a, b) => a + b, 0) : undefined;
  });

async function clickShow(r: Locator) {
  await r.locator(".show").click();
  await expect(r).toHaveAttribute("aria-busy", "false");
}

test("show and hide a saved SR and SEG from the tree; Save then supersedes the shown head", async ({ viewerPage }) => {
  const { sr, seg } = await saveSrAndSeg(viewerPage);
  const { ct } = seed();
  await openReady(viewerPage, ct); // a fresh viewer: nothing drawn
  expect((await viewerPage.stackState()).annotationCount).toBe(0);

  await expect(row(viewerPage, sr.chain_id)).toBeVisible();
  await clickShow(row(viewerPage, sr.chain_id));
  await expect.poll(async () => (await viewerPage.stackState()).annotationCount).toBe(1);
  await expect(chip(viewerPage, sr.chain_id)).toContainText("Annotations v1");
  await expect(viewerPage.page.locator('mires-viewer [data-save="annotation"]')).toContainText("Supersede v1 → v2");

  await chip(viewerPage, sr.chain_id).locator("button").click();
  await expect.poll(async () => (await viewerPage.stackState()).annotationCount).toBe(0);
  await expect(chip(viewerPage, sr.chain_id)).toHaveCount(0);

  await clickShow(row(viewerPage, seg.chain_id));
  await expect.poll(() => segVoxels(viewerPage.page)).toBeGreaterThan(0);
  await expect(chip(viewerPage, seg.chain_id)).toContainText("Segmentation v1");
  await expect(viewerPage.page.locator('mires-viewer [data-save="segmentation"]')).toContainText("Supersede v1 → v2");

  await clickShow(row(viewerPage, seg.chain_id)); // click again hides
  await expect.poll(() => segVoxels(viewerPage.page)).toBeUndefined();
});

test("showing an object of a series that isn't in view brings that series in", async ({ viewerPage }) => {
  const { sr } = await saveSrAndSeg(viewerPage);
  const { ct, pet } = seed();
  await openReady(viewerPage, pet, [ct]); // the PET is shown, the CT only listed
  expect((await viewerPage.stackState()).imageCount).toBe(pet.imageCount);

  await clickShow(row(viewerPage, sr.chain_id));

  await expect.poll(async () => (await viewerPage.stackState()).imageCount).toBe(ct.imageCount);
  await expect(viewerPage.page.locator(`mires-viewer .ser.shown`)).toHaveAttribute("data-series-uid", ct.seriesUid);
  await expect.poll(async () => (await viewerPage.stackState()).annotationCount).toBe(1);
});

test("Retire asks first, then the row is gone", async ({ viewerPage }) => {
  const { ct } = seed();
  await openReady(viewerPage, ct);
  await drawLength(viewerPage);
  const sr = await save(viewerPage, "annotation");
  await openReady(viewerPage, ct);

  await row(viewerPage, sr.chain_id).locator(".more").click();
  await row(viewerPage, sr.chain_id).locator('[data-action="retire"]').click();
  await expect(viewerPage.page.locator("mires-viewer .results-confirm")).toContainText("disappears from lists and counts");
  await viewerPage.page.locator('mires-viewer [data-confirm="ok"]').click();

  await expect(row(viewerPage, sr.chain_id)).toHaveCount(0);
  await viewerPage.page.locator("mires-viewer .show-retired").check();
  await expect(row(viewerPage, sr.chain_id)).toHaveClass(/retired/);
  await expect(row(viewerPage, sr.chain_id).locator(".show")).toBeDisabled();
});

test("Blinded Annotation: the lock row counts hidden work; the PI's Blinding Reveal lists it", async ({ viewerPage }) => {
  const { blinded } = seed();
  await openReady(viewerPage, blinded);
  const lock = viewerPage.page.locator("mires-viewer .lock-row");
  await expect(lock).toContainText("showing only your own work");
  await expect(lock.locator(".hidden-count")).toHaveText("1");
  await expect(viewerPage.page.locator("mires-viewer .result")).toHaveCount(0);

  await lock.locator('[data-action="reveal"]').click();
  await expect(viewerPage.page.locator("mires-viewer .results-confirm")).toContainText("audit-logged");
  await viewerPage.page.locator('mires-viewer [data-confirm="ok"]').click();

  await expect(lock).toContainText("Blinding Reveal active");
  await expect(viewerPage.page.locator("mires-viewer .result")).toHaveCount(1);
  await expect(viewerPage.page.locator("mires-viewer .result")).toContainText("ingested");
});

test.describe("view-only", () => {
  test.use({ viewOnly: true });

  test("the same tree, read-only: show works; no save, retire, show retired or reveal", async ({ viewerPage }) => {
    const { ct } = seed();
    await openReady(viewerPage, ct);
    const first = viewerPage.page.locator("mires-viewer .result").filter({ hasText: "Annotations" }).first();
    await expect(first).toBeVisible(); // earlier tests (and runs) saved some

    await clickShow(first);
    await expect.poll(async () => (await viewerPage.stackState()).annotationCount).toBeGreaterThan(0);
    await expect(viewerPage.page.locator("mires-viewer .chip")).toHaveCount(1);

    await first.locator(".more").click();
    await expect(first.locator('[data-action="history"]')).toBeVisible();
    await expect(first.locator('[data-action="retire"]')).toHaveCount(0);
    await expect(viewerPage.page.locator("mires-viewer .show-retired")).toHaveCount(0);
    await expect(viewerPage.page.locator("mires-viewer [data-save]")).toHaveCount(0);
    await expect(viewerPage.page.locator('mires-viewer [data-action="reveal"]')).toHaveCount(0);
  });
});
