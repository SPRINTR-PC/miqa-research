// Shared Playwright fixtures for viewer browser tests: a logged-in page (seeded session
// cookie) and helpers to open the dev viewer page and read the element's state.
import { test as base, expect, type Locator, type Page } from "@playwright/test";

export interface Seed {
  /** PI: annotate role. */
  sessionCookie: { name: string; value: string };
  /** Investigator: view-only role (#280). */
  viewOnlySessionCookie: { name: string; value: string };
  ct: { studyUid: string; seriesUid: string; imageCount: number };
  /** Synthetic TILED_FULL whole-slide image, JPEG tiles (#285). */
  wsi: { studyUid: string; seriesUid: string; levels: number; baseTiles: number };
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

  async open(series: { studyUid: string; seriesUid: string }): Promise<void> {
    await this.page.goto(`/viewer/dev/?study=${series.studyUid}&series=${series.seriesUid}`);
    await expect(this.viewer).toHaveAttribute("state", /ready|error/);
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
