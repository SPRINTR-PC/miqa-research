// In-memory ViewerAdapter for vitest: records calls and lets a test drive state changes.
import type { LoadedSeries } from "../series.ts";
import type { StackState, StackView, ViewerAdapter, VoiRange } from "./adapter.ts";

export class StubStackView implements StackView {
  current: StackState;
  private readonly onChange: () => void;

  constructor(series: LoadedSeries, onChange: () => void) {
    this.current = { imageIndex: 0, imageCount: series.images.length, voi: undefined };
    this.onChange = onChange;
  }

  state(): StackState {
    return { ...this.current };
  }

  scrollTo(imageIndex: number): void {
    this.current.imageIndex = Math.max(0, Math.min(imageIndex, this.current.imageCount - 1));
    this.onChange();
  }

  setVoi(voi: VoiRange): void {
    this.current.voi = voi;
    this.onChange();
  }
}

export class StubAdapter implements ViewerAdapter {
  opened: { element: HTMLDivElement; series: LoadedSeries }[] = [];
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

  resize(): void {
    this.resizes += 1;
  }

  destroy(): void {
    this.destroyed = true;
  }
}
