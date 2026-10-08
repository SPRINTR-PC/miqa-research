// #291 draft recovery after a reload, in a real browser: unsaved edits autosaved to IndexedDB, the
// banner on the next open, Restore brings them back, and saving clears the draft.
import { expect, seed, test, type ViewerPage } from "./fixtures.ts";

interface StoredDraft {
  kind: string;
  seriesUid: string;
  user: string;
}

/** The drafts in the viewer's IndexedDB. */
function drafts(v: ViewerPage): Promise<StoredDraft[]> {
  return v.page.evaluate(
    () =>
      new Promise<StoredDraft[]>((resolve, reject) => {
        const open = indexedDB.open("mires-viewer-drafts");
        open.onerror = () => reject(open.error);
        open.onsuccess = () => {
          const db = open.result;
          if (!db.objectStoreNames.contains("drafts")) return resolve([]);
          const all = db.transaction("drafts").objectStore("drafts").getAll();
          all.onsuccess = () => resolve(all.result as StoredDraft[]);
          all.onerror = () => reject(all.error);
        };
      }),
  );
}

const banner = (v: ViewerPage) => v.page.locator("mires-viewer .draft-banner");
const saveButton = (v: ViewerPage, kind: string) => v.page.locator(`mires-viewer [data-save="${kind}"]`);

async function openReady(v: ViewerPage) {
  await v.open(seed().ct);
  await expect(v.viewer).toHaveAttribute("state", "ready");
}

test("draw, reload without saving, Restore brings the edits back, and save clears the draft", async ({ viewerPage }) => {
  await openReady(viewerPage);
  await expect(banner(viewerPage)).toHaveCount(0);
  await viewerPage.press("l");
  await viewerPage.drag("left", 100, 0);
  await expect.poll(async () => (await viewerPage.stackState()).annotationCount).toBe(1);
  await expect.poll(async () => (await drafts(viewerPage)).map((d) => d.kind)).toEqual(["annotation"]);

  await openReady(viewerPage); // reload, nothing saved

  await expect(banner(viewerPage)).toContainText("Unsaved Annotations");
  await expect(banner(viewerPage)).toContainText("not saved before");
  expect((await viewerPage.stackState()).annotationCount).toBe(0);
  await banner(viewerPage).locator('[data-draft-restore="annotation"]').click();

  await expect.poll(async () => (await viewerPage.stackState()).annotationCount).toBe(1);
  await expect(banner(viewerPage)).toHaveCount(0);
  await expect(saveButton(viewerPage, "annotation")).toBeEnabled();
  await saveButton(viewerPage, "annotation").click();
  await expect(viewerPage.page.locator("mires-viewer .toast")).toContainText("Annotations saved (v1)");

  await expect.poll(() => drafts(viewerPage)).toEqual([]);
  await openReady(viewerPage);
  await expect(viewerPage.viewer).toHaveAttribute("state", "ready");
  await viewerPage.page.waitForTimeout(300); // the draft check is async
  await expect(banner(viewerPage)).toHaveCount(0);
});

test("a painted Segmentation is restored after a reload; Discard drops it", async ({ viewerPage }) => {
  const painted = () =>
    viewerPage.viewer.evaluate((el) => (el as unknown as { segmentationState?: { voxels: Record<number, number> } }).segmentationState?.voxels[1] ?? 0);
  await openReady(viewerPage);
  await viewerPage.press("g");
  await expect.poll(async () => (await viewerPage.stackState()).activeTool).toBe("Brush");
  await viewerPage.drag("left", 120, 0);
  await expect.poll(painted).toBeGreaterThan(0);
  const voxels = await painted();
  await expect.poll(async () => (await drafts(viewerPage)).map((d) => d.kind)).toEqual(["segmentation"]);

  await openReady(viewerPage);
  await expect(banner(viewerPage)).toContainText("Unsaved Segmentation");
  await banner(viewerPage).locator('[data-draft-restore="segmentation"]').click();

  await expect.poll(painted).toBe(voxels);
  await expect(saveButton(viewerPage, "segmentation")).toBeEnabled();

  await openReady(viewerPage); // the restored edits were autosaved again
  await banner(viewerPage).locator('[data-draft-discard="segmentation"]').click();
  await expect(banner(viewerPage)).toHaveCount(0);
  await expect.poll(() => drafts(viewerPage)).toEqual([]);
  expect(await painted()).toBe(0);
});
