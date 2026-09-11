import { describe, expect, it } from "vitest";

import { withAlpha } from "./chart-color-utils.js";

describe("withAlpha", () => {
  it("converts a 6-digit hex color to rgba with the given alpha", () => {
    expect(withAlpha("#2a78d6", 0.4)).toBe("rgba(42, 120, 214, 0.4)");
  });

  it("expands a 3-digit hex color before converting", () => {
    expect(withAlpha("#fff", 0.5)).toBe("rgba(255, 255, 255, 0.5)");
  });

  it("re-applies alpha to an rgb(...) string", () => {
    expect(withAlpha("rgb(42, 120, 214)", 0.4)).toBe("rgba(42, 120, 214, 0.4)");
  });

  it("re-applies alpha to an rgba(...) string, discarding its own alpha", () => {
    expect(withAlpha("rgba(42, 120, 214, 0.9)", 0.4)).toBe("rgba(42, 120, 214, 0.4)");
  });

  it("returns an unrecognized color format unchanged", () => {
    expect(withAlpha("hsl(210deg 70% 50%)", 0.4)).toBe("hsl(210deg 70% 50%)");
  });
});
