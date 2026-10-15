import { type Mock, afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { type FirstRenderBeacon, FirstRenderReport, beaconPayload, isHttp11Frames } from "./first-render.ts";
import type { LoadedSeries } from "./series.ts";

const SERIES_URL = "/api/v1/dicom/studies/2.25.100/series/2.25.200";

function series(slices: number, transferSyntax = "1.2.840.10008.1.2.1"): LoadedSeries {
  const instance = { "00083002": { vr: "UI", Value: [transferSyntax] }, "00080018": { vr: "UI", Value: ["2.25.9"] } };
  return {
    ref: { wadoRoot: "/api/v1/dicom", studyUid: "2.25.100", seriesUid: "2.25.200" },
    images: Array.from({ length: slices }, (_, i) => ({ imageId: `wadors:${SERIES_URL}/instances/2.25.9/frames/${i + 1}`, instance })),
  };
}

function frameEntry(n: number, protocol = "h2", encodedBodySize = 1000) {
  return { name: `https://x.test${SERIES_URL}/instances/2.25.9/frames/${n}`, nextHopProtocol: protocol, encodedBodySize };
}

describe("beaconPayload", () => {
  it("keeps only timings, series size and transfer syntax", () => {
    const payload = beaconPayload({
      first_image_ms: 412.5,
      slices: 500,
      bytes: 1024,
      transfer_syntax: "1.2.840.10008.1.2.4.70",
      study_uid: "2.25.100",
      series_uid: "2.25.200",
      participant: "P-001",
      url: SERIES_URL,
    } as never);

    expect(payload).toEqual({ first_image_ms: 412.5, slices: 500, bytes: 1024, transfer_syntax: "1.2.840.10008.1.2.4.70" });
  });

  it("drops stages that weren't reached", () => {
    expect(beaconPayload({ first_image_ms: 10, interleaved_ms: undefined, slices: 3 })).toEqual({ first_image_ms: 10, slices: 3 });
  });
});

describe("isHttp11Frames", () => {
  it("flags /frames fetched over HTTP/1.1 only", () => {
    expect(isHttp11Frames(frameEntry(1, "http/1.1"))).toBe(true);
    expect(isHttp11Frames(frameEntry(1, "h2"))).toBe(false);
    expect(isHttp11Frames({ name: `${SERIES_URL}/metadata`, nextHopProtocol: "http/1.1" })).toBe(false);
  });
});

describe("FirstRenderReport", () => {
  let send: Mock<(url: string, body: FirstRenderBeacon) => void>;
  let warn: Mock<(message: string) => void>;
  let now: number;

  beforeEach(() => {
    send = vi.fn();
    warn = vi.fn();
    now = 1000;
    performance.clearMarks();
  });

  afterEach(() => vi.restoreAllMocks());

  function report() {
    const perf = { mark: (name: string) => ({ name, startTime: now }) } as unknown as Performance;
    return new FirstRenderReport({ send, warn, perf, observe: false });
  }

  it("sets a performance.mark per stage and sends their times since open once", () => {
    const r = new FirstRenderReport({ send, warn, observe: false });
    r.series(series(3));
    r.mark("first-image");

    expect(performance.getEntriesByType("mark").map((m) => m.name)).toEqual(["mires-viewer:open", "mires-viewer:first-image"]);
    r.send();
    r.send();
    expect(send).toHaveBeenCalledOnce();
  });

  it("reports timings since open, slice count, frame bytes and transfer syntax, never UIDs", () => {
    const r = report();
    r.series(series(500, "1.2.840.10008.1.2.4.70"));
    now = 1412.5;
    r.mark("first-image");
    r.resource(frameEntry(1, "h2", 600));
    r.resource(frameEntry(2, "h2", 400));
    r.resource({ name: `${SERIES_URL}/metadata`, nextHopProtocol: "h2", encodedBodySize: 99999 });
    now = 2530;
    r.mark("interleaved");
    now = 7120.25;
    r.mark("volume-loaded");

    expect(send).toHaveBeenCalledOnce();
    const [url, body] = send.mock.calls[0];
    expect(url).toBe("/api/v1/viewer/first-render");
    expect(body).toEqual({
      first_image_ms: 412.5,
      interleaved_ms: 1530,
      volume_loaded_ms: 6120.25,
      slices: 500,
      bytes: 1000,
      transfer_syntax: "1.2.840.10008.1.2.4.70",
    });
    expect(JSON.stringify(body)).not.toContain("2.25.");
  });

  it("sends on dispose when the volume stages never come (stack view)", () => {
    const r = report();
    r.series(series(16));
    now = 1300;
    r.mark("first-image");
    expect(send).not.toHaveBeenCalled();

    r.dispose();

    expect(send).toHaveBeenCalledWith("/api/v1/viewer/first-render", {
      first_image_ms: 300,
      slices: 16,
      transfer_syntax: "1.2.840.10008.1.2.1",
    });
  });

  it("sends nothing when no image was ever shown", () => {
    const r = report();
    r.series(series(16));
    r.dispose();
    expect(send).not.toHaveBeenCalled();
  });

  it("warns once on the console when /frames come over HTTP/1.1", () => {
    const r = report();
    r.resource(frameEntry(1, "http/1.1"));
    r.resource(frameEntry(2, "http/1.1"));
    r.resource(frameEntry(3, "h2"));

    expect(warn).toHaveBeenCalledOnce();
    expect(warn.mock.calls[0][0]).toMatch(/HTTP\/1\.1/);
  });
});
