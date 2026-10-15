// Shared Playwright fixtures for viewer browser tests: a logged-in page (seeded session
// cookie) and helpers to open the dev viewer page and read the element's state.
import { test as base, expect, type Locator, type Page } from "@playwright/test";

export interface Seed {
  /** PI: annotate role. */
  sessionCookie: { name: string; value: string };
  /** Investigator: view-only role (#280). */
  viewOnlySessionCookie: { name: string; value: string };
  ct: { studyUid: string; seriesUid: string; imageCount: number };
  /** #281 2D spacing fixtures: CR with only ImagerPixelSpacing, SC with PixelSpacing, SC without spacing. */
  cr: SeriesRef;
  sc: SeriesRef;
  noSpacing: SeriesRef;
  /** Synthetic TILED_FULL whole-slide image, JPEG tiles (#285). */
  wsi: { studyUid: string; seriesUid: string; levels: number; baseTiles: number; participant: string };
  /** Bulk annotations (ANN) on the slide (#292): group names (property types), in group order. */
  wsiAnnotations: { groups: string[] };
  /** #284 fusion series in the CT's study: PETs on the CT's Frame of Reference (with / without SUV inputs), an MR on another. */
  pet: SeriesRef & { imageCount: number };
  petNoWeight: SeriesRef & { imageCount: number };
  mrOtherFor: SeriesRef & { imageCount: number };
  /** #279: an MR in a later study of the CT's participant (Related Series across studies). */
  followUp: SeriesRef & { imageCount: number };
  /** #290 Blinded Annotation project: a 2D image with one hidden (ingested) SR; the PI may reveal it. */
  blinded: SeriesRef & { participant: string };
}

export interface SeriesRef {
  studyUid: string;
  seriesUid: string;
}

export function seed(): Seed {
  const raw = process.env.VIEWER_HARNESS_SEED;
  if (!raw) throw new Error("VIEWER_HARNESS_SEED missing: run through `npm run test:browser` (global-setup)");
  return JSON.parse(raw) as Seed;
}

export interface StackState {
  imageIndex: number;
  imageCount: number;
  voi?: { lower: number; upper: number };
  activeTool: string;
  invert: boolean;
  zoom: number;
  pan: [number, number];
  unit: string;
  annotationCount: number;
  pendingCalibration?: { length: number; unit: string };
}

export type Button = "left" | "right" | "middle";

export class ViewerPage {
  readonly page: Page;
  readonly viewer: Locator;
  readonly viewport: Locator;

  constructor(page: Page) {
    this.page = page;
    this.viewer = page.locator("mires-viewer");
    this.viewport = page.locator("mires-viewer .viewport");
  }

  /** Open the dev page; `related` series are offered in the series list (#284). */
  async open(series: SeriesRef, related: SeriesRef[] = []): Promise<void> {
    await this.openList([series], related);
  }

  /** Open the dev page on several series (#279: first = base, the rest fused onto it), plus `related`. */
  async openList(opened: SeriesRef[], related: SeriesRef[] = []): Promise<void> {
    const query = [...opened.map((s) => `series=${s.seriesUid}`), ...related.map((r) => `related=${r.seriesUid}`)];
    await this.page.goto(`/viewer/dev/?${query.join("&")}`);
    await expect(this.viewer).toHaveAttribute("state", /ready|error/);
  }

  /** Drag a series row onto a drop zone with the real mouse (HTML5 drag: the zones appear once it starts). */
  async dragSeries(seriesUid: string, zone: "fuse" | "replace"): Promise<void> {
    const { page } = this;
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

  /** Drag across the viewport centre with a mouse button. */
  async drag(button: Button, dx: number, dy: number): Promise<void> {
    const box = (await this.viewport.boundingBox())!;
    const { mouse } = this.page;
    const x = box.x + box.width / 2;
    const y = box.y + box.height / 2;
    await mouse.move(x - dx / 2, y - dy / 2);
    await mouse.down({ button });
    await mouse.move(x + dx / 2, y + dy / 2, { steps: 10 });
    await mouse.up({ button });
  }

  /** Press a key with the viewer focused. */
  async press(key: string): Promise<void> {
    await this.viewer.focus();
    await this.page.keyboard.press(key);
  }

  railTools(): Promise<string[]> {
    return this.page.locator("mires-viewer .rail [data-tool]").evaluateAll((els) => els.map((e) => (e as HTMLElement).dataset.tool!));
  }

  stackState(): Promise<StackState> {
    return this.viewer.evaluate((el) => (el as unknown as { stackState: StackState }).stackState);
  }

  /** Grey-level fingerprint of the rendered canvas (sum of the red channel), to tell images apart. */
  canvasSignature(): Promise<number> {
    return this.page.locator("mires-viewer .viewport canvas").first().evaluate((c) => {
      const canvas = c as HTMLCanvasElement;
      const data = canvas.getContext("2d")!.getImageData(0, 0, canvas.width, canvas.height).data;
      let sum = 0;
      for (let i = 0; i < data.length; i += 4) sum += data[i];
      return sum;
    });
  }
}

export const test = base.extend<{ viewerPage: ViewerPage; viewOnly: boolean }>({
  /** Log in as the view-only user: `test.use({ viewOnly: true })`. */
  viewOnly: [false, { option: true }],
  viewerPage: async ({ page, context, baseURL, viewOnly }, use) => {
    const { sessionCookie, viewOnlySessionCookie } = seed();
    await context.addCookies([{ ...(viewOnly ? viewOnlySessionCookie : sessionCookie), url: baseURL! }]);
    await use(new ViewerPage(page));
  },
});

export { expect };
