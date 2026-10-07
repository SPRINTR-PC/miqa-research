// One-time Cornerstone3D initialisation (memoised). Browser only: needs Worker + WebGL.
// Later tickets register their extras here: volume loaders (#282), peerImport for
// dicom-microscopy-viewer (#285), segmentation/annotation tools (#280, #286).
import { init as csInit, metaData, utilities } from "@cornerstonejs/core";
import dicomImageLoader from "@cornerstonejs/dicom-image-loader";
import { registerDefaultProviders } from "@cornerstonejs/metadata";
import * as csTools from "@cornerstonejs/tools";

/** Tools registered globally; tool groups pick from these. Always reference tools by `.toolName` (minify mangles class names). */
export const STACK_TOOLS = [
  csTools.WindowLevelTool,
  csTools.PanTool,
  csTools.ZoomTool,
  csTools.StackScrollTool,
] as const;

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
    csInit();
    csTools.init();
    STACK_TOOLS.forEach((tool) => csTools.addTool(tool));
  })();
  return initPromise;
}
