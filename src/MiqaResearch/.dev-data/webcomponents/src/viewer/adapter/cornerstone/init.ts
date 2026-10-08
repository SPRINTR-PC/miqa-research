// One-time Cornerstone3D initialisation (memoised). Browser only: needs Worker + WebGL.
// Later tickets register their extras here: volume loaders (#282), peerImport for
// dicom-microscopy-viewer (#285). Tools are registered in tools.ts (registerCornerstoneTool).
import {
  ProgressiveRetrieveImages,
  cornerstoneStreamingImageVolumeLoader,
  init as csInit,
  metaData,
  utilities,
  volumeLoader,
} from "@cornerstonejs/core";
import dicomImageLoader from "@cornerstonejs/dicom-image-loader";
import { registerDefaultProviders } from "@cornerstonejs/metadata";
import * as csTools from "@cornerstonejs/tools";

import { addRegisteredTools } from "./tools.ts";
import { peerImport } from "./wsi.ts";

let initPromise: Promise<void> | undefined;

export function initCornerstone(): Promise<void> {
  initPromise ??= (async () => {
    // Typed metadata path (@cornerstonejs/metadata): /metadata is added per imageId with
    // utilities.addDicomWebInstance, never through the legacy wadors.metaDataManager.
    registerDefaultProviders();
    metaData.addProvider(
      utilities.calibratedPixelSpacingMetadataProvider.get.bind(utilities.calibratedPixelSpacingMetadataProvider),
      11000,
    );
    dicomImageLoader.init();
    // #282: volumes stream interleaved (spec "Oversized series": no HTJ2K/rangeIndex stages).
    volumeLoader.registerVolumeLoader("cornerstoneStreamingImageVolume", cornerstoneStreamingImageVolumeLoader as never);
    utilities.imageRetrieveMetadataProvider.add("volume", ProgressiveRetrieveImages.interleavedRetrieveStages);
    // Partial config: CS3D deep-merges it over its defaults (maxCacheSize 3 GiB, preferSizeOverAccuracy
    // false stay). peerImport supplies dmv for WSI (#285).
    csInit({ peerImport } as Parameters<typeof csInit>[0]);
    csTools.init();
    addRegisteredTools();
  })();
  return initPromise;
}
