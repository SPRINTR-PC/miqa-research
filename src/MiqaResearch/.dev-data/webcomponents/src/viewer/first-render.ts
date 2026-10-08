// First-render measurement (spec #271 "First render", #293).
// `performance.mark`s for open, first image, interleaved stage done and volume loaded; one
// beacon per open series to /api/v1/viewer/first-render (→ OTLP telemetry) with timings since
// open, series size and transfer syntax only: never UIDs, URLs or participant data.
// Also warns on the console when /frames come over HTTP/1.1 (the edge should speak HTTP/2).
// No CS3D import. The element creates one report per open; volume stages are marked by the
// volume view (#282) through the element.
import { type LoadedSeries, seriesUrl } from "./series.ts";

export type FirstRenderStage = "first-image" | "interleaved" | "volume-loaded";

/** The beacon body. The server's schema forbids any other field (422). */
export interface FirstRenderBeacon {
  first_image_ms?: number;
  interleaved_ms?: number;
  volume_loaded_ms?: number;
  slices?: number;
  /** Encoded body bytes of the series' /frames responses seen before the beacon. */
  bytes?: number;
  transfer_syntax?: string;
}

const ALLOWED: readonly (keyof FirstRenderBeacon)[] = [
  "first_image_ms",
  "interleaved_ms",
  "volume_loaded_ms",
  "slices",
  "bytes",
  "transfer_syntax",
];

const STAGE_FIELD: Record<FirstRenderStage, keyof FirstRenderBeacon> = {
  "first-image": "first_image_ms",
  interleaved: "interleaved_ms",
  "volume-loaded": "volume_loaded_ms",
};

export const BEACON_URL = "/api/v1/viewer/first-render";
const MARK_PREFIX = "mires-viewer:";
const AVAILABLE_TRANSFER_SYNTAX = "00083002";

/** Copy only the allowed beacon fields; drops anything else and unset stages. */
export function beaconPayload(fields: FirstRenderBeacon): FirstRenderBeacon {
  const out: Record<string, unknown> = {};
  for (const key of ALLOWED) if (fields[key] !== undefined) out[key] = fields[key];
  return out as FirstRenderBeacon;
}

type ResourceEntry = Pick<PerformanceResourceTiming, "name" | "nextHopProtocol"> & { encodedBodySize?: number };

const isFrames = (entry: ResourceEntry) => /\/frames\/[0-9,]+$/.test(new URL(entry.name, "http://x").pathname);

/** Whether a resource timing entry is a WADO `/frames` request served over HTTP/1.1. */
export function isHttp11Frames(entry: ResourceEntry): boolean {
  return isFrames(entry) && entry.nextHopProtocol === "http/1.1";
}

/** Django's CSRF token from the `csrftoken` cookie (the host page sets it), sent as `X-CSRFToken`. */
export function csrfToken(): string {
  return document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] ?? "";
}

/** POST with `keepalive` (sendBeacon can't send the CSRF header Django's session auth needs). */
function postBeacon(url: string, body: FirstRenderBeacon): void {
  void fetch(url, {
    method: "POST",
    keepalive: true,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
    body: JSON.stringify(body),
  }).catch(() => undefined);
}

export interface FirstRenderOptions {
  beaconUrl?: string;
  send?: (url: string, body: FirstRenderBeacon) => void;
  warn?: (message: string) => void;
  perf?: Performance;
  /** Observe resource timing for /frames (bytes, HTTP/1.1 check). Default true. */
  observe?: boolean;
}

/** One open series' first-render marks. Created at open; sends once (volume loaded or dispose). */
export class FirstRenderReport {
  private readonly beaconUrl: string;
  private readonly sendBeacon: (url: string, body: FirstRenderBeacon) => void;
  private readonly warn: (message: string) => void;
  private readonly perf: Performance;
  private readonly openedAt: number;
  private readonly fields: FirstRenderBeacon = {};
  private framesPrefix: string | undefined;
  private observer: PerformanceObserver | undefined;
  private warned = false;
  private sent = false;
  private readonly onPageHide = () => this.send();

  constructor(options: FirstRenderOptions = {}) {
    this.beaconUrl = options.beaconUrl ?? BEACON_URL;
    this.sendBeacon = options.send ?? postBeacon;
    this.warn = options.warn ?? ((m) => console.warn(m));
    this.perf = options.perf ?? performance;
    this.openedAt = this.perf.mark(`${MARK_PREFIX}open`).startTime;
    if (options.observe !== false && typeof PerformanceObserver !== "undefined") {
      // An observer, not getEntriesByType: the resource buffer (250 entries) is smaller than a CT.
      this.observer = new PerformanceObserver((list) =>
        list.getEntries().forEach((e) => this.resource(e as PerformanceResourceTiming)),
      );
      this.observer.observe({ type: "resource" });
      addEventListener("pagehide", this.onPageHide);
    }
  }

  /** Series size and transfer syntax from the loaded `/metadata`. */
  series(series: LoadedSeries): void {
    this.framesPrefix = `${seriesUrl(series.ref)}/instances/`;
    this.fields.slices = series.images.length;
    const syntax = series.images[0]?.instance[AVAILABLE_TRANSFER_SYNTAX]?.Value?.[0];
    if (typeof syntax === "string") this.fields.transfer_syntax = syntax;
  }

  mark(stage: FirstRenderStage): void {
    const field = STAGE_FIELD[stage];
    if (this.sent || this.fields[field] !== undefined) return;
    const at = this.perf.mark(`${MARK_PREFIX}${stage}`).startTime;
    (this.fields as Record<string, unknown>)[field] = at - this.openedAt;
    if (stage === "volume-loaded") this.send();
  }

  /** Feed one resource timing entry (from the observer, or a test). */
  resource(entry: ResourceEntry): void {
    if (!isFrames(entry)) return;
    if (!this.warned && isHttp11Frames(entry)) {
      this.warned = true;
      this.warn(
        "mires-viewer: /frames are served over HTTP/1.1. Terminate TLS + HTTP/2 at the browser-facing edge " +
          "(technical manual, deployment requirements); first render is much slower without it.",
      );
    }
    if (this.framesPrefix && new URL(entry.name, "http://x").pathname.startsWith(this.framesPrefix)) {
      this.fields.bytes = (this.fields.bytes ?? 0) + (entry.encodedBodySize ?? 0);
    }
  }

  /** Send the beacon once, if an image was shown. */
  send(): void {
    if (this.sent || this.fields.first_image_ms === undefined) return;
    this.sent = true;
    this.sendBeacon(this.beaconUrl, beaconPayload(this.fields));
  }

  dispose(): void {
    this.send();
    this.observer?.disconnect();
    removeEventListener("pagehide", this.onPageHide);
  }
}
