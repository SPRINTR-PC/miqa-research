// Window presets (spec: CT Soft tissue … Mediastinum + DICOM default, PET SUV 0–5 / 0–10),
// keys 0–8. Pure. Other tickets can add presets from their own module with `presets.register`.
import type { VoiRange } from "../adapter/adapter.ts";

export interface Preset {
  id: string;
  label: string;
  /** Digit shortcut. */
  key: string;
  /** Modalities it fits; omitted = every modality. */
  modalities?: readonly string[];
  /** CT-style window in modality units (HU). */
  window?: { width: number; center: number };
  /** Range in display units (PET: SUV). */
  range?: VoiRange;
}

/** Linear window → VOI range (DICOM PS3.3 C.11.2.1.2, as CS3D's toLowHighRange). */
export function windowToVoi(width: number, center: number): VoiRange {
  return { lower: center - 0.5 - (width - 1) / 2, upper: center - 0.5 + (width - 1) / 2 };
}

/** Inverse of windowToVoi. */
export function voiToWindow({ lower, upper }: VoiRange): { width: number; center: number } {
  return { width: upper - lower + 1, center: (upper + lower + 1) / 2 };
}

/** The VOI range a preset sets, or undefined for "back to the image's own window". */
export function presetVoi(p: Preset): VoiRange | undefined {
  if (p.range) return { ...p.range };
  if (p.window) return windowToVoi(p.window.width, p.window.center);
  return undefined;
}

export class PresetRegistry {
  private readonly all: Preset[] = [];

  register(p: Preset): void {
    const clash = this.all.find(
      (q) => q.id === p.id || (q.key === p.key && overlaps(q.modalities, p.modalities)),
    );
    if (clash) throw new Error(`Preset ${p.id} clashes with ${clash.id}`);
    this.all.push(p);
  }

  forModality(modality: string): Preset[] {
    return this.all.filter((p) => !p.modalities || p.modalities.includes(modality));
  }

  forKey(key: string, modality: string): Preset | undefined {
    return this.forModality(modality).find((p) => p.key === key);
  }
}

function overlaps(a?: readonly string[], b?: readonly string[]): boolean {
  if (!a || !b) return true;
  return a.some((m) => b.includes(m));
}

export const presets = new PresetRegistry();

const CT = ["CT"];
const PT = ["PT"];
[
  { id: "dicom", label: "DICOM default", key: "0" },
  { id: "soft", label: "Soft tissue", key: "1", modalities: CT, window: { width: 400, center: 40 } },
  { id: "lung", label: "Lung", key: "2", modalities: CT, window: { width: 1500, center: -600 } },
  { id: "bone", label: "Bone", key: "3", modalities: CT, window: { width: 2500, center: 480 } },
  { id: "brain", label: "Brain", key: "4", modalities: CT, window: { width: 80, center: 40 } },
  { id: "liver", label: "Liver", key: "5", modalities: CT, window: { width: 150, center: 90 } },
  { id: "mediastinum", label: "Mediastinum", key: "6", modalities: CT, window: { width: 350, center: 50 } },
  { id: "suv5", label: "SUV 0–5", key: "7", modalities: PT, range: { lower: 0, upper: 5 } },
  { id: "suv10", label: "SUV 0–10", key: "8", modalities: PT, range: { lower: 0, upper: 10 } },
].forEach((p) => presets.register(p));
