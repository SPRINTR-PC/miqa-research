// Shared Playwright fixtures for viewer browser tests: a logged-in page (seeded session
// cookie) and helpers to open the dev viewer page and read the element's state.
import { test as base, expect, type Locator, type Page } from "@playwright/test";

export interface Seed {
  sessionCookie: { name: string; value: string };
  ct: { studyUid: string; seriesUid: string; imageCount: number };
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
}

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

export const test = base.extend<{ viewerPage: ViewerPage }>({
  viewerPage: async ({ page, context, baseURL }, use) => {
    const { sessionCookie } = seed();
    await context.addCookies([{ ...sessionCookie, url: baseURL! }]);
    await use(new ViewerPage(page));
  },
});

export { expect };
