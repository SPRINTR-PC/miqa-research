// #283 size guard: with MAX_3D_TEXTURE_SIZE stubbed below the CT's 64 × 64 px, the CT opens as the
// full-resolution stack with a banner, and "Open reduced 3D (view only)" opens a decimated volume
// in three views without measurement or annotation tools.
import { expect, seed, test } from "./fixtures.ts";

interface VolumeState {
  views: { orientation: string; sliceCount: number }[];
}

test.beforeEach(async ({ page }) => {
  // Only the size guard reads MAX_3D_TEXTURE_SIZE (CS3D and vtk.js don't).
  await page.addInitScript(() => {
    const original = WebGL2RenderingContext.prototype.getParameter;
    WebGL2RenderingContext.prototype.getParameter = function (this: WebGL2RenderingContext, p: number) {
      return p === this.MAX_3D_TEXTURE_SIZE ? 32 : original.call(this, p);
    };
  });
});

test("a series beyond the 3D texture limit opens as a stack with a banner; reduced 3D is view only", async ({ viewerPage }) => {
  const { page, viewer } = viewerPage;
  await viewerPage.open(seed().ct);
  await expect(viewer).toHaveAttribute("state", "ready");

  const banner = page.locator("mires-viewer .size-banner");
  await expect(banner).toContainText("exceed the GPU's 3D texture limit (32)");
  await expect(banner).toContainText("MPR, crosshairs and fusion are off");
  expect((await viewerPage.stackState()).imageCount).toBe(seed().ct.imageCount);
  expect(await viewerPage.railTools()).toContain("Length");
  await expect(page.locator('mires-viewer [data-layout="axial"]')).toHaveCount(0);

  await page.locator('mires-viewer [data-layout="reduced"]').click();

  await expect
    .poll(() => viewer.evaluate((el) => (el as unknown as { volumeState?: VolumeState }).volumeState?.views.length))
    .toBe(3);
  await expect(page.locator("mires-viewer .vcell canvas")).toHaveCount(3);
  await expect(banner).toContainText("Reduced 3D (view only)");
  const rail = await viewerPage.railTools();
  expect(rail).toEqual(expect.arrayContaining(["WindowLevel", "Crosshairs"]));
  for (const tool of ["Length", "Angle", "RectangleROI", "ArrowAnnotate", "Calibrate"]) expect(rail).not.toContain(tool);
  // In-plane halved (64 → 32 px); every slice kept: the axial view still has all slices.
  const state = await viewer.evaluate((el) => (el as unknown as { volumeState: VolumeState }).volumeState);
  expect(state.views[0].sliceCount).toBe(seed().ct.imageCount);
  expect(state.views[1].sliceCount).toBe(32);
});
