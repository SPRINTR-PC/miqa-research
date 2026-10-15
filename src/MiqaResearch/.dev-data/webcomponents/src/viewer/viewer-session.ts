// Viewer Session (#288): one id per viewer open (page load), sent on every request the viewer makes.
// The server scopes a Blinding Reveal to it, so a reveal ends on reload, in other tabs and outside the viewer.
// The viewer page (#279) makes the id itself and audits the open under it; the element adopts it.

export const VIEWER_SESSION_HEADER = "X-Mires-Viewer-Session";

function newId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const hex = Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

let viewerSessionId = newId();

/** Adopt the Viewer Session id the page made for this open (cut to 64 characters, as the server reads it). */
export function adoptViewerSession(id: string): void {
  if (id) viewerSessionId = id.slice(0, 64);
}

/** `headers` plus the Viewer Session header. */
export function viewerHeaders(headers: Record<string, string> = {}): Record<string, string> {
  return { ...headers, [VIEWER_SESSION_HEADER]: viewerSessionId };
}
