// In-memory ViewerAdapter for vitest: records calls and lets a test drive state changes.
import type { LoadedSeries } from "../series.ts";
import type { StackState, StackView, ViewerAdapter, VoiRange } from "./adapter.ts";

export class StubStackView implements StackView {
  current: StackState;
  /** Window the image came with; resetVoi/resetView go back to it. */
  defaultVoi: VoiRange | undefined;
  resets = 0;
  private readonly onChange: () => void;

  constructor(series: LoadedSeries, onChange: () => void) {
    this.current = {
      imageIndex: 0,
      imageCount: series.images.length,
      voi: undefined,
      activeTool: "",
      invert: false,
      zoom: 1,
      pan: [0, 0],
      unit: "mm",
      annotationCount: 0,
    };
    this.onChange = onChange;
  }

  state(): StackState {
    return { ...this.current };
  }

  /** Test helper: apply a partial state change as the engine would, and notify. */
  emit(change: Partial<StackState>): void {
    Object.assign(this.current, change);
    this.onChange();
  }

  scrollTo(imageIndex: number): void {
    this.emit({ imageIndex: Math.max(0, Math.min(imageIndex, this.current.imageCount - 1)) });
  }

  setVoi(voi: VoiRange): void {
    this.emit({ voi });
  }

  resetVoi(): void {
    this.emit({ voi: this.defaultVoi });
  }

  setTool(toolId: string): void {
    this.emit({ activeTool: toolId });
  }

  toggleInvert(): void {
    this.emit({ invert: !this.current.invert });
  }

  resetView(): void {
    this.resets += 1;
    this.emit({ voi: this.defaultVoi, invert: false, zoom: 1, pan: [0, 0] });
  }
}

export class StubAdapter implements ViewerAdapter {
  opened: { element: HTMLDivElement; series: LoadedSeries }[] = [];
  openedWsi: { element: HTMLDivElement; series: LoadedSeries }[] = [];
  views: StubStackView[] = [];
  resizes = 0;
  destroyed = false;
  /** Set to make the next openStack reject. */
  failWith: Error | undefined;

  async openStack(element: HTMLDivElement, series: LoadedSeries, onChange: () => void): Promise<StackView> {
    if (this.failWith) throw this.failWith;
    this.opened.push({ element, series });
    const view = new StubStackView(series, onChange);
    this.views.push(view);
    return view;
  }

  async openWsi(element: HTMLDivElement, series: LoadedSeries, onChange: () => void): Promise<StackView> {
    if (this.failWith) throw this.failWith;
    this.openedWsi.push({ element, series });
    const view = new StubStackView({ ...series, images: series.images.slice(0, 1) }, onChange);
    this.views.push(view);
    return view;
  }

  resize(): void {
    this.resizes += 1;
  }

  destroy(): void {
    this.destroyed = true;
  }
}
