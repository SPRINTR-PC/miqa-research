// Inspector (right side panel) slots. Each panel registers from its own inspector/<panel>.ts,
// imported by inspector/index.ts; the element renders them sorted by `order`.
// Orders in use / reserved (leave gaps): 10 save buttons (#289), 20 layout (#282), 25 segments (#286),
// 30 layers (#284), 35 bulk annotations (#292), 40 calibration legend (#281), 50 window presets (#280), 90 mouse help (#280).
import type { ViewerContext } from "../context.ts";

export interface InspectorPanel {
  id: string;
  order: number;
  /**
   * A Lit template (or `nothing` to hide the panel now). Rendered inside the element's shadow
   * root, so the element's panel classes apply (`section.panel`, `h5`, `.grid2`, `kbd`, `.hint`);
   * a panel needing its own styles renders its own custom element.
   */
  render(ctx: ViewerContext): unknown;
}

export class InspectorRegistry {
  private readonly all: InspectorPanel[] = [];

  register(panel: InspectorPanel): void {
    if (this.all.some((p) => p.id === panel.id)) throw new Error(`Inspector panel ${panel.id} is already registered`);
    this.all.push(panel);
  }

  /** Test helper: remove a panel registered by a test. */
  unregister(id: string): void {
    const i = this.all.findIndex((p) => p.id === id);
    if (i >= 0) this.all.splice(i, 1);
  }

  panels(): InspectorPanel[] {
    return [...this.all].sort((a, b) => a.order - b.order);
  }
}

export const inspector = new InspectorRegistry();
