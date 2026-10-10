// #279 entry contract (#184): the page hands the viewer one series list. Opened series: the first is the
// base, the rest are fused onto it at open. Related Series, from any study of the participant, are listed
// without loading them, and load from their own study when dropped onto the view.
import { expect, seed, test } from "./fixtures.ts";

interface VolumeState {
  layers: { seriesUid: string }[];
}

test("opens the base with the other opened series fused, and lists a Related Series of another study", async ({
  viewerPage,
}) => {
  const s = seed();
  const metadata: string[] = [];
  viewerPage.page.on("request", (r) => {
    if (r.url().endsWith("/metadata")) metadata.push(new URL(r.url()).pathname);
  });

  await viewerPage.openList([s.ct, s.pet], [s.followUp]);

  await expect(viewerPage.viewer).toHaveAttribute("state", "ready");
  await expect
    .poll(() => viewerPage.viewer.evaluate((el) => (el as unknown as { volumeState?: VolumeState }).volumeState?.layers.map((l) => l.seriesUid)))
    .toEqual([s.ct.seriesUid, s.pet.seriesUid]);
  const rows = viewerPage.page.locator("mires-viewer .ser");
  await expect(rows).toHaveCount(3);
  await expect(rows.nth(2)).toContainText("Harness MR follow-up");
  expect(metadata.some((p) => p.includes(s.followUp.seriesUid))).toBe(false);

  // Dropped onto the bottom half (replace), it loads from its own study.
  await viewerPage.dragSeries(s.followUp.seriesUid, "replace");
  await expect.poll(() => metadata).toContain(`/api/v1/dicom/studies/${s.followUp.studyUid}/series/${s.followUp.seriesUid}/metadata`);
});
