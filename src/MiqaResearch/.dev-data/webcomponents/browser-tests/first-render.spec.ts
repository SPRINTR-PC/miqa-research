// #293: first-render performance marks and the beacon to /api/v1/viewer/first-render.
import { expect, seed, test } from "./fixtures.ts";

test("opening a series sets the first-render marks and sends the beacon on leaving", async ({ viewerPage }) => {
  const { ct } = seed();
  const { page } = viewerPage;

  await viewerPage.open(ct);
  await expect(viewerPage.viewer).toHaveAttribute("state", "ready");

  const marks = await page.evaluate(() => performance.getEntriesByType("mark").map((m) => m.name));
  expect(marks).toEqual(expect.arrayContaining(["mires-viewer:open", "mires-viewer:first-image"]));

  const beacon = page.waitForRequest("**/api/v1/viewer/first-render");
  await page.evaluate(() => document.querySelector("mires-viewer")!.remove());
  const request = await beacon;

  const body = request.postDataJSON();
  expect(Object.keys(body).sort()).toEqual(["bytes", "first_image_ms", "slices", "transfer_syntax"]);
  expect(body.slices).toBe(ct.imageCount);
  expect(body.first_image_ms).toBeGreaterThan(0);
  expect(body.bytes).toBeGreaterThan(0);
  expect(JSON.stringify(body)).not.toContain(ct.studyUid);
  expect((await request.response())!.status()).toBe(204);
});
