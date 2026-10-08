// Drop zones (#284): while a series is dragged from the series list, the big view shows two halves:
// top = fuse into every view, bottom = replace what's shown. Invalid drops are refused with the reason
// (the element's refusal message), so the zones only say what a drop there does.
import { css, html, nothing } from "lit";

export type DropZone = "fuse" | "replace";

export const dropZoneStyles = css`
  .drop-zones { position: absolute; z-index: 7; top: 0; left: 0; bottom: 0; display: grid; grid-template-rows: 1fr 1fr; gap: 4px; padding: 4px; box-sizing: border-box; }
  .drop-zone { display: flex; align-items: center; justify-content: center; text-align: center; padding: 8px; border: 2px dashed #2f4a6b; border-radius: 6px; background: rgb(15 25 40 / 70%); color: #cfe1ff; font-size: 13px; }
  .drop-zone.over { border-color: #1f6feb; background: rgb(31 111 235 / 35%); }
  .drop-zone small { display: block; color: #9fb3cc; font-size: 11px; margin-top: 2px; }
`;

export interface DropZonesOptions {
  /** Width of the big view in percent of the stage (three views: the split; else 100). */
  width: number;
  /** Zone under the pointer, highlighted. */
  over: DropZone | undefined;
  /** Series being dragged, e.g. "PT PET AC". */
  label: string;
  onOver(zone: DropZone | undefined): void;
  onDrop(zone: DropZone): void;
}

export function dropZones({ width, over, label, onOver, onDrop }: DropZonesOptions) {
  const zone = (id: DropZone, title: string, hint: string) => html`<div
    class="drop-zone ${over === id ? "over" : ""}"
    data-zone=${id}
    @dragenter=${(e: DragEvent) => {
      e.preventDefault();
      onOver(id);
    }}
    @dragover=${(e: DragEvent) => {
      e.preventDefault();
      if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
    }}
    @drop=${(e: DragEvent) => {
      e.preventDefault();
      onDrop(id);
    }}
  >
    <div>${title}${label ? html` ${label}` : nothing}<small>${hint}</small></div>
  </div>`;
  return html`<div class="drop-zones" style="width: ${width}%" @dragleave=${(e: DragEvent) => {
    if (!(e.currentTarget as HTMLElement).contains(e.relatedTarget as Node | null)) onOver(undefined);
  }}>
    ${zone("fuse", "Fuse", "into every view (same Frame of Reference, volumes only)")}
    ${zone("replace", "Replace with", "shown instead of the current series")}
  </div>`;
}
