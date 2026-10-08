// Volume views (#282): 1×1, or three views with the big one left and the other two stacked right,
// a draggable split between them. Always three cells (stable DOM for the adapter's slots); cells
// beyond the shown orientations are hidden. Frame colour follows the orientation (= crosshair colour).
import { css, html, nothing } from "lit";

import type { VolumeState } from "../adapter/adapter.ts";
import { ORIENTATION_COLOR, type Orientation } from "../layout.ts";
import { voiToWindow } from "../tools/index.ts";

export interface VolumeGridOptions {
  orientations: Orientation[];
  split: number;
  state: VolumeState | undefined;
  /** Double-click on a small view (slot 1 or 2). */
  swap(slot: number): void;
  /** Pointer down on the divider. */
  startSplit(e: PointerEvent): void;
}

export const volumeGridStyles = css`
  .vgrid { position: absolute; inset: 0; display: grid; grid-template-columns: var(--split) 6px minmax(0, 1fr); grid-template-rows: 1fr 1fr; }
  .vgrid.one { grid-template-columns: minmax(0, 1fr); grid-template-rows: 1fr; }
  .vcell { position: relative; min-width: 0; min-height: 0; border: 1px solid var(--c); box-sizing: border-box; }
  .vcell[hidden], .divider[hidden] { display: none; }
  .vcell[data-slot="0"] { grid-column: 1; grid-row: 1 / span 2; }
  .vgrid.one .vcell[data-slot="0"] { grid-row: 1; }
  .vcell[data-slot="1"] { grid-column: 3; grid-row: 1; }
  .vcell[data-slot="2"] { grid-column: 3; grid-row: 2; }
  .vslot { position: absolute; inset: 0; }
  .vlabel { position: absolute; left: 6px; bottom: 4px; pointer-events: none; font: 11px ui-monospace, monospace; text-shadow: 0 0 2px #000; }
  .vlabel b { color: var(--c); text-transform: capitalize; font-weight: 600; }
  .divider { grid-column: 2; grid-row: 1 / span 2; cursor: col-resize; background: #262c35; touch-action: none; }
  .divider:hover { background: #1f6feb; }
`;

function label(state: VolumeState | undefined, slot: number, orientation: Orientation) {
  const view = state?.views[slot];
  const slice = view ? ` ${view.sliceIndex + 1} / ${view.sliceCount}` : "";
  let window = "";
  if (slot === 0 && state?.voi) {
    const { width, center } = voiToWindow(state.voi);
    window = ` · W ${Math.round(width)} L ${Math.round(center)}`;
  }
  return html`<b>${orientation}</b>${slice}${window}`;
}

export function volumeGrid({ orientations, split, state, swap, startSplit }: VolumeGridOptions) {
  const three = orientations.length === 3;
  return html`<div class="vgrid ${three ? "three" : "one"}" style="--split: ${split}%">
    ${[0, 1, 2].map((slot) => {
      const o = orientations[slot];
      return html`<div
        class="vcell"
        data-slot=${slot}
        data-orientation=${o ?? ""}
        ?hidden=${!o}
        style="--c: ${o ? ORIENTATION_COLOR[o] : "transparent"}"
        title=${three && slot > 0 ? "Double-click: show in the big view" : ""}
        @dblclick=${three && slot > 0 ? () => swap(slot) : undefined}
      >
        <div class="vslot" tabindex="-1"></div>
        ${o ? html`<div class="vlabel">${label(state, slot, o)}</div>` : nothing}
      </div>`;
    })}
    <div class="divider" ?hidden=${!three} title="Drag to resize" @pointerdown=${startSplit}></div>
  </div>`;
}
