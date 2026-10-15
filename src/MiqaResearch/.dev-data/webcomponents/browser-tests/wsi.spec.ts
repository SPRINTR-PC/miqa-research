// #285 WSI: the seeded TILED_FULL slide through WSIViewport + dicom-microscopy-viewer, from our /frames.
import { expect, seed, test } from "./fixtures.ts";

test.describe("whole-slide image", () => {
  test("tiles load from our /frames as JPEG", async ({ viewerPage }) => {
    const { wsi } = seed();
    const tiles: { url: string; status: number; type: string }[] = [];
    const wasm: { url: string; type: string }[] = [];
    // Context-wide: dmv fetches tiles and its WASM codecs from web workers too.
    viewerPage.page.context().on("response", (r) => {
      const type = r.headers()["content-type"] ?? "";
      if (r.url().includes("/frames/")) tiles.push({ url: r.url(), status: r.status(), type });
      if (r.url().endsWith(".wasm")) wasm.push({ url: r.url(), type });
    });

    await viewerPage.open(wsi);

    await expect(viewerPage.viewer).toHaveAttribute("state", "ready");
    await expect.poll(() => tiles.length).toBeGreaterThan(0);
    for (const tile of tiles) {
      expect(new URL(tile.url).pathname).toMatch(
        new RegExp(`^/api/v1/dicom/studies/${wsi.studyUid}/series/${wsi.seriesUid}/instances/[\\d.]+/frames/\\d+$`),
      );
      expect(tile.status).toBe(200);
      expect(tile.type).toContain("multipart/related");
    }
    // dmv's JPEG codec comes from the viewer's own dmv/ directory, as application/wasm.
    await expect.poll(() => wasm.find((w) => w.url.includes("/static/js/viewer/dmv/libjpegturbowasm_decode.wasm"))?.type).toBe(
      "application/wasm",
    );
  });

  test("the overview control sits bottom-left inside the viewport (head CSS mirrored into the shadow root)", async ({ viewerPage }) => {
    await viewerPage.open(seed().wsi);
    await expect(viewerPage.viewer).toHaveAttribute("state", "ready");

    const overview = viewerPage.page.locator("mires-viewer .ol-overviewmap");
    await expect(overview).toBeVisible();
    const box = (await overview.boundingBox())!;
    const vp = (await viewerPage.viewport.boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(vp.x);
    expect(box.x + box.width).toBeLessThan(vp.x + vp.width / 2);
    expect(box.y).toBeGreaterThan(vp.y + vp.height / 2);
    expect(box.y + box.height).toBeLessThanOrEqual(vp.y + vp.height + 1);
    expect(box.height).toBeGreaterThan(50);
  });

  test("offers the WSI tool set; wheel zooms; Length draws a measurement", async ({ viewerPage }) => {
    await viewerPage.open(seed().wsi);
    await expect(viewerPage.viewer).toHaveAttribute("state", "ready");
    expect(await viewerPage.railTools()).toEqual([
      "Pan",
      "Zoom",
      "Length",
      "RectangleROI",
      "EllipticalROI",
      "PlanarFreehandROI",
      "ArrowAnnotate",
    ]);
    const before = await viewerPage.stackState();
    expect(before.unit).toBe("mm");

    await viewerPage.viewport.hover();
    for (let i = 0; i < 3; i++) await viewerPage.page.mouse.wheel(0, -120);
    await expect.poll(async () => (await viewerPage.stackState()).zoom).toBeGreaterThan(before.zoom);

    await viewerPage.press("l");
    await viewerPage.drag("left", 160, 0);

    await expect.poll(async () => (await viewerPage.stackState()).annotationCount).toBe(1);
    expect((await viewerPage.stackState()).activeTool).toBe("Length");
  });
});
