import { describe, expect, it } from "vitest";

import { snakeToCamelDeep } from "./snake-to-camel.js";

describe("snakeToCamelDeep", () => {
  it("converts a flat object's keys", () => {
    expect(snakeToCamelDeep({ webgl_threshold: 100 })).toEqual({ webglThreshold: 100 });
  });

  it("converts nested objects recursively", () => {
    expect(snakeToCamelDeep({ event_callbacks: { on_click: "foo" } })).toEqual({
      eventCallbacks: { onClick: "foo" },
    });
  });

  it("converts keys inside array elements without touching array structure", () => {
    expect(snakeToCamelDeep({ groupings: [{ group_name: "a" }, { group_name: "b" }] })).toEqual({
      groupings: [{ groupName: "a" }, { groupName: "b" }],
    });
  });

  it("leaves already-camelCase keys untouched", () => {
    expect(snakeToCamelDeep({ alreadyCamel: 1 })).toEqual({ alreadyCamel: 1 });
  });

  it("leaves primitives and null untouched", () => {
    expect(snakeToCamelDeep(5)).toBe(5);
    expect(snakeToCamelDeep("a_b")).toBe("a_b");
    expect(snakeToCamelDeep(null)).toBeNull();
  });
});
