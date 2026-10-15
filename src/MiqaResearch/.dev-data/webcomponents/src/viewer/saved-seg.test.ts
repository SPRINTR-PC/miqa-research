// #290 saved SEG frames: our /frames multipart/related body split into frame bytes.
import { describe, expect, it } from "vitest";

import { parseMultipartRelated } from "./saved-seg.ts";

const bytes = (...parts: (string | number[])[]) =>
  new Uint8Array(parts.flatMap((p) => (typeof p === "string" ? [...new TextEncoder().encode(p)] : p)));

describe("parseMultipartRelated", () => {
  it("returns each part's body in order, binary bytes intact (CR LF and dashes inside included)", () => {
    const head = "Content-Type: application/octet-stream; transfer-syntax=1.2.840.10008.1.2.1\r\n\r\n";
    const body = bytes("--abc\r\n", head, [0x0d, 0x0a, 0x2d, 0x2d, 0xff], "\r\n--abc\r\n", head, [0x00, 0x01], "\r\n--abc--\r\n");

    const parts = parseMultipartRelated(body, 'multipart/related; type="application/octet-stream"; boundary=abc');

    expect(parts.map((p) => [...p])).toEqual([[0x0d, 0x0a, 0x2d, 0x2d, 0xff], [0x00, 0x01]]);
  });

  it("reads a quoted boundary", () => {
    const body = bytes('--x y\r\nContent-Type: a\r\n\r\n', [9], "\r\n--x y--\r\n");
    expect(parseMultipartRelated(body, 'multipart/related; boundary="x y"').map((p) => [...p])).toEqual([[9]]);
  });

  it("refuses a body without a boundary", () => {
    expect(() => parseMultipartRelated(new Uint8Array(), "application/octet-stream")).toThrow("boundary");
  });
});
