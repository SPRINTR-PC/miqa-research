// Feed WADO-RS /metadata to Cornerstone3D through the typed path only
// (spec: ERMF/Proj/Calibrated/US-region handling exists only there).
import { Enums, utilities } from "@cornerstonejs/core";
import { utilities as mdUtilities } from "@cornerstonejs/metadata";

import { secondaryCaptureSpacing } from "../../calibration.ts";
import type { LoadedSeries } from "../../series.ts";
import { applySuvScaling } from "./suv.ts";

/** Register every frame's instance metadata; returns the series' imageIds in display order. */
export function registerSeriesMetadata(series: LoadedSeries): string[] {
  const imageIds = series.images.map(({ imageId, instance }) => {
    void mdUtilities.addDicomWebInstance(imageId, instance);
    // SC shim (#281): CS3D treats SC PixelSpacing as trusted tomographic `mm`. Tag it Unknown
    // (`mm Unknown`) before CS3D's IMAGE_PLANE provider adds its own entry (it keeps an existing one).
    const sc = secondaryCaptureSpacing(instance);
    if (sc) utilities.calibratedPixelSpacingMetadataProvider.add(imageId, { ...sc, type: Enums.CalibrationTypes.UNKNOWN });
    return imageId;
  });
  // PET (#284): whole-series SUV scaling, before any image loads; status via suvStatusOf (./suv.ts).
  applySuvScaling(series, imageIds);
  return imageIds;
}
