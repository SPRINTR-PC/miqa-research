// Feed WADO-RS /metadata to Cornerstone3D through the typed path only
// (spec: ERMF/Proj/Calibrated/US-region handling exists only there).
import { utilities as mdUtilities } from "@cornerstonejs/metadata";

import type { LoadedSeries } from "../../series.ts";

/** Register every frame's instance metadata; returns the series' imageIds in display order. */
export function registerSeriesMetadata(series: LoadedSeries): string[] {
  return series.images.map(({ imageId, instance }) => {
    void mdUtilities.addDicomWebInstance(imageId, instance);
    return imageId;
  });
}
