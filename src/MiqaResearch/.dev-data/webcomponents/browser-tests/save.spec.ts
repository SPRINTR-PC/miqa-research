// #289 Save from the viewer in a real browser: SR TID 1500 (CS3D adapters) and SEG to our object API,
// the stored SR's units / calibration qualifier / User reference line (read back through WADO
// /metadata), supersede, and the 409 dialog's three outcomes on a simulated stale head.
// The harness database is kept between runs: assertions look at the objects each test saves.
import type { Page } from "@playwright/test";

import { expect, seed, test, type ViewerPage } from "./fixtures.ts";

type Json = Record<string, { vr: string; Value?: unknown[] }>;
interface Version {
  id: string;
  chain_id: string;
  version: number;
  modality: string;
  author: string | null;
  series_instance_uid: string;
}

const saveButton = (v: ViewerPage, kind: "annotation" | "segmentation") => v.page.locator(`mires-viewer [data-save="${kind}"]`);
const toast = (v: ViewerPage) => v.page.locator("mires-viewer .toast");
const dialog = (v: ViewerPage) => v.page.locator('mires-viewer [role="dialog"]');

async function openReady(v: ViewerPage, series: { studyUid: string; seriesUid: string }) {
  await v.open(series);
  await expect(v.viewer).toHaveAttribute("state", "ready");
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

async function drawLength(v: ViewerPage, dy: number) {
  const before = (await v.stackState()).annotationCount;
  await v.press("l");
  await drawLine(v, 100, dy);
  await expect.poll(async () => (await v.stackState()).annotationCount).toBe(before + 1);
}

/** The participant's object chains (heads), via the object API with the page's session. */
async function chains(page: Page): Promise<Version[]> {
  const participant = await page.locator("mires-viewer").evaluate((el) => (el as unknown as { participant: string }).participant);
  const response = await page.request.get(`/api/v1/viewer/objects?participant=${participant}`);
  expect(response.ok()).toBe(true);
  return response.json();
}

/** The next object the viewer saves (201 from POST /objects). */
async function nextSaved(page: Page): Promise<Version> {
  const response = await page.waitForResponse((r) => r.url().endsWith("/api/v1/viewer/objects") && r.request().method() === "POST");
  expect(response.status()).toBe(201);
  return response.json();
}

/** Click Save; returns the saved version once the toast confirms it. */
async function save(v: ViewerPage, kind: "annotation" | "segmentation"): Promise<Version> {
  const saved = nextSaved(v.page);
  await saveButton(v, kind).click();
  const version = await saved;
  await expect(toast(v)).toContainText(`saved (v${version.version})`);
  return version;
}

/** The stored object as WADO /metadata serves it (DICOM JSON). */
async function stored(page: Page, study: string, series: string): Promise<Json> {
  const response = await page.request.get(`/api/v1/dicom/studies/${study}/series/${series}/metadata`);
  expect(response.ok()).toBe(true);
  return (await response.json())[0];
}

const items = (item: Json, tag = "0040A730") => (item[tag]?.Value ?? []) as Json[];
const codeValue = (item: Json, tag: string) => String(items(item, tag)[0]?.["00080100"]?.Value?.[0] ?? "");
/** Every content item of the SR, depth first. */
function contentItems(item: Json): Json[] {
  return items(item).flatMap((child) => [child, ...contentItems(child)]);
}
const NUM_UNIT = (num: Json) => codeValue(items(num, "0040A300")[0], "004008EA");

test("saving a Length stores an SR TID 1500; editing on top supersedes it", async ({ viewerPage }) => {
  const { ct } = seed();
  await openReady(viewerPage, ct);
  await expect(saveButton(viewerPage, "annotation")).toBeDisabled();

  await drawLength(viewerPage, -40);
  await expect(saveButton(viewerPage, "annotation")).toBeEnabled();
  await expect(saveButton(viewerPage, "annotation")).toContainText("Save as new (v1)");
  const v1 = await save(viewerPage, "annotation");

  expect(v1.version).toBe(1);
  const sr = await stored(viewerPage.page, ct.studyUid, v1.series_instance_uid);
  expect(sr["00080016"].Value![0]).toBe("1.2.840.10008.5.1.4.1.1.88.34"); // Comprehensive 3D SR
  expect(items(sr, "0040A504")[0]["0040DB00"].Value![0]).toBe("1500");
  const lengths = contentItems(sr).filter((i) => i["0040A040"]?.Value?.[0] === "NUM" && codeValue(i, "0040A043") === "410668003");
  expect(lengths.map(NUM_UNIT)).toEqual(["mm"]); // CT: tomographic mm, no qualifier
  expect(contentItems(sr).some((i) => codeValue(i, "0040A043") === "SpacingCalib")).toBe(false);

  await expect(saveButton(viewerPage, "annotation")).toBeDisabled();
  await expect(saveButton(viewerPage, "annotation")).toContainText("Supersede v1 → v2");
  await drawLength(viewerPage, 40);
  const v2 = await save(viewerPage, "annotation");

  expect(v2.version).toBe(2);
  expect(v2.chain_id).toBe(v1.chain_id);
  const v2Lengths = contentItems(await stored(viewerPage.page, ct.studyUid, v2.series_instance_uid)).filter(
    (i) => codeValue(i, "0040A043") === "410668003",
  );
  expect(v2Lengths).toHaveLength(2);
});

test("an uncalibrated Length is stored in {pixels}; a User calibration as mm, its qualifier and reference line", async ({ viewerPage }) => {
  const { noSpacing } = seed();
  await openReady(viewerPage, noSpacing);
  await drawLength(viewerPage, -60);
  const px = await save(viewerPage, "annotation");
  const pxSr = await stored(viewerPage.page, noSpacing.studyUid, px.series_instance_uid);
  const pxLength = contentItems(pxSr).find((i) => codeValue(i, "0040A043") === "410668003")!;
  expect(NUM_UNIT(pxLength)).toBe("{pixels}");
  expect(contentItems(pxSr).filter((i) => codeValue(i, "0040A043") === "SpacingCalib").map((i) => codeValue(i, "0040A168"))).toEqual([
    "Uncalibrated",
  ]);

  // Calibrate: a line 100 px long is 50 mm.
  await viewerPage.press("c");
  await drawLine(viewerPage, 100, 60);
  await expect.poll(async () => (await viewerPage.stackState()).pendingCalibration?.unit).toBe("px");
  const legend = viewerPage.page.locator("mires-viewer .calibration");
  await legend.locator("input").fill("50");
  await legend.locator("input").press("Enter");
  await expect(viewerPage.page.locator("mires-viewer .unit")).toHaveText("mm User");
  await expect(saveButton(viewerPage, "annotation")).toBeEnabled(); // the calibration changed the value
  const user = await save(viewerPage, "annotation");

  const sr = await stored(viewerPage.page, noSpacing.studyUid, user.series_instance_uid);
  const all = contentItems(sr);
  const length = all.find((i) => codeValue(i, "0040A043") === "410668003")!;
  expect(NUM_UNIT(length)).toBe("mm");
  expect(Math.abs(Number(items(length, "0040A300")[0]["0040A30A"].Value![0]) - 50)).toBeLessThan(2.5);
  expect(all.filter((i) => codeValue(i, "0040A043") === "SpacingCalib").map((i) => codeValue(i, "0040A168"))).toEqual(["User"]);
  const known = all.find((i) => codeValue(i, "0040A043") === "CalKnownLength")!;
  expect(Number(items(known, "0040A300")[0]["0040A30A"].Value![0])).toBe(50);
  const line = items(known).find((i) => i["0040A040"]?.Value?.[0] === "SCOORD")!;
  const [c0, r0, c1, r1] = (line["00700022"].Value as number[]).map(Number);
  expect(r0).toBeCloseTo(r1, 0);
  expect(Math.abs(c1 - c0)).toBeGreaterThan(10);
});

test.describe("a stale head (409)", () => {
  /** Save a calibrated Length on the no-spacing image (v1), reload, draw again, and get a simulated 409 naming v1. */
  async function stale(viewerPage: ViewerPage, canChange: boolean) {
    const { noSpacing } = seed();
    await openReady(viewerPage, noSpacing);
    await viewerPage.press("c");
    await drawLine(viewerPage, 100, 60);
    await expect.poll(async () => (await viewerPage.stackState()).pendingCalibration?.unit).toBe("px");
    await viewerPage.page.locator("mires-viewer .calibration input").fill("50");
    await viewerPage.page.locator("mires-viewer .calibration input").press("Enter");
    await drawLength(viewerPage, -60);
    const theirs = await save(viewerPage, "annotation");

    await openReady(viewerPage, noSpacing); // a fresh viewer: no annotations, no calibration
    await expect(viewerPage.page.locator("mires-viewer .unit")).toHaveText("px");
    await drawLength(viewerPage, 0);
    await drawLength(viewerPage, 30);
    await viewerPage.page.route(
      "**/api/v1/viewer/objects",
      (route) =>
        route.request().method() === "POST"
          ? route.fulfill({
              status: 409,
              contentType: "application/json",
              body: JSON.stringify({ detail: "a newer version was saved first", head: theirs, can_change: canChange }),
            })
          : route.continue(),
      { times: 1 },
    );
    await saveButton(viewerPage, "annotation").click();
    await expect(dialog(viewerPage)).toBeVisible();
    return theirs;
  }

  test("the dialog names who saved which version; Discard mine, load theirs shows it with its User calibration", async ({ viewerPage }) => {
    const theirs = await stale(viewerPage, false);
    await expect(dialog(viewerPage)).toContainText(`${theirs.author} saved v${theirs.version}`);
    await expect(dialog(viewerPage).locator('[data-choice="on-top"]')).toHaveCount(0);

    await dialog(viewerPage).locator('[data-choice="load-theirs"]').click();

    await expect(dialog(viewerPage)).toHaveCount(0);
    await expect.poll(async () => (await viewerPage.stackState()).annotationCount).toBe(1);
    await expect(viewerPage.page.locator("mires-viewer .unit")).toHaveText("mm User"); // reapplied on reopen
    await expect(saveButton(viewerPage, "annotation")).toBeDisabled();
  });

  test("Save mine as a separate object starts a new chain", async ({ viewerPage }) => {
    const theirs = await stale(viewerPage, true);
    const saved = nextSaved(viewerPage.page);
    await dialog(viewerPage).locator('[data-choice="separate"]').click();
    const mine = await saved;
    await expect(toast(viewerPage)).toContainText("Annotations saved (v1)");
    expect(mine.chain_id).not.toBe(theirs.chain_id);
    expect(mine.version).toBe(1);
  });

  test("Save mine on top supersedes their head", async ({ viewerPage }) => {
    const theirs = await stale(viewerPage, true);
    const saved = nextSaved(viewerPage.page);
    await dialog(viewerPage).locator('[data-choice="on-top"]').click();
    const mine = await saved;
    expect(mine.chain_id).toBe(theirs.chain_id);
    expect(mine.version).toBe(theirs.version + 1);
    const head = (await chains(viewerPage.page)).find((c) => c.chain_id === theirs.chain_id)!;
    expect(head.version).toBe(theirs.version + 1);
  });
});

test("painting a segment saves a SEG (BINARY) with its label", async ({ viewerPage }) => {
  const { ct } = seed();
  await openReady(viewerPage, ct);
  await expect(saveButton(viewerPage, "segmentation")).toBeDisabled();
  await viewerPage.press("g");
  await expect.poll(async () => (await viewerPage.stackState()).activeTool).toBe("Brush");
  await viewerPage.drag("left", 120, 0);
  await expect(saveButton(viewerPage, "segmentation")).toBeEnabled();

  const seg = await save(viewerPage, "segmentation");

  const dataset = await stored(viewerPage.page, ct.studyUid, seg.series_instance_uid);
  expect(dataset["00080016"].Value![0]).toBe("1.2.840.10008.5.1.4.1.1.66.4");
  expect(dataset["00620001"].Value![0]).toBe("BINARY");
  expect(items(dataset, "00620002").map((s) => s["00620005"].Value![0])).toEqual(["Segment 1"]);
});

test("WSI: Length, rectangle and freehand are stored as SCOORD3D in slide mm, simplified, geometric measurements only", async ({ viewerPage }) => {
  const { wsi } = seed();
  await openReady(viewerPage, wsi);
  await drawLength(viewerPage, -40);
  await viewerPage.press("r");
  const box = (await viewerPage.viewport.boundingBox())!;
  await viewerPage.page.mouse.move(box.x + box.width / 2 - 40, box.y + box.height / 2 + 20);
  await viewerPage.page.mouse.down();
  await viewerPage.page.mouse.move(box.x + box.width / 2 + 40, box.y + box.height / 2 + 80, { steps: 10 });
  await viewerPage.page.mouse.up();
  // Freehand: a closed loop drawn in 80 small steps along a square, simplified to about its corners.
  await viewerPage.press("f");
  const [x, y] = [box.x + box.width / 2 + 120, box.y + box.height / 2 - 60];
  await viewerPage.page.mouse.move(x, y);
  await viewerPage.page.mouse.down();
  for (const [dx, dy] of [[60, 0], [60, 60], [0, 60], [0, 0]]) await viewerPage.page.mouse.move(x + dx, y + dy, { steps: 20 });
  await viewerPage.page.mouse.up();
  await expect.poll(async () => (await viewerPage.stackState()).annotationCount).toBe(3);

  const saved = await save(viewerPage, "annotation");

  const all = contentItems(await stored(viewerPage.page, wsi.studyUid, saved.series_instance_uid));
  const scoords = all.filter((i) => i["0040A040"]?.Value?.[0] === "SCOORD3D");
  expect(scoords.length).toBeGreaterThanOrEqual(3);
  const pointCounts = scoords.map((s) => (s["00700022"].Value as number[]).length / 3);
  expect(Math.max(...pointCounts)).toBeLessThanOrEqual(8); // the 80-step loop is down to its corners
  for (const s of scoords) {
    expect((s["00700022"].Value as number[]).length % 3).toBe(0);
    expect(s["30060024"]?.Value?.[0]).toBeTruthy(); // ReferencedFrameOfReferenceUID
  }
  const concepts = all.filter((i) => i["0040A040"]?.Value?.[0] === "NUM").map((i) => codeValue(i, "0040A043"));
  expect(concepts).toContain("410668003");
  expect(concepts).not.toContain("373098007"); // no Mean on a slide
  for (const num of all.filter((i) => i["0040A040"]?.Value?.[0] === "NUM")) expect(["mm", "mm2"]).toContain(NUM_UNIT(num));
});
