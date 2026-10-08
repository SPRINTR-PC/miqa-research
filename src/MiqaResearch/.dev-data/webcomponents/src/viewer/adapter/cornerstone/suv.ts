// SUV (#284): whole-series SUVbw scaling factors from @cornerstonejs/calculate-suv (re-exported by
// @cornerstonejs/metadata), added as each image's `scalingModule` so the image loader pre-scales PET
// to SUV. CS3D's typed provider only tries per instance and falls back to Bq/ml silently, so the
// status reported is what CS3D will actually use: `scalingModule.suvbw` present or not.
import { metaData, utilities } from "@cornerstonejs/core";
import { calculateSUVScalingFactors } from "@cornerstonejs/metadata";

import type { LoadedSeries } from "../../series.ts";
import { isPet, seriesInstances, suvInputs, type SuvStatus } from "../../suv.ts";

const statusBySeries = new Map<string, SuvStatus>();

/** Add SUV scaling for a PET series' `imageIds` (same order as `series.images`); undefined off PET. */
export function applySuvScaling(series: LoadedSeries, imageIds: string[]): SuvStatus | undefined {
  if (!isPet(series) || !imageIds.length) return undefined;
  const instances = seriesInstances(series);
  const inputs = suvInputs(instances);
  let reason = inputs.ok ? "" : inputs.reason;
  if (inputs.ok) {
    try {
      const factors = calculateSUVScalingFactors(inputs.inputs as never) as { suvbw: number }[];
      const byInstance = new Map(instances.map((instance, n) => [instance, factors[n]]));
      imageIds.forEach((id, n) => {
        const factor = byInstance.get(series.images[n].instance);
        if (factor) utilities.genericMetadataProvider.add(id, { type: "scalingModule", metadata: factor });
      });
    } catch (e) {
      reason = e instanceof Error ? e.message : String(e);
    }
  }
  const scaling = metaData.get("scalingModule", imageIds[0]) as { suvbw?: unknown } | undefined;
  const status: SuvStatus =
    typeof scaling?.suvbw === "number" ? { applied: true } : { applied: false, reason: reason || "no SUVbw scaling factor" };
  statusBySeries.set(series.ref.seriesUid, status);
  return status;
}

/** Status recorded when the series' metadata was registered; undefined off PET or before. */
export function suvStatusOf(seriesUid: string): SuvStatus | undefined {
  return statusBySeries.get(seriesUid);
}
