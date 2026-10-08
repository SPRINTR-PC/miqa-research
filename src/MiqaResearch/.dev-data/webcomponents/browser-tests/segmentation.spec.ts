// #286 segmentation on the harness CT (16 slices, 64 × 64 px: a sphere with a left→right HU ramp,
// −200 to 200, in air): brush paints and right-drag erases on a stack and a volume; the stack's
// Rectangle ROI threshold fills exactly the pixels in range; a full budget refuses the labelmap.
import type { Locator } from "@playwright/test";

import { expect, seed, test, type ViewerPage } from "./fixtures.ts";

interface SegmentationState {
  active: number;
  thresholdRectangles: number;
  voxels: Record<number, number>;
}

const segmentation = (viewerPage: ViewerPage) =>
  viewerPage.viewer.evaluate((el) => (el as unknown as { segmentationState?: SegmentationState }).segmentationState);
const painted = async (viewerPage: ViewerPage) => (await segmentation(viewerPage))?.voxels[1] ?? 0;

/** Drag across `target`'s centre, `dx` px wide. */
async function stroke(viewerPage: ViewerPage, target: Locator, button: "left" | "right", dx: number) {
  const box = (await target.boundingBox())!;
  const { mouse } = viewerPage.page;
  const y = box.y + box.height / 2;
  await mouse.move(box.x + box.width / 2 - dx / 2, y);
  await mouse.down({ button });
  await mouse.move(box.x + box.width / 2 + dx / 2, y, { steps: 10 });
  await mouse.up({ button });
}

async function openCt(viewerPage: ViewerPage) {
  await viewerPage.open(seed().ct);
  await expect(viewerPage.viewer).toHaveAttribute("state", "ready");
}

test("stack: the brush paints the active segment and right-drag erases it", async ({ viewerPage }) => {
  await openCt(viewerPage);

  await viewerPage.press("g");
  await expect.poll(async () => (await viewerPage.stackState()).activeTool).toBe("Brush");
  await stroke(viewerPage, viewerPage.viewport, "left", 120);

  await expect.poll(() => painted(viewerPage)).toBeGreaterThan(0);
  const before = await painted(viewerPage);

  await stroke(viewerPage, viewerPage.viewport, "right", 120);

  await expect.poll(() => painted(viewerPage)).toBeLessThan(before);
  // Right-drag erased instead of windowing.
  await expect(viewerPage.page.locator("mires-viewer .overlay")).toContainText("W 400 L 40");
});

test("volume: the brush paints in an axial view and right-drag erases", async ({ viewerPage }) => {
  await openCt(viewerPage);
  await viewerPage.page.locator('mires-viewer [data-layout="axial"]').click();
  await expect(viewerPage.page.locator("mires-viewer .vcell canvas")).toHaveCount(1);
  await expect
    .poll(() => viewerPage.page.evaluate(() => performance.getEntriesByType("mark").map((m) => m.name)))
    .toContain("mires-viewer:volume-loaded");
  const view = viewerPage.page.locator('mires-viewer .vcell[data-slot="0"]');

  await viewerPage.press("g");
  await stroke(viewerPage, view, "left", 120);

  await expect.poll(() => painted(viewerPage)).toBeGreaterThan(0);
  const before = await painted(viewerPage);

  await stroke(viewerPage, view, "right", 120);

  await expect.poll(() => painted(viewerPage)).toBeLessThan(before);
});

/** Pixels with HU in [0, 300] on slice 8 (or 9) of 16, z = ±1.25 mm from the sphere's centre. */
function expectedThresholdPixels(): number {
  // Seed: HU = −200 + 400·x/63 inside (x − 31.5)² + (y − 31.5)² + z² ≤ 28.8², else −1000: HU ≥ 0 ⇔ x ≥ 32.
  let n = 0;
  for (let y = 0; y < 64; y++) for (let x = 32; x < 64; x++) if ((x - 31.5) ** 2 + (y - 31.5) ** 2 + 1.25 ** 2 <= 28.8 ** 2) n++;
  return n;
}

/** Threshold tool: a rectangle over the whole of `target`, then run [0, 300] on its slice only. */
async function runThreshold(viewerPage: ViewerPage, target: Locator) {
  await viewerPage.press("m");
  const box = (await target.boundingBox())!;
  const { mouse } = viewerPage.page;
  await mouse.move(box.x + 4, box.y + 4);
  await mouse.down();
  await mouse.move(box.x + box.width - 4, box.y + box.height - 4, { steps: 10 });
  await mouse.up();
  await expect.poll(async () => (await segmentation(viewerPage))?.thresholdRectangles).toBe(1);

  const form = viewerPage.page.locator("mires-viewer .segments form.threshold");
  await form.locator("input[name=lower]").fill("0");
  await form.locator("input[name=upper]").fill("300");
  await form.locator('[data-action="threshold"]').click();
  return form;
}

test("stack threshold fills exactly the pixels within the range inside the rectangle", async ({ viewerPage }) => {
  await openCt(viewerPage);
  // Slice 8 of 16: z = ±1.25 mm from the sphere's centre (either slice order).
  await viewerPage.viewer.evaluate((el) => (el as unknown as { stackView: { scrollTo(i: number): void } }).stackView.scrollTo(7));
  await expect.poll(async () => (await viewerPage.stackState()).imageIndex).toBe(7);

  const form = await runThreshold(viewerPage, viewerPage.viewport);

  const expected = expectedThresholdPixels();
  await expect.poll(() => painted(viewerPage)).toBe(expected);
  expect((await segmentation(viewerPage))!.thresholdRectangles).toBe(0);
  await expect(form.locator(".threshold-result")).toContainText(`${expected} voxels`);
});

test("volume threshold (CS3D's helper on the base volume) fills the pixels within the range", async ({ viewerPage }) => {
  await openCt(viewerPage);
  await viewerPage.page.locator('mires-viewer [data-layout="axial"]').click();
  await expect
    .poll(() => viewerPage.page.evaluate(() => performance.getEntriesByType("mark").map((m) => m.name)))
    .toContain("mires-viewer:volume-loaded");
  // The axial view opens on the middle slice (8 or 9 of 16).
  const state = await viewerPage.viewer.evaluate((el) => (el as unknown as { volumeState: { views: { sliceIndex: number }[] } }).volumeState);
  expect([7, 8]).toContain(state.views[0].sliceIndex);

  await runThreshold(viewerPage, viewerPage.page.locator('mires-viewer .vcell[data-slot="0"]'));

  await expect.poll(() => painted(viewerPage)).toBe(expectedThresholdPixels());
});

test("a labelmap over the budget is refused with the size guard's message", async ({ viewerPage }) => {
  await openCt(viewerPage);
  await viewerPage.viewer.evaluate((el) => {
    const { budget } = el as unknown as { budget: { budget: number; reserve(e: object[]): unknown } };
    budget.reserve([{ id: "test-fill", series: "elsewhere", kind: "volume", bytes: budget.budget - 1 }]);
  });

  await viewerPage.press("g");

  await expect(viewerPage.page.locator("mires-viewer .refusal")).toContainText("Save and close the other Segmentation first.");
  expect(await segmentation(viewerPage)).toBeUndefined();
  expect((await viewerPage.stackState()).activeTool).toBe("WindowLevel");
});
