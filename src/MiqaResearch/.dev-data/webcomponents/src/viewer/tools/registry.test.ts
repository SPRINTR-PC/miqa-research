import { describe, expect, it } from "vitest";

import { ToolRegistry } from "./registry.ts";

const length = { id: "Length", label: "Length", key: "l", group: "measure", icon: "L", viewports: ["stack", "volume"] } as const;
const arrow = { id: "ArrowAnnotate", label: "Arrow", key: "t", group: "annotate", icon: "A", viewports: ["stack"], annotateOnly: true } as const;
const pan = { id: "Pan", label: "Pan", key: "p", group: "nav", icon: "P", viewports: ["stack", "wsi"] } as const;

describe("ToolRegistry", () => {
  it("lists the tools of a viewport kind grouped for the rail, in registration order", () => {
    const tools = new ToolRegistry();
    [length, arrow, pan].forEach((t) => tools.register(t));

    const rail = tools.rail({ viewport: "stack", canAnnotate: true });

    expect(rail.map((g) => [g.label, g.tools.map((t) => t.id)])).toEqual([
      ["Nav", ["Pan"]],
      ["Measure", ["Length"]],
      ["Annot.", ["ArrowAnnotate"]],
    ]);
  });

  it("leaves out tools of other viewport kinds", () => {
    const tools = new ToolRegistry();
    [length, arrow, pan].forEach((t) => tools.register(t));

    expect(tools.available({ viewport: "wsi", canAnnotate: true }).map((t) => t.id)).toEqual(["Pan"]);
  });

  it("gives a view-only user no annotate tools", () => {
    const tools = new ToolRegistry();
    [length, arrow, pan].forEach((t) => tools.register(t));

    const ids = tools.available({ viewport: "stack", canAnnotate: false }).map((t) => t.id);

    expect(ids).toEqual(["Length", "Pan"]);
    expect(tools.forKey("t", { viewport: "stack", canAnnotate: false })).toBeUndefined();
  });

  it("finds a tool by its shortcut key, case-insensitively", () => {
    const tools = new ToolRegistry();
    tools.register(length);

    expect(tools.forKey("L", { viewport: "stack", canAnnotate: false })?.id).toBe("Length");
  });

  it("refuses a second tool with the same id or shortcut key", () => {
    const tools = new ToolRegistry();
    tools.register(length);

    expect(() => tools.register({ ...pan, id: "Length" })).toThrow(/Length/);
    expect(() => tools.register({ ...pan, key: "l" })).toThrow(/"l"/);
  });

  it("refuses shortcut keys reserved for viewer commands", () => {
    const tools = new ToolRegistry(["i", "v"]);

    expect(() => tools.register({ ...pan, key: "i" })).toThrow(/"i"/);
  });
});
