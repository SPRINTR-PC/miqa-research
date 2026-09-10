import { afterEach, describe, expect, it, vi } from "vitest";

import {
  registerChartCallback,
  resolveChartCallback,
  unregisterChartCallback,
} from "./chart-callback-registry.js";

describe("chart callback registry", () => {
  afterEach(() => {
    unregisterChartCallback("test-callback");
  });

  it("resolves a registered callback by name", () => {
    const fn = vi.fn();
    registerChartCallback("test-callback", fn);

    expect(resolveChartCallback("test-callback")).toBe(fn);
  });

  it("returns undefined for an unregistered name", () => {
    expect(resolveChartCallback("nonexistent")).toBeUndefined();
  });

  it("removes a callback on unregister", () => {
    registerChartCallback("test-callback", vi.fn());
    unregisterChartCallback("test-callback");

    expect(resolveChartCallback("test-callback")).toBeUndefined();
  });

  it("is also reachable via window.mires for plain <script> consumers", () => {
    const fn = vi.fn();
    window.mires?.registerChartCallback?.("test-callback", fn);

    expect(resolveChartCallback("test-callback")).toBe(fn);

    window.mires?.unregisterChartCallback?.("test-callback");
    expect(resolveChartCallback("test-callback")).toBeUndefined();
  });
});
