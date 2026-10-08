// #281 spacing calibration in a real browser: CS3D's unit for CR/SC/no-spacing images from our WADO,
// the calibration legend, the burned-in badge and User calibration.
import { expect, seed, test, type ViewerPage } from "./fixtures.ts";

const unit = (v: ViewerPage) => v.page.locator("mires-viewer .unit");
const legend = (v: ViewerPage) => v.page.locator("mires-viewer .calibration");

/** Text of the measurement labels CS3D draws in the viewport's SVG layer. */
function measurementLabels(v: ViewerPage): Promise<string[]> {
  return v.page
    .locator("mires-viewer .viewport svg text")
    .evaluateAll((els) => els.map((e) => e.textContent ?? "").filter((t) => /\d/.test(t)));
}

/** Left-drag a horizontal line of `length` CSS px, `dy` px below the viewport centre. */
async function drawLine(v: ViewerPage, length: number, dy: number) {
  const box = (await v.viewport.boundingBox())!;
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2 + dy;
  await v.page.mouse.move(x - length / 2, y);
  await v.page.mouse.down();
  await v.page.mouse.move(x + length / 2, y, { steps: 10 });
  await v.page.mouse.up();
}

async function openReady(v: ViewerPage, series: { studyUid: string; seriesUid: string }) {
  await v.open(series);
  await expect(v.viewer).toHaveAttribute("state", "ready");
}

test("a CR with only ImagerPixelSpacing shows mm Proj and the Proj legend", async ({ viewerPage }) => {
  await openReady(viewerPage, seed().cr);

  await expect(unit(viewerPage)).toHaveText("mm Proj");
  await expect(legend(viewerPage).locator(".badge")).toHaveText("Detector plane (Proj)");
  await expect(legend(viewerPage)).toContainText(/overestimated/);
  await expect(viewerPage.page.locator("mires-viewer .burned-in")).toHaveCount(0);
});

test("an SC with PixelSpacing shows mm Unknown, labelled unverified, with the burned-in badge", async ({ viewerPage }) => {
  await openReady(viewerPage, seed().sc);

  await expect(unit(viewerPage)).toHaveText("mm Unknown");
  await expect(legend(viewerPage).locator(".badge")).toHaveText("Unverified (SC)");
  await expect(legend(viewerPage)).toContainText("Spacing from secondary capture — unverified");
  await expect(viewerPage.page.locator("mires-viewer .burned-in")).toBeVisible();
});

test("an image without spacing measures in px", async ({ viewerPage }) => {
  await openReady(viewerPage, seed().noSpacing);

  await expect(unit(viewerPage)).toHaveText("px");
  await expect(legend(viewerPage).locator(".badge")).toHaveText("No spacing (px)");
});

test("CT shows no legend", async ({ viewerPage }) => {
  await openReady(viewerPage, seed().ct);

  await expect(unit(viewerPage)).toHaveText("mm");
  await expect(legend(viewerPage)).toHaveCount(0);
});

test("User calibration changes the Length value and shows mm User", async ({ viewerPage }) => {
  await openReady(viewerPage, seed().noSpacing);
  await viewerPage.press("l");
  await drawLine(viewerPage, 120, -60);
  await expect.poll(async () => (await viewerPage.stackState()).annotationCount).toBe(1);
  await expect.poll(() => measurementLabels(viewerPage)).toEqual([expect.stringMatching(/ px$/)]);

  // A Calibrate line as long (same screen length), told it is 50 mm: the Length now reads ~50 mm User.
  await viewerPage.press("c");
  await drawLine(viewerPage, 120, 60);
  await expect.poll(async () => (await viewerPage.stackState()).pendingCalibration?.unit).toBe("px");
  // Enter submits (the dev page's debug toolbar can cover the Apply button).
  await legend(viewerPage).locator("input").fill("50");
  await legend(viewerPage).locator("input").press("Enter");

  await expect(unit(viewerPage)).toHaveText("mm User");
  await expect(legend(viewerPage).locator(".badge")).toHaveText("User-calibrated");
  await expect.poll(() => measurementLabels(viewerPage)).toEqual([expect.stringMatching(/ mm User$/)]);
  const lengthMm = parseFloat((await measurementLabels(viewerPage))[0]);
  expect(Math.abs(lengthMm - 50)).toBeLessThan(2.5); // both lines snap to image pixels
  const state = await viewerPage.stackState();
  expect(state.annotationCount).toBe(1);
  expect(state.activeTool).toBe("Length");
});

test.describe("view-only user", () => {
  test.use({ viewOnly: true });

  test("cannot calibrate", async ({ viewerPage }) => {
    await openReady(viewerPage, seed().noSpacing);

    expect(await viewerPage.railTools()).not.toContain("Calibrate");
    await viewerPage.press("c");
    expect((await viewerPage.stackState()).activeTool).toBe("WindowLevel");
  });
});
