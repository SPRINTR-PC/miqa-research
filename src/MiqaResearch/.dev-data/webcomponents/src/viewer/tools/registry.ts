// Tool registry: the tools the rail shows and the single-key shortcuts that select them.
// Pure data, no Cornerstone3D: `id` is the CS3D tool (instance) name, which the adapter maps
// to a tool class (adapter/cornerstone/tools.ts). Tickets add tools from their own module
// (tools/<capability>.ts, imported by tools/index.ts) with `tools.register(...)`.

export type ViewportKind = "stack" | "volume" | "wsi";
export type ToolGroup = "nav" | "measure" | "annotate" | "segment";

export interface ToolDef {
  /** CS3D tool name (`Tool.toolName`) or tool-instance name; also the rail button's `data-tool`. */
  id: string;
  label: string;
  /** Single-key shortcut, lower case. */
  key: string;
  group: ToolGroup;
  /** Short glyph for the rail button. */
  icon: string;
  /** Viewport kinds that offer the tool (spec tool sets). */
  viewports: readonly ViewportKind[];
  /** Only for annotate roles (Annotator, PI, Site PI, Admin). */
  annotateOnly?: boolean;
  /** Needs at least this many views shown at once (Crosshairs: 3, #282). Default 1. */
  minViews?: number;
}

export interface ToolScope {
  viewport: ViewportKind;
  canAnnotate: boolean;
  /** Views shown at once (1×1 = 1, three views = 3). Default 1. */
  views?: number;
}

export interface RailGroup {
  group: ToolGroup;
  label: string;
  tools: ToolDef[];
}

const GROUPS: [ToolGroup, string][] = [
  ["nav", "Nav"],
  ["measure", "Measure"],
  ["annotate", "Annot."],
  ["segment", "Segment"],
];

export class ToolRegistry {
  private readonly tools: ToolDef[] = [];
  private readonly reserved: Set<string>;

  /** `reservedKeys`: keys owned by viewer commands/presets, never a tool shortcut. */
  constructor(reservedKeys: Iterable<string> = []) {
    this.reserved = new Set([...reservedKeys].map((k) => k.toLowerCase()));
  }

  register(tool: ToolDef): void {
    const key = tool.key.toLowerCase();
    if (this.tools.some((t) => t.id === tool.id)) throw new Error(`Tool ${tool.id} is already registered`);
    const clash = this.tools.find((t) => t.key === key);
    if (clash) throw new Error(`Shortcut "${key}" of ${tool.id} is taken by ${clash.id}`);
    if (this.reserved.has(key)) throw new Error(`Shortcut "${key}" of ${tool.id} is reserved for a viewer command`);
    this.tools.push({ ...tool, key });
  }

  available(scope: ToolScope): ToolDef[] {
    return this.tools.filter(
      (t) =>
        t.viewports.includes(scope.viewport) &&
        (scope.canAnnotate || !t.annotateOnly) &&
        (t.minViews ?? 1) <= (scope.views ?? 1),
    );
  }

  rail(scope: ToolScope): RailGroup[] {
    const tools = this.available(scope);
    return GROUPS.map(([group, label]) => ({ group, label, tools: tools.filter((t) => t.group === group) })).filter(
      (g) => g.tools.length,
    );
  }

  forKey(key: string, scope: ToolScope): ToolDef | undefined {
    const k = key.toLowerCase();
    return this.available(scope).find((t) => t.key === k);
  }

  byId(id: string): ToolDef | undefined {
    return this.tools.find((t) => t.id === id);
  }
}

/**
 * Keys owned by viewer commands and presets, never a tool shortcut:
 * 0–9 presets, I invert, V orientation cycle (#282), Esc reset.
 */
export const RESERVED_KEYS = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "i", "v", "escape"];

/** The viewer's tool registry. Register from tools/<capability>.ts, imported by tools/index.ts. */
export const tools = new ToolRegistry(RESERVED_KEYS);
