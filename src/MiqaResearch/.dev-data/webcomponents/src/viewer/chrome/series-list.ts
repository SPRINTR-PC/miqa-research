// Series list (far left). #280 lists the open series; the entry contract's related series (#279),
// drag-to-fuse/replace drop zones (#284) and the Annotation/Segmentation tree (#290) extend it.
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

export function seriesList(items: SeriesListItem[]) {
  return html`<aside class="series" aria-label="Series">
    <h5>Series</h5>
    ${items.map(
      (s) => html`<div class="ser ${s.shown ? "shown" : ""}" data-series-uid=${s.seriesUid}>
        <span class="mod">${s.modality || "?"}</span>
        <span class="txt"><b>${s.description || s.seriesUid}</b><small>${s.imageCount} images</small></span>
      </div>`,
    )}
    ${items.length ? nothing : html`<p class="hint">Loading…</p>`}
  </aside>`;
}
