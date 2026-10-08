import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchSeries, SeriesLoadError } from "./series.ts";

const REF = { wadoRoot: "/api/v1/dicom", studyUid: "2.25.1", seriesUid: "2.25.2" };
const FRAMES = "/api/v1/dicom/studies/2.25.1/series/2.25.2/instances";

/** Minimal DICOM JSON instance (PS3.18 F.2): SOPInstanceUID, InstanceNumber, optional geometry/frames. */
function instance(sop: string, n: number, extra: Record<string, unknown> = {}) {
  return {
    "00080018": { vr: "UI", Value: [sop] },
    "00200013": { vr: "IS", Value: [n] },
    ...extra,
  };
}
const ipp = (z: number) => ({ "00200032": { vr: "DS", Value: [0, 0, z] } });
const AXIAL_IOP = { "00200037": { vr: "DS", Value: [1, 0, 0, 0, 1, 0] } };

function respondWith(body: unknown, status = 200) {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

describe("fetchSeries", () => {
  it("asks for the series /metadata as DICOM JSON with the session cookie and the Viewer Session id", async () => {
    const fetchMock = respondWith([instance("2.25.10", 1)]);

    await fetchSeries(REF);

    expect(fetchMock).toHaveBeenCalledWith("/api/v1/dicom/studies/2.25.1/series/2.25.2/metadata", {
      credentials: "same-origin",
      headers: { Accept: "application/dicom+json", "X-Mires-Viewer-Session": expect.stringMatching(/^[0-9a-f-]{36}$/) },
    });
  });

  it("builds one wadors frame imageId per instance, ordered along the slice normal", async () => {
    respondWith([
      instance("2.25.12", 1, { ...AXIAL_IOP, ...ipp(30) }),
      instance("2.25.10", 3, { ...AXIAL_IOP, ...ipp(10) }),
      instance("2.25.11", 2, { ...AXIAL_IOP, ...ipp(20) }),
    ]);

    const { images } = await fetchSeries(REF);

    expect(images.map((i) => i.imageId)).toEqual([
      `wadors:${FRAMES}/2.25.10/frames/1`,
      `wadors:${FRAMES}/2.25.11/frames/1`,
      `wadors:${FRAMES}/2.25.12/frames/1`,
    ]);
  });

  it("falls back to InstanceNumber when geometry is missing", async () => {
    respondWith([instance("2.25.b", 2), instance("2.25.a", 1)]);

    const { images } = await fetchSeries(REF);

    expect(images.map((i) => i.imageId)).toEqual([
      `wadors:${FRAMES}/2.25.a/frames/1`,
      `wadors:${FRAMES}/2.25.b/frames/1`,
    ]);
  });

  it("gives every frame of a multi-frame instance its own imageId, sharing the instance metadata", async () => {
    const multi = instance("2.25.m", 1, { "00280008": { vr: "IS", Value: [3] } });
    respondWith([multi]);

    const { images } = await fetchSeries(REF);

    expect(images.map((i) => i.imageId)).toEqual([1, 2, 3].map((f) => `wadors:${FRAMES}/2.25.m/frames/${f}`));
    expect(images.map((i) => i.instance)).toEqual([multi, multi, multi]);
  });

  it("fails with the HTTP status when the series isn't visible", async () => {
    respondWith({ detail: "Not Found" }, 404);

    await expect(fetchSeries(REF)).rejects.toEqual(new SeriesLoadError(404));
  });

  it("fails when the series has no instances", async () => {
    respondWith([]);

    await expect(fetchSeries(REF)).rejects.toBeInstanceOf(SeriesLoadError);
  });
});
