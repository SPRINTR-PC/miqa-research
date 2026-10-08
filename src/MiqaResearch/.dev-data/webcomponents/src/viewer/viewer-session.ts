// Viewer Session (#288): one id per viewer open (page load), sent on every request the viewer makes.
// The server scopes a Blinding Reveal to it, so a reveal ends on reload, in other tabs and outside the viewer.

export const VIEWER_SESSION_HEADER = "X-Mires-Viewer-Session";

function newId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const hex = Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export const viewerSessionId = newId();

/** `headers` plus the Viewer Session header. */
export function viewerHeaders(headers: Record<string, string> = {}): Record<string, string> {
  return { ...headers, [VIEWER_SESSION_HEADER]: viewerSessionId };
}
