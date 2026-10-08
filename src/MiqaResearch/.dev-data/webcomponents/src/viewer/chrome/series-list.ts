// Series list (far left). #280 lists the open series; the entry contract's related series (#279),
// drag-to-fuse/replace drop zones (#284) and the Annotation/Segmentation tree (#290, chrome/results-tree.ts) extend it.
import { html, nothing } from "lit";

import type { LoadedSeries } from "../series.ts";

export interface SeriesListItem {
  studyUid: string;
  seriesUid: string;
  modality: string;
  description: string;
  imageCount: number;
  /** Shown in the viewport. */
  shown: boolean;
}

const MODALITY = "00080060";
const SERIES_DESCRIPTION = "0008103E";

/** List row for a loaded series, from its first instance's /metadata. */
export function seriesListItem(series: LoadedSeries, shown = true): SeriesListItem {
  const first = series.images[0]?.instance ?? {};
  const text = (tag: string) => String(first[tag]?.Value?.[0] ?? "");
  return {
    studyUid: series.ref.studyUid,
    seriesUid: series.ref.seriesUid,
    modality: text(MODALITY),
    description: text(SERIES_DESCRIPTION),
    imageCount: series.images.length,
    shown,
  };
}

/** What the results tree (#290) adds: a row above the list (blinding lock), rows under each series, a footer. */
export interface SeriesListExtras {
  top?: unknown;
  nested?: (seriesUid: string) => unknown;
  footer?: unknown;
}

export function seriesList(items: SeriesListItem[], extras: SeriesListExtras = {}) {
  return html`<aside class="series" aria-label="Series">
    <h5>Series</h5>
    ${extras.top ?? nothing}
    ${items.map(
      // Rows are draggable onto the big view (#284 drop zones: top half fuses, bottom half replaces).
      (s) => html`<div class="ser-group" data-series-uid=${s.seriesUid}>
        <div class="ser ${s.shown ? "shown" : ""}" data-series-uid=${s.seriesUid} draggable="true"
          title="Drag onto the view: top half fuses, bottom half replaces">
          <span class="mod">${s.modality || "?"}</span>
          <span class="txt"><b>${s.description || s.seriesUid}</b><small>${s.imageCount} images</small></span>
        </div>
        ${extras.nested?.(s.seriesUid) ?? nothing}
      </div>`,
    )}
    ${items.length ? nothing : html`<p class="hint">Loading…</p>`}
    ${extras.footer ?? nothing}
  </aside>`;
}
