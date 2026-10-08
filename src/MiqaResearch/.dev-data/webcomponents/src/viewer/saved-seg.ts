// A saved SEG for showing (#290): sessions get 403 on raw DICOM bytes, so the SEG comes as its sanitized
// `/metadata` (DICOM JSON) plus its frames from `/frames` (multipart/related, BINARY frames still bit-packed).
// The adapter turns them into a labelmap (adapter/cornerstone/segmentation.ts). Pure fetch, no CS3D.
import { seriesUrl, type DicomJsonInstance, type SeriesRef } from "./series.ts";

/** A SEG instance's header and its frames' pixel bytes (frame n at index n − 1). */
export interface SavedSegmentation {
  instance: DicomJsonInstance;
  frames: Uint8Array[];
}

const SOP_INSTANCE_UID = "00080018";
const NUMBER_OF_FRAMES = "00280008";
const FRAMES_ACCEPT = 'multipart/related; type="application/octet-stream"; transfer-syntax=*';

/** Fetch the (single-instance) SEG series `ref`: its `/metadata`, then every frame in one `/frames` request. */
export async function fetchSavedSegmentation(ref: SeriesRef): Promise<SavedSegmentation> {
  const url = seriesUrl(ref);
  const meta = await fetch(`${url}/metadata`, { credentials: "same-origin", headers: { Accept: "application/dicom+json" } });
  if (!meta.ok) throw new Error(`SEG metadata: HTTP ${meta.status}`);
  const [instance] = (await meta.json()) as DicomJsonInstance[];
  if (!instance) throw new Error("the SEG has no instance");
  const sop = String(instance[SOP_INSTANCE_UID]?.Value?.[0] ?? "");
  const count = Number(instance[NUMBER_OF_FRAMES]?.Value?.[0] ?? 1);
  const list = Array.from({ length: count }, (_, i) => i + 1).join(",");
  const response = await fetch(`${url}/instances/${sop}/frames/${list}`, { credentials: "same-origin", headers: { Accept: FRAMES_ACCEPT } });
  if (!response.ok) throw new Error(`SEG frames: HTTP ${response.status}`);
  const frames = parseMultipartRelated(new Uint8Array(await response.arrayBuffer()), response.headers.get("Content-Type") ?? "");
  if (frames.length !== count) throw new Error(`the SEG has ${count} frames, ${frames.length} were served`);
  return { instance, frames };
}

/** The parts' bodies of a multipart/related body (PS3.18 8.7.3.1), in order. */
export function parseMultipartRelated(body: Uint8Array, contentType: string): Uint8Array[] {
  const boundary = contentType.match(/boundary="?([^";]+)"?/i)?.[1];
  if (!boundary) throw new Error("no multipart boundary");
  const delimiter = new TextEncoder().encode(`--${boundary}`);
  const parts: Uint8Array[] = [];
  let at = indexOf(body, delimiter, 0);
  while (at >= 0) {
    const afterDelimiter = at + delimiter.length;
    if (body[afterDelimiter] === 0x2d && body[afterDelimiter + 1] === 0x2d) break; // closing "--"
    const headersEnd = indexOf(body, CRLF2, afterDelimiter);
    if (headersEnd < 0) break;
    const next = indexOf(body, delimiter, headersEnd + 4);
    if (next < 0) break;
    // The part's body ends with the CRLF before the next delimiter.
    const end = body[next - 2] === 0x0d && body[next - 1] === 0x0a ? next - 2 : next;
    parts.push(body.slice(headersEnd + 4, end));
    at = next;
  }
  return parts;
}

const CRLF2 = new Uint8Array([0x0d, 0x0a, 0x0d, 0x0a]);

function indexOf(haystack: Uint8Array, needle: Uint8Array, from: number): number {
  outer: for (let i = from; i <= haystack.length - needle.length; i++) {
    for (let j = 0; j < needle.length; j++) if (haystack[i + j] !== needle[j]) continue outer;
    return i;
  }
  return -1;
}
