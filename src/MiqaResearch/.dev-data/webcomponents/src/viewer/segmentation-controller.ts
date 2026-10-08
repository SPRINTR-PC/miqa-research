// The element's Segmentation (#286): made on first use of a segment tool (or "New segmentation"),
// through the size guard (#283), then shown in every stack / volume view the element opens.
// One per element, on the base series' grid; Save (#289) exports it as SEG.
import type { SegmentationView, ViewControls, ViewerAdapter } from "./adapter/adapter.ts";
import type { ValueRange } from "./segmentation.ts";
import type { LoadedSeries } from "./series.ts";
import { TOO_LARGE_MESSAGE, isTooLargeError, labelmapBytes, seriesGrid, type SizeGuard } from "./size-guard.ts";

export interface SegmentationHost {
  adapter(): ViewerAdapter | undefined;
  series(): LoadedSeries | undefined;
  readonly budget: SizeGuard;
  refuse(message: string): void;
  /** State changed: re-render. */
  changed(): void;
}

export class SegmentationController {
  view: SegmentationView | undefined;
  /** A labelmap is being made. */
  busy = false;
  /** Voxels set by the last threshold run. */
  thresholdResult: number | undefined;
  private readonly host: SegmentationHost;

  constructor(host: SegmentationHost) {
    this.host = host;
  }

  /** The Segmentation, made and shown in `shownIn` if there is none; undefined (refusal shown) when it doesn't fit. */
  async ensure(shownIn: ViewControls | undefined): Promise<SegmentationView | undefined> {
    if (this.view || this.busy) return this.view;
    const adapter = this.host.adapter();
    const series = this.host.series();
    const grid = series && seriesGrid(series);
    if (!adapter || !series || !grid) return undefined;
    const id = `seg:${series.ref.seriesUid}`;
    const reserved = this.host.budget.reserveLabelmap(series.ref.seriesUid, id, labelmapBytes(grid));
    if (!reserved.ok) {
      this.host.refuse(reserved.message);
      return undefined;
    }
    this.busy = true;
    try {
      this.view = await adapter.openSegmentation(series, id, () => this.host.changed());
      if (shownIn) await this.view.show(shownIn);
      return this.view;
    } catch (e) {
      this.view?.close();
      this.view = undefined;
      this.host.budget.release(id);
      this.host.refuse(isTooLargeError(e) ? TOO_LARGE_MESSAGE : `Can't add a segmentation: ${e instanceof Error ? e.message : String(e)}`);
      return undefined;
    } finally {
      this.busy = false;
      this.host.changed();
    }
  }

  /** Show the Segmentation (if any) in a newly opened or re-laid-out view. */
  async show(view: ViewControls | undefined): Promise<void> {
    if (this.view && view) await this.view.show(view);
  }

  runThreshold(range: ValueRange, slices: number, sourceSeriesUid: string): void {
    if (!this.view) return;
    this.thresholdResult = this.view.threshold(range, { slices, sourceSeriesUid });
    this.host.changed();
  }

  close(): void {
    if (!this.view) return;
    this.host.budget.release(this.view.id);
    this.view.close();
    this.view = undefined;
  }
}
