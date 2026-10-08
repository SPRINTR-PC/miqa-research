// #282 volumes: the CT as a streaming volume in ORTHOGRAPHIC views, 1×1 orientation + V, three views
// with crosshairs, double-click swap, and the volume first-render marks (#293).
import type { Page } from "@playwright/test";

import { expect, seed, test, type ViewerPage } from "./fixtures.ts";

interface VolumeState {
  activeTool: string;
  views: { orientation: string; focalPoint: [number, number, number]; sliceIndex: number; sliceCount: number }[];
}

const volumeState = (viewerPage: ViewerPage) =>
  viewerPage.viewer.evaluate((el) => (el as unknown as { volumeState?: VolumeState }).volumeState);

const marks = (page: Page) => page.evaluate(() => performance.getEntriesByType("mark").map((m) => m.name));

async function openLayout(viewerPage: ViewerPage, layout: string) {
  await viewerPage.open(seed().ct);
  await expect(viewerPage.viewer).toHaveAttribute("state", "ready");
  await viewerPage.page.locator(`mires-viewer [data-layout="${layout}"]`).click();
  await expect.poll(async () => (await volumeState(viewerPage))?.views.length).toBe(layout === "three" ? 3 : 1);
  // Wait for the whole volume, so focal points don't move under the test.
  await expect.poll(() => marks(viewerPage.page)).toContain("mires-viewer:volume-loaded");
}

test("three views: dragging the crosshair in axial moves the sagittal and coronal focal points", async ({ viewerPage }) => {
  await openLayout(viewerPage, "three");
  const before = (await volumeState(viewerPage))!;
  expect(before.activeTool).toBe("Crosshairs");
  expect(before.views.map((v) => v.orientation)).toEqual(["axial", "sagittal", "coronal"]);
  await expect(viewerPage.page.locator("mires-viewer .vcell canvas")).toHaveCount(3);

  const box = (await viewerPage.page.locator('mires-viewer .vcell[data-slot="0"]').boundingBox())!;
  const { mouse } = viewerPage.page;
  const cx = box.x + box.width / 2;
  const cy = box.y + box.height / 2;
  await mouse.move(cx, cy);
  await mouse.down();
  await mouse.move(cx + box.width / 6, cy + box.height / 8, { steps: 10 });
  await mouse.up();

  await expect
    .poll(async () => {
      const after = (await volumeState(viewerPage))!;
      return [1, 2].map((slot) => after.views[slot].focalPoint.join() !== before.views[slot].focalPoint.join());
    })
    .toEqual([true, true]);
  // Dragging within the axial plane doesn't change the axial slice.
  expect((await volumeState(viewerPage))!.views[0].sliceIndex).toBe(before.views[0].sliceIndex);
});

test("1×1: V cycles the orientation of the one view", async ({ viewerPage }) => {
  await openLayout(viewerPage, "axial");
  expect((await volumeState(viewerPage))!.views[0].sliceCount).toBe(seed().ct.imageCount);

  await viewerPage.press("v");
  await expect.poll(async () => (await volumeState(viewerPage))!.views[0].orientation).toBe("sagittal");
  await viewerPage.press("v");
  await expect.poll(async () => (await volumeState(viewerPage))!.views[0].orientation).toBe("coronal");
  expect(await viewerPage.railTools()).not.toContain("Crosshairs");
});

test("three views: double-clicking a small view swaps it into the big one", async ({ viewerPage }) => {
  await openLayout(viewerPage, "three");

  await viewerPage.page.locator('mires-viewer .vcell[data-slot="2"]').dblclick();

  await expect
    .poll(async () => (await volumeState(viewerPage))!.views.map((v) => v.orientation))
    .toEqual(["coronal", "sagittal", "axial"]);
});

test("the volume sets the interleaved and volume-loaded first-render marks", async ({ viewerPage }) => {
  await openLayout(viewerPage, "three");

  expect(await marks(viewerPage.page)).toEqual(
    expect.arrayContaining(["mires-viewer:first-image", "mires-viewer:interleaved", "mires-viewer:volume-loaded"]),
  );
});
