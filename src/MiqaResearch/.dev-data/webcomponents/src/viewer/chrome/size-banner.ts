// Size guard chrome (#283): the banner over the view for a series too big for full-resolution 3D
// (stack fallback, or reduced 3D), and the dismissible refusal message (fusion #284, labelmap #286,
// CS3D cache errors).
import { css, html, nothing } from "lit";

import type { ViewLayout } from "../layout.ts";
import type { VolumeFit } from "../size-guard.ts";

export const sizeBannerStyles = css`
  .size-banner, .refusal { position: absolute; z-index: 6; left: 50%; transform: translateX(-50%); max-width: 80%;
    padding: 4px 10px; border-radius: 4px; font-size: 12px; line-height: 1.4; }
  .size-banner { top: 8px; background: #3b2a12; border: 1px solid #8a5a14; color: #ffcf7a; pointer-events: none; }
  .refusal { top: 44px; display: flex; gap: 8px; align-items: center; background: #3b1616; border: 1px solid #8a2a2a; color: #ffb0b0; }
  .refusal button { padding: 0 6px; }
`;

export function sizeBanner(fit: VolumeFit | undefined, layout: ViewLayout) {
  if (!fit || fit.ok) return nothing;
  if (layout.kind === "volume" && layout.reduced) {
    const [i, , k] = layout.reduced;
    const grid = [i > 1 ? `1/${i} resolution in-plane` : "", k > 1 ? `every ${ordinal(k)} slice` : ""].filter(Boolean).join(", ");
    return html`<div class="size-banner" role="status">
      Reduced 3D (view only)${grid ? html`: ${grid}` : nothing}. Measurements, annotations and segmentation are off; Stack shows full resolution.
    </div>`;
  }
  if (layout.kind !== "stack") return nothing;
  return html`<div class="size-banner" role="status">
    ${fit.message} Showing the full-resolution stack; MPR, crosshairs and fusion are off.
  </div>`;
}

function ordinal(n: number): string {
  const suffix = n % 100 >= 11 && n % 100 <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th";
  return `${n}${suffix}`;
}

export function refusalMessage(message: string, dismiss: () => void) {
  if (!message) return nothing;
  return html`<div class="refusal" role="alert">
    <span>${message}</span><button title="Dismiss" @click=${dismiss}>×</button>
  </div>`;
}
