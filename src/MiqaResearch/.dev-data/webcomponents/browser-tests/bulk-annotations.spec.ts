// #292 Bulk ANN: the seeded slide's ANN (two POLYGON groups, pure green "Neoplasm" and magenta
// "Connective tissue") rendered read-only by dicom-microscopy-viewer, toggled per group.
import type { Page } from "@playwright/test";

import { expect, seed, test, type ViewerPage } from "./fixtures.ts";

interface Blob {
  /** Pixels of the group's colour on the 2D (vector) canvases. */
  n: number;
  /** Centroid and one pixel of it, in page coordinates. */
  cx: number;
  cy: number;
  x: number;
  y: number;
}

/** Find each group's colour on the viewport's 2D canvases (the slide's tiles are WebGL; vector layers are 2D). */
function annotationPixels(page: Page): Promise<{ green: Blob; magenta: Blob }> {
  return page.locator("mires-viewer .viewport canvas").evaluateAll((canvases) => {
    const blob = () => ({ n: 0, cx: 0, cy: 0, x: 0, y: 0 });
    const out = { green: blob(), magenta: blob() };
    for (const c of canvases as HTMLCanvasElement[]) {
      if (!c.width || !c.height) continue;
      const ctx = c.getContext("2d");
      if (!ctx) continue;
      const rect = c.getBoundingClientRect();
      const sx = rect.width / c.width;
      const sy = rect.height / c.height;
      const data = ctx.getImageData(0, 0, c.width, c.height).data;
      for (let i = 0; i < data.length; i += 4) {
        const [r, g, b] = [data[i], data[i + 1], data[i + 2]];
        const key = g > 180 && r < 90 && b < 90 ? "green" : r > 180 && b > 180 && g < 90 ? "magenta" : undefined;
        if (!key) continue;
        const px = (i / 4) % c.width;
        const py = Math.floor(i / 4 / c.width);
        const o = out[key];
        o.n += 1;
        o.cx += rect.left + px * sx;
        o.cy += rect.top + py * sy;
        o.x = rect.left + px * sx;
        o.y = rect.top + py * sy;
      }
    }
    for (const o of Object.values(out)) if (o.n) Object.assign(o, { cx: o.cx / o.n, cy: o.cy / o.n });
    return out;
  });
}

const toggle = (viewerPage: ViewerPage, name: string) =>
  viewerPage.page.locator("mires-viewer [data-panel=bulk-annotations] label").filter({ hasText: name }).locator("input");

test.describe("bulk annotations (ANN) on a slide", () => {
  test("groups are listed and shown; toggling hides and shows each", async ({ viewerPage }) => {
    const { wsi, wsiAnnotations } = seed();
    await viewerPage.open(wsi);
    await expect(viewerPage.viewer).toHaveAttribute("state", "ready");

    const panel = viewerPage.page.locator("mires-viewer [data-panel=bulk-annotations]");
    await expect(panel.locator("label")).toHaveCount(wsiAnnotations.groups.length);
    for (const name of wsiAnnotations.groups) await expect(panel).toContainText(name);
    await expect.poll(async () => (await annotationPixels(viewerPage.page)).green.n).toBeGreaterThan(100);
    expect((await annotationPixels(viewerPage.page)).magenta.n).toBeGreaterThan(100);

    await toggle(viewerPage, "Neoplasm").uncheck();
    await expect.poll(async () => (await annotationPixels(viewerPage.page)).green.n).toBe(0);
    expect((await annotationPixels(viewerPage.page)).magenta.n).toBeGreaterThan(100);

    await toggle(viewerPage, "Connective tissue").uncheck();
    await expect.poll(async () => (await annotationPixels(viewerPage.page)).magenta.n).toBe(0);

    await toggle(viewerPage, "Neoplasm").check();
    await expect.poll(async () => (await annotationPixels(viewerPage.page)).green.n).toBeGreaterThan(100);
    expect((await annotationPixels(viewerPage.page)).magenta.n).toBe(0);
  });

  test("no editing: dragging on a group, drawing over it and Delete leave it unchanged", async ({ viewerPage }) => {
    await viewerPage.open(seed().wsi);
    await expect(viewerPage.viewer).toHaveAttribute("state", "ready");
    await expect.poll(async () => (await annotationPixels(viewerPage.page)).green.n).toBeGreaterThan(100);
    await viewerPage.press("Escape"); // fitted home view, to compare against
    await viewerPage.page.waitForTimeout(500);
    const before = (await annotationPixels(viewerPage.page)).green;
    const { mouse } = viewerPage.page;

    // Drag starting on the outline (Pan on the left button): moves the slide, never the shape.
    await mouse.move(before.x, before.y);
    await mouse.down();
    await mouse.move(before.x + 80, before.y + 60, { steps: 10 });
    await mouse.up();
    // Length drawn across the shape is a CS3D measurement of its own; the ANN isn't one.
    await viewerPage.press("l");
    await mouse.move(before.cx - 40, before.cy);
    await mouse.down();
    await mouse.move(before.cx + 40, before.cy, { steps: 10 });
    await mouse.up();
    await viewerPage.press("Delete");
    await viewerPage.press("Escape");
    await viewerPage.page.waitForTimeout(500);

    expect((await viewerPage.stackState()).annotationCount).toBe(1);
    const after = (await annotationPixels(viewerPage.page)).green;
    expect(Math.abs(after.n - before.n)).toBeLessThan(before.n * 0.05);
    expect(after.cx).toBeCloseTo(before.cx, 0);
    expect(after.cy).toBeCloseTo(before.cy, 0);
  });
});
