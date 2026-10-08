// #284 fusion: a series dragged from the series list onto the big view's top half fuses into every
// view (same Frame of Reference, volumes only); a different Frame of Reference is refused with the
// reason; right-drag windows the selected overlay only; a PET without an SUV input is flagged.
import { expect, seed, test, type ViewerPage } from "./fixtures.ts";

interface Layer {
  seriesUid: string;
  colormap: string;
  voi?: { lower: number; upper: number };
  suv?: { applied: boolean; reason?: string };
}

interface VolumeState {
  views: { orientation: string }[];
  layers: Layer[];
  selectedLayer: string;
}

const volumeState = (viewerPage: ViewerPage) =>
  viewerPage.viewer.evaluate((el) => (el as unknown as { volumeState?: VolumeState }).volumeState);

/** Pixels of the big view whose colour channels differ clearly (grey CT pixels don't). */
const colouredPixels = (viewerPage: ViewerPage) =>
  viewerPage.page.locator('mires-viewer .vcell[data-slot="0"] canvas').first().evaluate((c) => {
    const canvas = c as HTMLCanvasElement;
    const data = canvas.getContext("2d")!.getImageData(0, 0, canvas.width, canvas.height).data;
    let n = 0;
    for (let i = 0; i < data.length; i += 4) {
      if (Math.max(data[i], data[i + 1], data[i + 2]) - Math.min(data[i], data[i + 1], data[i + 2]) > 60) n += 1;
    }
    return n;
  });

async function openCt(viewerPage: ViewerPage) {
  const s = seed();
  await viewerPage.open(s.ct, [s.pet, s.petNoWeight, s.mrOtherFor]);
  await expect(viewerPage.viewer).toHaveAttribute("state", "ready");
  await expect(viewerPage.page.locator("mires-viewer .ser")).toHaveCount(4);
}

/** HTML5 drag with the real mouse: the drop zones appear once the drag has started. */
async function dragSeries(viewerPage: ViewerPage, seriesUid: string, zone: "fuse" | "replace") {
  const { page } = viewerPage;
  const row = (await page.locator(`mires-viewer .ser[data-series-uid="${seriesUid}"]`).boundingBox())!;
  await page.mouse.move(row.x + row.width / 2, row.y + row.height / 2);
  await page.mouse.down();
  await page.mouse.move(row.x + row.width / 2 + 30, row.y + row.height / 2 + 10, { steps: 5 });
  const target = page.locator(`mires-viewer .drop-zone[data-zone="${zone}"]`);
  await expect(target).toBeVisible();
  const box = (await target.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 10 });
  await page.mouse.up();
  await expect(target).toHaveCount(0);
}

test("a PET dropped on the CT's top half fuses into three views, in SUV", async ({ viewerPage }) => {
  await openCt(viewerPage);
  const { pet, ct } = seed();

  await dragSeries(viewerPage, pet.seriesUid, "fuse");

  await expect.poll(async () => (await volumeState(viewerPage))?.layers.map((l) => l.seriesUid)).toEqual([ct.seriesUid, pet.seriesUid]);
  await expect.poll(async () => (await volumeState(viewerPage))!.selectedLayer).toBe(pet.seriesUid);
  const state = (await volumeState(viewerPage))!;
  expect(state.views.map((v) => v.orientation)).toEqual(["axial", "sagittal", "coronal"]);
  expect(state.layers[1]).toMatchObject({ colormap: "hsv", voi: { lower: 0, upper: 5 }, suv: { applied: true } });
  await expect(viewerPage.page.locator("mires-viewer .vcell canvas")).toHaveCount(3);
  await expect(viewerPage.page.locator("mires-viewer .suv-warning")).toHaveCount(0);
  // The hot sphere (SUV 6) shows in colour over the grey CT; SUV 1 background is transparent (curve).
  await expect.poll(() => colouredPixels(viewerPage)).toBeGreaterThan(50);
  await expect(viewerPage.page.locator("mires-viewer .refusal")).toHaveCount(0);

  // Re-layout keeps the fusion.
  await viewerPage.page.locator('mires-viewer [data-layout="coronal"]').click();
  await expect.poll(async () => (await volumeState(viewerPage))?.views.map((v) => v.orientation)).toEqual(["coronal"]);
  expect((await volumeState(viewerPage))!.layers).toHaveLength(2);
  await expect.poll(() => colouredPixels(viewerPage)).toBeGreaterThan(50);
});

test("a series on another Frame of Reference is refused with the reason", async ({ viewerPage }) => {
  await openCt(viewerPage);

  await dragSeries(viewerPage, seed().mrOtherFor.seriesUid, "fuse");

  await expect(viewerPage.page.locator("mires-viewer .refusal")).toContainText("different Frame of Reference");
  expect(await volumeState(viewerPage)).toBeUndefined();
});

test("right-drag windows the selected overlay only", async ({ viewerPage }) => {
  await openCt(viewerPage);
  await dragSeries(viewerPage, seed().pet.seriesUid, "fuse");
  await expect.poll(async () => (await volumeState(viewerPage))?.selectedLayer).toBe(seed().pet.seriesUid);
  const before = (await volumeState(viewerPage))!.layers;

  const box = (await viewerPage.page.locator('mires-viewer .vcell[data-slot="0"]').boundingBox())!;
  const { mouse } = viewerPage.page;
  await mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await mouse.down({ button: "right" });
  await mouse.move(box.x + box.width / 2 + 60, box.y + box.height / 2 + 40, { steps: 10 });
  await mouse.up({ button: "right" });

  await expect.poll(async () => (await volumeState(viewerPage))!.layers[1].voi).not.toEqual(before[1].voi);
  expect((await volumeState(viewerPage))!.layers[0].voi).toEqual(before[0].voi);
});

test("a PET without PatientWeight is flagged as Bq/ml, not SUV", async ({ viewerPage }) => {
  await openCt(viewerPage);
  const { petNoWeight } = seed();

  await dragSeries(viewerPage, petNoWeight.seriesUid, "fuse");

  await expect(viewerPage.page.locator(`mires-viewer .suv-warning[data-series-uid="${petNoWeight.seriesUid}"]`)).toContainText(
    "missing PatientWeight",
  );
  expect((await volumeState(viewerPage))!.layers[1].suv).toEqual({ applied: false, reason: "missing PatientWeight" });
});
