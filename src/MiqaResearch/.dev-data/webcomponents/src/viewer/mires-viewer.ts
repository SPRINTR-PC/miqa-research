// <mires-viewer>: the DICOM viewer element (spec #271). Lit in Shadow DOM.
// Talks to the rendering engine only through the ViewerAdapter seam (./adapter/adapter.ts);
// the Cornerstone3D adapter is imported lazily so unit tests never load CS3D.
//
// Chrome B (#280): series list | tool rail | viewport | inspector. Tools, presets, commands and
// inspector panels come from registries (tools/, commands.ts, inspector/) that later tickets
// extend from their own modules; see README.md "Extension points".
import { LitElement, css, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import type {
  AdapterFactory,
  AnnotationSet,
  StackState,
  StackView,
  ViewControls,
  ViewerAdapter,
  VolumeState,
  VolumeView,
  WsiView,
} from "./adapter/adapter.ts";
import { fetchBulkAnnotations, type BulkAnnotationGroup } from "./bulk-annotations.ts";
import { seriesList, seriesListItem, type SeriesListItem } from "./chrome/series-list.ts";
import { toolRail } from "./chrome/tool-rail.ts";
import { refusalMessage, sizeBanner, sizeBannerStyles } from "./chrome/size-banner.ts";
import { conflictDialog, saveDialogStyles, toast } from "./chrome/save-dialogs.ts";
import { lockRow, resultChips, resultRows, resultsConfirm, resultsFooter, resultsTreeStyles } from "./chrome/results-tree.ts";
import { draftBanner, draftBannerStyles } from "./chrome/draft-banner.ts";
import { volumeGrid, volumeGridStyles } from "./chrome/volume-grid.ts";
import { dropZones, dropZoneStyles, type DropZone } from "./chrome/drop-zones.ts";
import { commands } from "./commands.ts";
import type { ViewerContext } from "./context.ts";
import { FirstRenderReport } from "./first-render.ts";
import { DraftController, DraftStore, defaultDraftBackend, type Draft, type DraftBackend, type DraftHost } from "./drafts.ts";
import { inspector } from "./inspector/index.ts";
import { burnedInWarning } from "./calibration.ts";
import { fuseBlocker, layerDisplay, modalityOf, overlayBudget, replaceBlocker, seriesLabel } from "./fusion.ts";
import { clampSplit, loadSplit, saveSplit, swapIntoMain, threeViews, type ViewLayout } from "./layout.ts";
import { isReconstructable, type Reconstructability } from "./reconstructable.ts";
import { SaveController, type ObjectKind, type ObjectVersion, type SaveHost } from "./save.ts";
import { Quiet, ResultsController, baseOf, kindOf, type ResultChain, type ResultsHost } from "./results.ts";
import { fetchSavedSegmentation } from "./saved-seg.ts";
import { fetchSeries, type DicomJsonInstance, type LoadedSeries, type SeriesRef } from "./series.ts";
import {
  SizeGuard,
  TOO_LARGE_MESSAGE,
  checkImageTexture,
  fitVolume,
  isTooLargeError,
  refusalMessage as budgetRefusal,
  seriesGrid,
  volumeEntries,
  type BudgetEntry,
  type GpuLimits,
  type VolumeFit,
} from "./size-guard.ts";
import { presets, presetVoi, tools, voiToWindow, type Preset, type ToolScope, type ViewportKind } from "./tools/index.ts";
import { CROSSHAIRS } from "./tools/volume.ts";
import { isSegmentTool } from "./tools/segmentation.ts";
import { SegmentationController } from "./segmentation-controller.ts";
import type { SegmentationState } from "./segmentation.ts";
import { suvStatusFor, type SuvStatus } from "./suv.ts";
import { unitTooltip } from "./units.ts";
import { isWholeSlide, WSI_DEFAULT_TOOL } from "./wsi.ts";

export type ViewerState = "loading" | "ready" | "error";

const DEFAULT_TOOL = "WindowLevel";

const cornerstoneAdapter: AdapterFactory = async () => {
  const { createCornerstoneAdapter } = await import("./adapter/cornerstone/index.ts");
  return createCornerstoneAdapter();
};

@customElement("mires-viewer")
export class MiresViewer extends LitElement {
  @property({ attribute: "wado-root" }) wadoRoot = "/api/v1/dicom";
  @property({ attribute: "study-uid" }) studyUid = "";
  @property({ attribute: "series-uid" }) seriesUid = "";
  /** Annotate role on this participant (set by the page from the server): Arrow, Calibrate, segment tools, Save. */
  @property({ type: Boolean, attribute: "can-annotate" }) canAnnotate = false;
  /** Study Participant id of the series (set by the page): lists its Annotations, e.g. bulk ANN on a slide (#292). */
  @property() participant = "";
  /** The logged-in user's id (set by the page): drafts (#291) are kept per user. No user, no drafts. */
  @property() user = "";
  @property({ attribute: "api-root" }) apiRoot = "/api/v1/viewer";
  /**
   * Other series of the same study to offer in the series list (#284), space-separated UIDs; they can be
   * dropped onto the view to fuse or replace. The entry contract (#279) fills it with the Related Series.
   */
  @property({ attribute: "related-series" }) relatedSeries = "";

  /** Reflected for pages and browser tests: loading → ready | error. */
  @property({ reflect: true }) state: ViewerState = "loading";

  /** Swapped by tests for a stub; defaults to the Cornerstone3D adapter. */
  adapterFactory: AdapterFactory = cornerstoneAdapter;
  /** Where drafts (#291) live: IndexedDB; unit tests swap in memory. Set before the element connects. */
  draftBackend: DraftBackend | undefined;

  @state() private stack: StackState | undefined;
  @state() private error = "";
  @state() private series: SeriesListItem[] = [];
  @state() private viewportKind: ViewportKind = "stack";
  @state() private bulkGroups: BulkAnnotationGroup[] = [];

  /** Stack, or a volume in one / three views (#282). */
  @state() private layout: ViewLayout = { kind: "stack" };
  @state() private volume: VolumeState | undefined;
  @state() private split = loadSplit();
  /** A layout switch is running (views being closed/opened); further switches are ignored. */
  @state() layoutBusy = false;

  /** Size guard (#283): the budget ledger, shared with fusion (#284) and segmentation (#286) via the context. */
  readonly budget = new SizeGuard();
  /** Segmentation (#286): one labelmap on the base series, made on first use of a segment tool. */
  private readonly segmentation = new SegmentationController({
    adapter: () => this.adapter,
    series: () => this.loaded,
    budget: this.budget,
    refuse: (message) => this.refuse(message),
    changed: () => this.requestUpdate(),
  });
  /** Save (#289): Annotations (SR) and the Segmentation (SEG) of the base series. */
  readonly save = new SaveController(this.saveHost());
  /** Results tree (#290): the participant's Annotations and Segmentations, shown / hidden from the series list. */
  readonly results = new ResultsController(this.resultsHost());
  /** Annotation ids each shown SR chain added (by chain id), to hide them again. */
  private readonly resultAnnotations = new Map<string, string[]>();
  /** Drafts (#291): autosave of unsaved edits, the recovery banner on open. Made on first open. */
  drafts: DraftController | undefined;
  @state() private toastMessage = "";
  private toastTimer: ReturnType<typeof setTimeout> | undefined;
  @state() private gpu: GpuLimits | undefined;
  /** Whether the series fits as a full-resolution volume; drives the banner and the layout panel. */
  @state() private volumeFit: VolumeFit | undefined;
  @state() private refusal = "";

  /** Fusion (#284): the series being dragged from the list, and the drop zone under the pointer. */
  @state() private dragged: string | undefined;
  @state() private dragOver: DropZone | undefined;
  /** A fuse / replace is running; further drops are ignored. */
  @state() fusionBusy = false;
  /** SUV status of the series shown (PET), from the adapter. */
  @state() private suv: SuvStatus | undefined;
  /** Loaded /metadata per series UID: the series shown and the related ones. */
  private readonly catalog = new Map<string, LoadedSeries>();

  private adapter: ViewerAdapter | undefined;
  /** Annotations of every view (#289). */
  private annotations: AnnotationSet | undefined;
  private view: StackView | undefined;
  private wsiView: WsiView | undefined;
  private volumeView: VolumeView | undefined;
  private loaded: LoadedSeries | undefined;
  private mpr: Reconstructability | undefined;
  private resizeObserver: ResizeObserver | undefined;
  private disposed = false;
  /** First-render marks + beacon (#293); volume views mark "interleaved" / "volume-loaded" on it. */
  firstRender: FirstRenderReport | undefined;

  static styles = [volumeGridStyles, sizeBannerStyles, dropZoneStyles, saveDialogStyles, resultsTreeStyles, draftBannerStyles, css`
    :host { display: block; position: relative; background: #0b0d10; color: #d8dde3; font: 13px system-ui, sans-serif; outline: none; }
    .chrome { position: absolute; inset: 0; display: grid; grid-template-columns: 180px 56px minmax(0, 1fr) 250px; }
    button { font: inherit; color: inherit; background: #1b2027; border: 1px solid #2b323c; border-radius: 4px; padding: 4px 8px; cursor: pointer; }
    button:hover { background: #26303b; }
    button[aria-pressed="true"] { background: #1f6feb; border-color: #1f6feb; color: #fff; }
    button:disabled { opacity: 0.4; cursor: default; }
    kbd { font: 10px ui-monospace, monospace; background: #2b323c; border-radius: 3px; padding: 0 3px; color: #aab; }
    h5 { margin: 10px 0 6px; font-size: 10px; text-transform: uppercase; color: #6c7684; font-weight: 600; }
    .hint { color: #8a94a0; font-size: 12px; line-height: 1.5; }

    .series { background: #0f1318; border-right: 1px solid #262c35; overflow-y: auto; padding: 0 6px; }
    .ser { display: flex; gap: 6px; align-items: center; padding: 6px; border: 1px solid #262c35; border-radius: 4px; margin-bottom: 4px; background: #151a21; }
    .ser.shown { background: #16233a; }
    .ser .mod { font: 600 11px ui-monospace, monospace; background: #2b323c; border-radius: 3px; padding: 6px 4px; min-width: 22px; text-align: center; }
    .ser .txt { display: flex; flex-direction: column; min-width: 0; font-size: 12px; }
    .ser .txt b { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-weight: 500; }
    .ser .txt small { color: #7a8591; font-size: 10px; }

    .rail { background: #141920; border-right: 1px solid #262c35; display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 4px 0; overflow-y: auto; }
    .rail h6 { margin: 8px 0 2px; font-size: 9px; text-transform: uppercase; color: #6c7684; font-weight: 600; }
    .rail button { width: 40px; height: 36px; font-size: 16px; padding: 0; position: relative; flex: none; }
    .rail button kbd { position: absolute; bottom: 1px; right: 2px; font-size: 8px; padding: 0 2px; }

    .stage { position: relative; background: #000; min-width: 0; min-height: 0; }
    .viewport { position: absolute; inset: 0; }
    .overlay { position: absolute; left: 8px; bottom: 8px; pointer-events: none; text-shadow: 0 0 2px #000; font: 12px ui-monospace, monospace; }
    .burned-in { position: absolute; left: 8px; top: 8px; z-index: 5; padding: 1px 6px; border-radius: 3px; font-size: 11px; cursor: help; background: #3b2a12; border: 1px solid #8a5a14; color: #ffcf7a; }
    .unit { position: absolute; right: 8px; top: 8px; z-index: 5; padding: 1px 6px; border-radius: 3px; font: 11px ui-monospace, monospace; cursor: help; background: #1d2b3b; border: 1px solid #2f4a6b; }
    [role="alert"] { position: absolute; inset: auto 8px 8px; color: #f88; }

    .inspector { background: #11151a; border-left: 1px solid #262c35; overflow-y: auto; padding: 0 10px 8px; }
    .inspector .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; }
    .inspector .grid2 button { text-align: left; font-size: 12px; }
    .inspector .row { display: flex; gap: 4px; margin-top: 6px; flex-wrap: wrap; }
    .inspector .badge { font: 11px ui-monospace, monospace; padding: 1px 6px; border-radius: 3px; background: #1d2b3b; border: 1px solid #2f4a6b; }
    .inspector .save-buttons { display: flex; flex-direction: column; gap: 4px; }
    .inspector .save-buttons button { text-align: left; font-size: 12px; }
    .inspector .save-dropped, .inspector .save-error { color: #ffcf7a; }
    .inspector .badge[data-level="warn"] { background: #3b2a12; border-color: #8a5a14; color: #ffcf7a; }
  `];

  /** Current stack state, for browser tests and diagnostics. */
  get stackState(): StackState | undefined {
    return this.view?.state();
  }

  /** The open stack view (scroll / window), for browser tests and diagnostics. */
  get stackView(): StackView | undefined {
    return this.view;
  }

  /** Current volume state (#282), for browser tests and diagnostics. */
  get segmentationState(): (SegmentationState & { voxels: Record<number, number> }) | undefined {
    const view = this.segmentation.view;
    return view && { ...view.state(), voxels: view.voxelCounts() };
  }

  /** A labelmap is being made (#286). */
  get segmentationBusy(): boolean {
    return this.segmentation.busy;
  }

  /** Select a tool; a segment tool first makes the Segmentation (size guard) and stays off if refused. */
  private async selectTool(id: string): Promise<void> {
    if (isSegmentTool(id) && !(await this.segmentation.ensure(this.controls))) return;
    this.controls?.setTool(id);
  }

  get volumeState(): VolumeState | undefined {
    return this.volumeView?.state();
  }

  /** Controls of whichever view is open. */
  private get controls(): ViewControls | undefined {
    return this.volumeView ?? this.view;
  }

  connectedCallback(): void {
    super.connectedCallback();
    this.disposed = false;
    if (!this.hasAttribute("tabindex")) this.tabIndex = 0;
    this.addEventListener("keydown", this.onKey);
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    this.disposed = true;
    this.removeEventListener("keydown", this.onKey);
    this.resizeObserver?.disconnect();
    this.firstRender?.dispose();
    clearTimeout(this.toastTimer);
    this.drafts?.dispose();
    this.segmentation.close();
    this.annotations?.dispose();
    this.annotations = undefined;
    this.adapter?.destroy();
    this.adapter = undefined;
    this.view = undefined;
    this.wsiView = undefined;
    this.volumeView = undefined;
  }

  protected firstUpdated(): void {
    void this.open();
  }

  private async open(): Promise<void> {
    this.firstRender = new FirstRenderReport();
    try {
      const series = await fetchSeries({ wadoRoot: this.wadoRoot, studyUid: this.studyUid, seriesUid: this.seriesUid });
      this.firstRender.series(series);
      this.series = [seriesListItem(series)];
      this.catalog.set(series.ref.seriesUid, series);
      this.loaded = series;
      this.mpr = isReconstructable(series);
      this.adapter = await this.adapterFactory();
      if (this.disposed) return this.adapter.destroy();
      this.annotations = this.adapter.watchAnnotations(() => this.requestUpdate());
      const wsi = isWholeSlide(series);
      if (wsi) this.viewportKind = "wsi";
      // Size guard (#283): 2D images must fit one texture (WSI is tiled); 3D is checked against the budget.
      this.gpu = this.adapter.gpuLimits();
      if (!wsi) {
        const texture = checkImageTexture(series, this.gpu);
        if (!texture.ok) throw new Error(texture.message);
      }
      this.volumeFit = this.fitVolume();
      await this.openStackView(this.adapter, series);
      this.view!.setTool(wsi ? WSI_DEFAULT_TOOL : DEFAULT_TOOL);
      this.stack = this.view!.state();
      this.firstRender.mark("first-image");
      this.resizeObserver = new ResizeObserver(() => this.adapter?.resize());
      this.resizeObserver.observe(this.renderRoot.querySelector(".stage")!);
      this.state = "ready";
      this.drafts = new DraftController(new DraftStore(this.draftBackend ?? defaultDraftBackend()), this.draftHost());
      void this.drafts.check();
      void this.loadRelated();
      void this.results.refresh();
    } catch (e) {
      this.fail(e);
    }
  }

  /** Related series (#284): /metadata of each, listed in attribute order; a failure only drops that row. */
  private async loadRelated(): Promise<void> {
    const uids = [...new Set(this.relatedSeries.split(/[\s,]+/))].filter((u) => u && !this.catalog.has(u));
    const results = await Promise.allSettled(
      uids.map((seriesUid) => fetchSeries({ wadoRoot: this.wadoRoot, studyUid: this.studyUid, seriesUid })),
    );
    if (this.disposed) return;
    results.forEach((r, i) => {
      if (r.status === "fulfilled") this.catalog.set(uids[i], r.value);
      else console.warn(`Related series ${uids[i]} could not be loaded`, r.reason);
    });
    const loaded = results.flatMap((r) => (r.status === "fulfilled" ? [seriesListItem(r.value, false)] : []));
    this.series = [...this.series, ...loaded];
  }

  /** Bulk ANN on the slide (#292), read-only. A failure leaves the slide usable and is only logged. */
  private async loadBulkAnnotations(view: WsiView, slide: SeriesRef): Promise<void> {
    try {
      const instances = await fetchBulkAnnotations({ apiRoot: this.apiRoot, participant: this.participant }, slide);
      if (instances.length && !this.disposed) await view.addBulkAnnotations(instances);
    } catch (e) {
      console.warn("Bulk annotations could not be shown", e);
    }
  }

  private fail(e: unknown): void {
    this.error = isTooLargeError(e) ? TOO_LARGE_MESSAGE : e instanceof Error ? e.message : String(e);
    this.state = "error";
  }

  private async openStackView(adapter: ViewerAdapter, series: LoadedSeries): Promise<void> {
    const viewport = this.renderRoot.querySelector<HTMLDivElement>(".viewport")!;
    const onChange = () => {
      this.stack = this.view?.state();
      this.bulkGroups = this.wsiView?.bulkAnnotationGroups() ?? [];
    };
    if (isWholeSlide(series)) {
      this.view = this.wsiView = await adapter.openWsi(viewport, series, onChange);
      if (this.participant) void this.loadBulkAnnotations(this.wsiView, series.ref);
    } else {
      this.view = await adapter.openStack(viewport, series, onChange);
    }
    this.suv = adapter.suvStatus(series);
  }

  /** What Save (#289) needs of the element: edits, bytes from the adapter, loading the head saved first. */
  private saveHost(): SaveHost {
    const el = this;
    return {
      get apiRoot() {
        return el.apiRoot;
      },
      revision: (kind) => (kind === "annotation" ? (el.annotations?.revision() ?? 0) : el.segmentation.revision()),
      isEmpty: (kind) =>
        kind === "annotation" ? !el.loaded || !el.annotations?.count(el.loaded) : el.segmentation.isEmpty(),
      // Base series first, then the fused overlays (#284): objects made on a Fusion list them all.
      sourceSeries: () => [el.seriesUid, ...(el.volume?.layers ?? []).map((l) => l.seriesUid).filter((uid) => uid !== el.seriesUid)],
      build: async (kind) => {
        if (kind === "segmentation") {
          if (!el.segmentation.view) throw new Error("no segmentation");
          return el.segmentation.view.exportSeg();
        }
        if (!el.annotations || !el.loaded) throw new Error("the viewer isn't ready");
        return el.annotations.exportSr(el.loaded);
      },
      loadTheirs: (kind, head) => el.loadTheirs(kind, head),
      changed: () => el.requestUpdate(),
      toast: (message) => el.showToast(message),
      saved: (kind) => el.drafts?.saved(kind),
    };
  }

  protected updated(): void {
    this.drafts?.edited();
  }

  /** What drafts (#291) need of the element: the key, edits as Save counts them, snapshots from the adapter. */
  private draftHost(): DraftHost {
    const el = this;
    return {
      key: (kind) =>
        el.user && el.participant && el.canAnnotate && el.loaded
          ? { user: el.user, participant: el.participant, seriesUid: el.loaded.ref.seriesUid, kind }
          : undefined,
      revision: (kind) => (kind === "annotation" ? (el.annotations?.revision() ?? 0) : el.segmentation.revision()),
      dirty: (kind) => el.save.dirty(kind),
      isEmpty: (kind) =>
        kind === "annotation" ? !el.loaded || !el.annotations?.count(el.loaded) : el.segmentation.isEmpty(),
      base: (kind) => el.save.base(kind),
      snapshot: async (kind) => {
        if (kind === "segmentation") return el.segmentation.view?.snapshot();
        return el.loaded && el.annotations?.snapshot(el.loaded);
      },
      restore: (draft) => el.restoreDraft(draft),
      changed: () => el.requestUpdate(),
    };
  }

  /** Restore a draft: on top of its base head (Save then supersedes it), the edits replace what is shown. */
  private async restoreDraft(draft: Draft): Promise<void> {
    const series = this.loaded;
    if (!series || series.ref.seriesUid !== draft.seriesUid) throw new Error("another series is shown");
    if (draft.base) this.save.setHead(draft.kind, draft.base.head, draft.base.canChange);
    if (draft.kind === "annotation") {
      if (!this.annotations) throw new Error("the viewer isn't ready");
      this.annotations.restore(draft.data, series);
    } else {
      const view = await this.segmentation.ensure(this.controls);
      if (!view) throw new Error("the Segmentation doesn't fit");
      view.restore(draft.data);
    }
  }

  /** 409 "Discard mine, load theirs": drop the local edits and show the head saved first (in the results tree too, #290). */
  private async loadTheirs(kind: ObjectKind, head: ObjectVersion): Promise<void> {
    const series = this.loaded;
    if (!series) return;
    this.results.hideWhere((c) => kindOf(c) === kind);
    if (kind === "segmentation") {
      this.segmentation.close();
      await this.showSavedSegmentation(head);
    } else {
      this.annotations?.clear(series);
      await this.showSr(head);
    }
    await this.results.refresh();
    const chain = this.results.chain(head.chain_id);
    if (chain) this.results.markShown(chain);
    this.showToast(`Showing ${kind === "segmentation" ? "Segmentation" : "Annotations"} v${head.version}`);
  }

  /** Import an SR head's annotations onto the base series, remembering them by chain to hide them again. */
  private async showSr(head: ObjectVersion): Promise<void> {
    const series = this.loaded;
    if (!series || !this.annotations) throw new Error("the viewer isn't ready");
    const url = `${this.wadoRoot}/studies/${this.studyUid}/series/${head.series_instance_uid}/metadata`;
    const response = await fetch(url, { credentials: "same-origin", headers: { Accept: "application/dicom+json" } });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const [instance] = (await response.json()) as DicomJsonInstance[];
    if (!instance) throw new Error("the SR has no instance");
    this.resultAnnotations.set(head.chain_id, await this.annotations.importSr(instance, series));
  }

  /** Show a saved SEG as the element's Segmentation (`/metadata` + `/frames`: sessions can't fetch raw bytes). */
  private async showSavedSegmentation(head: ObjectVersion): Promise<void> {
    const saved = await fetchSavedSegmentation({ wadoRoot: this.wadoRoot, studyUid: this.studyUid, seriesUid: head.series_instance_uid });
    if (!(await this.segmentation.load(saved, this.controls))) throw new Quiet("refused"); // the refusal says why
  }

  /** What the results tree (#290) needs of the element: bring the source series in, show / hide heads. */
  private resultsHost(): ResultsHost {
    const el = this;
    return {
      get apiRoot() {
        return el.apiRoot;
      },
      get participant() {
        return el.participant;
      },
      show: (chain) => el.showResult(chain),
      hide: (chain) => el.hideResult(chain),
      changed: () => el.requestUpdate(),
      toast: (message) => el.showToast(message),
    };
  }

  /**
   * Show a head from the results tree: its base series replaces the one shown if needed, the other sources
   * of a Fusion are fused (both within the size guard; refusals are shown), then the SR / SEG is imported
   * and becomes what Save supersedes.
   */
  private async showResult(chain: ResultChain): Promise<void> {
    if (this.layoutBusy || this.fusionBusy) throw new Error("the viewer is busy");
    const kind = kindOf(chain);
    if (kind === "segmentation" && this.segmentation.view && this.save.dirty("segmentation") && !this.segmentation.isEmpty()) {
      this.refuse("Save your Segmentation edits first: one Segmentation is shown at a time.");
      throw new Quiet("unsaved segmentation");
    }
    const base = baseOf(chain);
    this.refusal = "";
    this.fusionBusy = true;
    try {
      if (this.loaded?.ref.seriesUid !== base) {
        await this.replace(base);
        if (this.loaded?.ref.seriesUid !== base) throw new Quiet("not replaced");
      }
      for (const uid of chain.source_series_uids) {
        if (uid !== base && !this.shownUids().includes(uid)) await this.fuse(uid);
      }
    } finally {
      this.fusionBusy = false;
    }
    if (kind === "segmentation") {
      this.results.hideWhere((c) => kindOf(c) === "segmentation"); // one Segmentation at a time
      await this.showSavedSegmentation(chain);
    } else {
      await this.showSr(chain);
    }
    this.save.setHead(kind, chain, chain.can_change);
  }

  /** Hide a head: its annotations removed, or its Segmentation closed; Save no longer supersedes it. */
  private hideResult(chain: ResultChain): void {
    const kind = kindOf(chain);
    if (kind === "annotation") {
      this.annotations?.remove(this.resultAnnotations.get(chain.chain_id) ?? []);
      this.resultAnnotations.delete(chain.chain_id);
    } else {
      this.segmentation.close();
    }
    if (this.save.head(kind)?.chain_id !== chain.chain_id) return;
    const other = [...this.results.shown.values()].find((c) => kindOf(c) === kind);
    if (other) this.save.setHead(kind, other, other.can_change);
    else this.save.forgetHead(kind);
  }

  private showToast(message: string): void {
    this.toastMessage = message;
    clearTimeout(this.toastTimer);
    this.toastTimer = setTimeout(() => (this.toastMessage = ""), 4000);
  }

  /** Show a refusal message over the view (#283: over-budget fusion #284 / labelmap #286, cache errors). */
  refuse(message: string): void {
    this.refusal = message;
  }

  /** Size guard (#283): does the series fit as a full-resolution volume now? Undefined unless reconstructable. */
  private fitVolume(): VolumeFit | undefined {
    const grid = this.loaded && seriesGrid(this.loaded);
    if (!this.mpr?.ok || !grid || !this.gpu || this.viewportKind === "wsi") return undefined;
    return fitVolume(grid, this.seriesUid, this.gpu, this.budget.open(), { annotate: this.canAnnotate });
  }

  /**
   * Budget entries for opening `next` (#283), reserved in the guard; undefined (with a refusal shown)
   * when it doesn't fit. Re-checked on every add: the series' own earlier volume entries (same ids) are replaced.
   */
  private reserveVolume(next: Extract<ViewLayout, { kind: "volume" }>): BudgetEntry[] | undefined {
    const fit = (this.volumeFit = this.fitVolume());
    if (!fit) return undefined;
    let entries: BudgetEntry[];
    if (next.reduced) entries = volumeEntries(this.seriesUid, seriesGrid(this.loaded!)!, false, next.reduced);
    else if (fit.ok) entries = fit.entries;
    else {
      this.refusal = fit.message;
      return undefined;
    }
    const check = this.budget.reserve(entries);
    if (check.ok) return entries;
    this.refusal = fit.ok ? "Too large for 3D: the budget is full." : fit.message;
    return undefined;
  }

  /** CS3D's cache refused the volume (#283): free its budget entries, say so, back to the stack. */
  private tooLarge(entries: BudgetEntry[]): void {
    entries.forEach((e) => this.budget.release(e.id));
    this.refusal = TOO_LARGE_MESSAGE;
    void this.setLayout({ kind: "stack" });
  }

  /**
   * Switch between the stack and volume layouts (#282). Same volume, other orientations: the view
   * is re-oriented. Stack ↔ volume: the open view is closed and the other opened on new DOM.
   */
  private async setLayout(next: ViewLayout): Promise<void> {
    const { adapter, loaded } = this;
    if (!adapter || !loaded || this.layoutBusy) return;
    if (next.kind === "volume" && (!this.mpr?.ok || this.viewportKind === "wsi")) return;
    const previous = this.layout;
    const previousTool = this.context().activeTool;
    const sameVolume = next.kind === "volume" && previous.kind === "volume" && String(next.reduced) === String(previous.reduced);
    const opensVolume = next.kind === "volume" && !(sameVolume && this.volumeView);
    const entries = opensVolume ? this.reserveVolume(next) : [];
    if (!entries) return;
    this.layoutBusy = true;
    let tooLarge = false;
    try {
      this.layout = next;
      if (next.kind === "volume" && sameVolume && this.volumeView) {
        await this.updateComplete;
        await this.volumeView.setOrientations(next.orientations);
      } else {
        const current = this.controls;
        if (current) adapter.close(current);
        this.view = this.volumeView = undefined;
        this.stack = this.volume = undefined;
        this.viewportKind = next.kind === "stack" ? "stack" : "volume";
        await this.updateComplete;
        if (next.kind === "stack") await this.openStackView(adapter, loaded);
        else {
          const slots = [...this.renderRoot.querySelectorAll<HTMLDivElement>(".vslot")];
          this.volumeView = await adapter.openVolume(
            slots,
            loaded,
            next.orientations,
            () => (this.volume = this.volumeView?.state()),
            (stage) => this.firstRender?.mark(stage),
            { decimation: next.reduced, onTooLarge: () => this.tooLarge(entries) },
          );
        }
        if (this.disposed) return;
      }
      // The labelmap is on the full-resolution grid: not shown in reduced 3D (segment tools are off there).
      if (!(next.kind === "volume" && next.reduced)) await this.segmentation.show(this.controls);
      this.controls?.setTool(this.toolAfterSwitch(previous, previousTool));
      this.stack = this.view?.state();
      this.volume = this.volumeView?.state();
    } catch (e) {
      if (next.kind === "volume" && isTooLargeError(e)) tooLarge = true;
      else this.fail(e);
    } finally {
      this.layoutBusy = false;
    }
    if (tooLarge) this.tooLarge(entries);
  }

  /** Crosshairs when entering three views; else keep the tool if the new layout offers it. */
  private toolAfterSwitch(previous: ViewLayout, tool: string): string {
    const views = (l: ViewLayout) => (l.kind === "volume" ? l.orientations.length : 1);
    if (views(this.layout) === 3 && views(previous) !== 3) return CROSSHAIRS;
    return tools.available(this.toolScope()).some((t) => t.id === tool) ? tool : DEFAULT_TOOL;
  }

  private toolScope(): ToolScope {
    const views = this.layout.kind === "volume" ? this.layout.orientations.length : 1;
    const viewOnly = this.layout.kind === "volume" && !!this.layout.reduced;
    return { viewport: this.viewportKind, canAnnotate: this.canAnnotate, views, viewOnly };
  }

  /** Drag the divider between the big view and the two small ones (25–85%, remembered). */
  private startSplit = (e: PointerEvent): void => {
    const divider = e.currentTarget as HTMLElement;
    const grid = divider.parentElement!;
    divider.setPointerCapture?.(e.pointerId);
    e.preventDefault();
    e.stopPropagation();
    const move = (ev: PointerEvent) => {
      const r = grid.getBoundingClientRect();
      this.split = clampSplit(((ev.clientX - r.left) / r.width) * 100);
      void this.updateComplete.then(() => this.adapter?.resize());
    };
    const up = () => {
      divider.removeEventListener("pointermove", move);
      divider.removeEventListener("pointerup", up);
      divider.removeEventListener("pointercancel", up);
      saveSplit(this.split);
    };
    divider.addEventListener("pointermove", move);
    divider.addEventListener("pointerup", up);
    divider.addEventListener("pointercancel", up);
  };

  /** Series UIDs in view: the volume's layers (base first), else the series shown. */
  private shownUids(): string[] {
    const layers = this.volume?.layers;
    return layers?.length ? layers.map((l) => l.seriesUid) : this.loaded ? [this.loaded.ref.seriesUid] : [];
  }

  private async seriesFor(seriesUid: string): Promise<LoadedSeries | undefined> {
    const known = this.catalog.get(seriesUid);
    if (known) return known;
    try {
      const series = await fetchSeries({ wadoRoot: this.wadoRoot, studyUid: this.studyUid, seriesUid });
      this.catalog.set(seriesUid, series);
      return series;
    } catch (e) {
      this.refuse(`Can't load the series: ${e instanceof Error ? e.message : String(e)}`);
      return undefined;
    }
  }

  private onDragStart = (e: DragEvent): void => {
    const row = (e.target as HTMLElement | null)?.closest?.<HTMLElement>(".ser");
    const uid = row?.dataset.seriesUid;
    if (!uid || !this.controls) return;
    e.dataTransfer?.setData("text/plain", uid);
    if (e.dataTransfer) e.dataTransfer.effectAllowed = "copy";
    this.dragged = uid;
  };

  private onDragEnd = (): void => {
    this.dragged = this.dragOver = undefined;
  };

  private async onDrop(zone: DropZone): Promise<void> {
    const uid = this.dragged;
    this.dragged = this.dragOver = undefined;
    if (!uid || this.fusionBusy || this.layoutBusy) return;
    this.fusionBusy = true;
    this.refusal = "";
    try {
      if (zone === "fuse") await this.fuse(uid);
      else await this.replace(uid);
    } finally {
      this.fusionBusy = false;
    }
  }

  /**
   * Fuse a series into every view (#284): same Frame of Reference, volumes only, within the size
   * guard's budget. From the stack, the base opens in three views first. The overlay is selected.
   */
  private async fuse(uid: string): Promise<void> {
    const { adapter, loaded, gpu } = this;
    if (!adapter || !loaded || !gpu) return;
    const overlay = await this.seriesFor(uid);
    if (!overlay) return;
    const fit = this.volumeFit;
    const why = fuseBlocker({
      base: loaded,
      overlay,
      shown: this.shownUids(),
      reduced: this.layout.kind === "volume" && !!this.layout.reduced,
      baseTooLarge: fit && !fit.ok ? fit.message : undefined,
    });
    if (why) return this.refuse(why);
    // From the stack the base volume is added too: check both before opening anything.
    const budget = overlayBudget(overlay, gpu, this.budget, this.layout.kind === "stack" && fit?.ok ? fit.entries : []);
    if (!budget.ok) return this.refuse(budget.message);
    if (this.layout.kind === "stack") await this.setLayout({ kind: "volume", orientations: threeViews("axial") });
    const view = this.volumeView;
    if (!view) return;
    const reserved = this.budget.reserve(budget.entries);
    if (!reserved.ok) return this.refuse(budgetRefusal("fusion", reserved));
    const { voi, ...display } = layerDisplay(modalityOf(overlay), { base: false, suv: suvStatusFor(overlay) });
    try {
      await view.addLayer(overlay, display, { voi, onTooLarge: () => this.dropOverlay(uid, TOO_LARGE_MESSAGE) });
      view.selectLayer(uid);
    } catch (e) {
      this.budget.releaseSeries(uid);
      this.refuse(isTooLargeError(e) ? TOO_LARGE_MESSAGE : `Can't fuse ${seriesLabel(overlay)}: ${e instanceof Error ? e.message : String(e)}`);
    }
    this.volume = view.state();
  }

  /** Remove an overlay, its cached volume and its budget, optionally saying why. */
  private dropOverlay(uid: string, message?: string): void {
    this.volumeView?.removeLayer(uid);
    this.adapter?.evict(uid);
    this.budget.releaseSeries(uid);
    this.volume = this.volumeView?.state();
    if (message) this.refuse(message);
  }

  /**
   * Show another series instead of everything shown (#284, bottom drop zone): views closed, their
   * budget freed, the series opened as a stack (or slide), then in the previous volume layout when it
   * is reconstructable and fits.
   */
  private async replace(uid: string): Promise<void> {
    const { adapter, gpu } = this;
    if (!adapter || !gpu) return;
    const next = await this.seriesFor(uid);
    if (!next) return;
    const why = replaceBlocker(next, this.shownUids());
    if (why) return this.refuse(why);
    const wsi = isWholeSlide(next);
    if (!wsi) {
      const texture = checkImageTexture(next, gpu);
      if (!texture.ok) return this.refuse(texture.message);
    }
    const wanted = this.layout;
    this.layoutBusy = true;
    try {
      const current = this.controls;
      const old = this.shownUids();
      if (current) adapter.close(current);
      // The replaced series leave CS3D's cache too, so the size guard stops counting them (#283).
      old.forEach((u) => {
        adapter.evict(u);
        this.budget.releaseSeries(u);
      });
      this.view = this.wsiView = this.volumeView = undefined;
      this.stack = this.volume = undefined;
      this.bulkGroups = [];
      this.loaded = next;
      this.seriesUid = uid;
      this.results.hideWhere((c) => baseOf(c) !== uid); // heads of the replaced series go with it (#290)
      this.save.reset(); // Save (#289) starts over on the new base series
      void this.drafts?.check(); // and its drafts (#291) are offered
      this.mpr = isReconstructable(next);
      this.viewportKind = wsi ? "wsi" : "stack";
      this.layout = { kind: "stack" };
      this.volumeFit = this.fitVolume();
      await this.updateComplete;
      await this.openStackView(adapter, next);
      if (this.disposed) return;
      this.view!.setTool(wsi ? WSI_DEFAULT_TOOL : DEFAULT_TOOL);
      this.stack = this.view!.state();
    } catch (e) {
      this.fail(e);
      return;
    } finally {
      this.layoutBusy = false;
    }
    if (wanted.kind === "volume" && !wanted.reduced && this.mpr.ok && this.volumeFit?.ok) {
      await this.setLayout({ kind: "volume", orientations: wanted.orientations });
    }
  }

  private swapIntoMain(slot: number): void {
    if (this.layout.kind !== "volume") return;
    void this.setLayout({ ...this.layout, orientations: swapIntoMain(this.layout.orientations, slot) });
  }

  /** What inspector panels and commands see; see context.ts. */
  private context(): ViewerContext {
    return {
      canAnnotate: this.canAnnotate,
      viewport: this.viewportKind,
      modality: this.selectedLayer()?.modality ?? this.series.find((s) => s.seriesUid === this.loaded?.ref.seriesUid)?.modality ?? "",
      activeTool: (this.volume ?? this.stack)?.activeTool ?? "",
      view: this.controls,
      stack: this.stack,
      stackView: this.view,
      image: this.loaded?.images[this.stack?.imageIndex ?? 0]?.instance,
      selectTool: (id) => void this.selectTool(id),
      applyPreset: (p) => this.applyPreset(p),
      layout: this.layout,
      volume: this.volume,
      mpr: this.mpr,
      setLayout: (layout) => void this.setLayout(layout),
      bulkAnnotationGroups: this.bulkGroups,
      setBulkAnnotationGroupVisible: (uid, visible) => this.wsiView?.setBulkAnnotationGroupVisible(uid, visible),
      budget: this.budget,
      gpu: this.gpu,
      volumeFit: this.volumeFit,
      refuse: (message) => this.refuse(message),
      segmentation: this.segmentation.view?.state(),
      segmentationView: this.segmentation.view,
      ensureSegmentation: () => this.segmentation.ensure(this.controls),
      thresholdLayer: this.thresholdLayer(),
      runThreshold: (range, slices) => this.segmentation.runThreshold(range, slices, this.thresholdLayer().seriesUid),
      thresholdResult: this.segmentation.thresholdResult,
      save: this.save,
      annotationTools: (this.loaded && this.annotations?.toolNames(this.loaded)) || [],
      layers: this.volume?.layers ?? [],
      selectedLayer: this.volume?.selectedLayer,
      selectLayer: (uid) => this.volumeView?.selectLayer(uid),
      setLayerDisplay: (uid, change) => this.volumeView?.setLayerDisplay(uid, change),
      removeLayer: (uid) => this.dropOverlay(uid),
      suv: this.suv,
    };
  }

  private selectedLayer() {
    return this.volume?.layers.find((l) => l.seriesUid === this.volume?.selectedLayer);
  }

  /** Threshold source (#286): the selected layer (#284), else the base series. */
  private thresholdLayer(): { seriesUid: string; modality: string } {
    const l = this.selectedLayer();
    if (l) return { seriesUid: l.seriesUid, modality: l.modality };
    return { seriesUid: this.seriesUid, modality: this.series.find((s) => s.seriesUid === this.seriesUid)?.modality ?? this.series[0]?.modality ?? "" };
  }

  private applyPreset(p: Preset): void {
    const voi = presetVoi(p);
    if (voi) this.controls?.setVoi(voi);
    else this.controls?.resetVoi();
  }

  private onKey = (e: KeyboardEvent): void => {
    if (!this.controls || e.altKey || e.repeat) return;
    const target = e.composedPath()[0];
    if (target instanceof HTMLElement && target.matches("input, select, textarea, [contenteditable]")) return;
    const ctx = this.context();
    const mod = e.ctrlKey || e.metaKey;
    const command = commands.forKey(e.key, mod, ctx);
    if (command) {
      e.preventDefault();
      return command.run(ctx);
    }
    if (mod) return;
    const tool = tools.forKey(e.key, this.toolScope());
    if (tool) return ctx.selectTool(tool.id);
    const preset = presets.forKey(e.key, ctx.modality);
    if (preset) this.applyPreset(preset);
  };

  private overlay() {
    if (!this.stack || this.viewportKind === "wsi") return nothing;
    const { imageIndex, imageCount, voi } = this.stack;
    let window = "";
    if (voi) {
      const { width, center } = voiToWindow(voi);
      window = ` · W ${Math.round(width)} L ${Math.round(center)}`;
    }
    return html`<div class="overlay">Image ${imageIndex + 1} / ${imageCount}${window}</div>`;
  }

  private unit() {
    const unit = this.stack?.unit;
    if (!unit) return nothing;
    return html`<span class="unit" title=${unitTooltip(unit)}>${unit}</span>`;
  }

  /** Burned-in badge (#281): the image may carry identifying text in its pixels. */
  private burnedIn(ctx: ViewerContext) {
    if (!burnedInWarning(ctx.image)) return nothing;
    return html`<span class="burned-in" role="note" title="The image may have identifying text burned into its pixels (BurnedInAnnotation is YES, or missing on a secondary capture or ultrasound). Pixels aren't scrubbed.">⚠ Burned-in annotation</span>`;
  }

  render() {
    const ctx = this.context();
    const rail = tools.rail(this.toolScope());
    const shown = this.shownUids();
    const views =
      this.layout.kind === "volume"
        ? volumeGrid({
            orientations: this.layout.orientations,
            split: this.split,
            state: this.volume,
            swap: (slot) => this.swapIntoMain(slot),
            startSplit: this.startSplit,
          })
        : html`<div class="viewport" tabindex="-1"></div>
            ${this.overlay()} ${this.unit()}`;
    return html`<div class="chrome">
      <div style="display: contents" @dragstart=${this.onDragStart} @dragend=${this.onDragEnd}>
        ${seriesList(
          this.series.map((s) => ({ ...s, shown: shown.includes(s.seriesUid) })),
          {
            top: lockRow(this.results),
            nested: (uid) => resultRows(this.results, uid, (u) => this.series.find((s) => s.seriesUid === u)?.modality ?? "", this.canAnnotate),
            footer: resultsFooter(this.results, this.canAnnotate),
          },
        )}
      </div>
      ${toolRail(rail, ctx.activeTool, ctx.selectTool)}
      <div class="stage" @pointerdown=${() => this.focus()} @contextmenu=${(e: Event) => e.preventDefault()}>
        ${views} ${this.burnedIn(ctx)} ${sizeBanner(this.volumeFit, this.layout)} ${resultChips(this.results)}
        ${refusalMessage(this.refusal, () => (this.refusal = ""))}
        ${this.drafts
          ? draftBanner(this.drafts.pending, this.drafts.error, (kind) => void this.drafts?.restore(kind), (kind) => void this.drafts?.discard(kind))
          : nothing}
        ${conflictDialog(this.save.conflict, !!this.save.saving, (choice) => void this.save.resolve(choice), () => this.save.dismiss())}
        ${resultsConfirm(this.results)}
        ${toast(this.toastMessage)}
        ${this.dragged
          ? dropZones({
              width: this.layout.kind === "volume" && this.layout.orientations.length === 3 ? this.split : 100,
              over: this.dragOver,
              label: this.series.find((s) => s.seriesUid === this.dragged)?.modality ?? "",
              onOver: (zone) => (this.dragOver = zone),
              onDrop: (zone) => void this.onDrop(zone),
            })
          : nothing}
        ${this.error ? html`<div role="alert">${this.error}</div>` : nothing}
      </div>
      <aside class="inspector" aria-label="Inspector">${inspector.panels().map((p) => p.render(ctx))}</aside>
    </div>`;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "mires-viewer": MiresViewer;
  }
}
