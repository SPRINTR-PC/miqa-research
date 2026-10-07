// #280 chrome B on a CT stack: workstation mouse, tool keys, presets, invert/reset, role gating.
import { expect, seed, test } from "./fixtures.ts";

const SERIES_WINDOW = "W 400 L 40";

test.describe("workstation mouse", () => {
  test.beforeEach(async ({ viewerPage }) => {
    await viewerPage.open(seed().ct);
    await expect(viewerPage.viewer).toHaveAttribute("state", "ready");
    await expect(viewerPage.page.locator("mires-viewer .overlay")).toContainText(SERIES_WINDOW);
  });

  test("right-drag changes the window, whatever tool is selected", async ({ viewerPage }) => {
    await viewerPage.press("l");

    await viewerPage.drag("right", 80, 60);

    await expect(viewerPage.page.locator("mires-viewer .overlay")).not.toContainText(SERIES_WINDOW);
    const state = await viewerPage.stackState();
    expect(state.activeTool).toBe("Length");
    expect(state.annotationCount).toBe(0);
  });

  test("middle-drag pans", async ({ viewerPage }) => {
    const before = await viewerPage.stackState();

    await viewerPage.drag("middle", 100, 40);

    await expect.poll(async () => (await viewerPage.stackState()).pan).not.toEqual(before.pan);
    const after = await viewerPage.stackState();
    expect(after.voi).toEqual(before.voi);
    expect(after.zoom).toBeCloseTo(before.zoom);
  });

  test("Ctrl+wheel zooms instead of scrolling", async ({ viewerPage }) => {
    const before = await viewerPage.stackState();
    await viewerPage.viewport.hover();

    await viewerPage.page.keyboard.down("Control");
    for (let i = 0; i < 3; i++) await viewerPage.page.mouse.wheel(0, -120);
    await viewerPage.page.keyboard.up("Control");

    await expect.poll(async () => (await viewerPage.stackState()).zoom).not.toBeCloseTo(before.zoom);
    expect((await viewerPage.stackState()).imageIndex).toBe(before.imageIndex);
  });

  test("left button uses the selected tool: Length draws a measurement", async ({ viewerPage }) => {
    await viewerPage.press("l");

    await viewerPage.drag("left", 120, 0);

    await expect.poll(async () => (await viewerPage.stackState()).annotationCount).toBe(1);
    await expect(viewerPage.page.locator("mires-viewer .overlay")).toContainText(SERIES_WINDOW);
  });
});

test.describe("keys", () => {
  test.beforeEach(async ({ viewerPage }) => {
    await viewerPage.open(seed().ct);
    await expect(viewerPage.viewer).toHaveAttribute("state", "ready");
  });

  test("every rail tool's key selects it in the view", async ({ viewerPage }) => {
    const rail = await viewerPage.railTools();
    expect(rail).toContain("ArrowAnnotate");

    for (const id of rail) {
      const button = viewerPage.page.locator(`mires-viewer .rail [data-tool="${id}"]`);
      const key = (await button.locator("kbd").textContent())!.toLowerCase();
      await viewerPage.press(key);
      await expect(button).toHaveAttribute("aria-pressed", "true");
      expect((await viewerPage.stackState()).activeTool).toBe(id);
    }
  });

  test("digits apply window presets: 2 = Lung, 0 = DICOM default", async ({ viewerPage }) => {
    const overlay = viewerPage.page.locator("mires-viewer .overlay");

    await viewerPage.press("2");
    await expect(overlay).toContainText("W 1500 L -600");

    await viewerPage.press("0");
    await expect(overlay).toContainText(SERIES_WINDOW);
  });

  test("I inverts, Esc resets zoom, pan, window and invert", async ({ viewerPage }) => {
    await viewerPage.press("i");
    await expect.poll(async () => (await viewerPage.stackState()).invert).toBe(true);
    await viewerPage.drag("middle", 100, 40);
    await viewerPage.press("3");
    const changed = await viewerPage.stackState();
    expect(changed.pan).not.toEqual([0, 0]);

    await viewerPage.press("Escape");

    await expect.poll(async () => (await viewerPage.stackState()).invert).toBe(false);
    const reset = await viewerPage.stackState();
    expect(reset.pan[0]).toBeCloseTo(0);
    expect(reset.pan[1]).toBeCloseTo(0);
    await expect(viewerPage.page.locator("mires-viewer .overlay")).toContainText(SERIES_WINDOW);
  });

  test("the measurement unit is CS3D's raw suffix with a tooltip", async ({ viewerPage }) => {
    const unit = viewerPage.page.locator("mires-viewer .unit");

    await expect(unit).toHaveText("mm");
    await expect(unit).toHaveAttribute("title", /pixel spacing/i);
  });
});

test.describe("view-only user", () => {
  test.use({ viewOnly: true });

  test("has no annotate tools, by rail or by key", async ({ viewerPage }) => {
    await viewerPage.open(seed().ct);
    await expect(viewerPage.viewer).toHaveAttribute("state", "ready");

    const rail = await viewerPage.railTools();
    expect(rail).toContain("Length");
    expect(rail).not.toContain("ArrowAnnotate");

    await viewerPage.press("t");
    expect((await viewerPage.stackState()).activeTool).toBe("WindowLevel");
  });
});
