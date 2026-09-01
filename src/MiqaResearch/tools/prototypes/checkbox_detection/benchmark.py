"""
PROTOTYPE — throwaway code for issue #15 (checkbox/radio detection on CPU).

Run: python tools/prototypes/checkbox_detection/benchmark.py   (from the repo root)

Renders each of the 10 real fixture scans (tests/example_data/prom_data/prom_samples),
crops every in-scope candidate box (see boxes.py), scores each crop with all three
detectors in detectors.py, compares against ground_truth.json, and reports
precision/recall/F1 per detector (overall and broken out by field type). Writes
results.json and results.md next to this file.

Deliberately lives under tools/ (not MiqaResearch/tasks/) so it never needs Django
settings/app registry — MiqaResearch/tasks/__init__.py eagerly imports Django models,
which would force a full Django bootstrap just to run a throwaway CV benchmark.

No Django, no test framework, no error handling beyond what's needed to get through
the 10 real files without crashing. Throwaway.
"""

import json
from pathlib import Path

import cv2
import numpy as np
import pymupdf

import boxes as B
from detectors import DETECTORS

REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLES_DIR = REPO_ROOT / "tests" / "example_data" / "prom_data" / "prom_samples"
OUT_DIR = Path(__file__).resolve().parent
DPI = 200

# sample_09's scan.pdf has physical pages 2 and 3 (0-indexed) swapped relative to
# every other sample (manifest.json calls this out explicitly).
SWAPPED_PAGE_SAMPLES = {"sample_09": {2: 3, 3: 2}}


def render_pages(pdf_path):
    doc = pymupdf.open(pdf_path)
    pages = []
    for page in doc:
        pix = page.get_pixmap(dpi=DPI)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        if pix.n == 4:
            img = cv2.cvtColor(img, cv2.COLOR_RGBA2GRAY)
        elif pix.n == 3:
            img = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        pages.append(img)
    return pages


def normalize_page_size(page_img, page_index):
    target_w, target_h = B.CANONICAL_PAGE_SIZE[page_index]
    if page_img.shape[1] == target_w and page_img.shape[0] == target_h:
        return page_img
    return cv2.resize(page_img, (target_w, target_h))


def get_logical_page(pages, sample_id, logical_index):
    real_index = SWAPPED_PAGE_SAMPLES.get(sample_id, {}).get(logical_index, logical_index)
    return normalize_page_size(pages[real_index], logical_index)


def crop_box(page_img, x, y, w, h, pad=4):
    h_img, w_img = page_img.shape
    x0 = max(0, x - pad)
    y0 = max(0, y - pad)
    x1 = min(w_img, x + w + pad)
    y1 = min(h_img, y + h + pad)
    return page_img[y0:y1, x0:x1]


def load_ground_truth(sample_id):
    gt_path = SAMPLES_DIR / sample_id / "ground_truth.json"
    data = json.load(open(gt_path))
    return {entry["fieldId"]: entry["value"] for entry in data["data"]}


def ground_truth_marked(field_id, field_type, option_key, gt):
    """Returns True/False, or None if the field is absent from ground truth
    (respondent left it entirely blank) -- excluded from the eval, since we
    can't distinguish 'a confident unmarked box' from 'no attempt made'."""
    if field_id not in gt:
        return None
    value = gt[field_id]
    if field_type == "ranged-radio":
        return str(value) == option_key
    if field_type == "checkbox":
        return option_key in (value or [])
    if field_type == "radio":
        return option_key == value
    raise ValueError(field_type)


def collect_samples():
    for sample_dir in sorted(SAMPLES_DIR.iterdir()):
        if not sample_dir.is_dir():
            continue
        yield sample_dir.name


def main():
    records = []  # each: dict(sample, field_id, field_type, option_key, label, scores={})

    for sample_id in collect_samples():
        pdf_path = SAMPLES_DIR / sample_id / "scan.pdf"
        pages = render_pages(pdf_path)
        gt = load_ground_truth(sample_id)

        for field_id, field_type, option_key, page_index, x, y, w, h in B.all_candidate_boxes():
            label = ground_truth_marked(field_id, field_type, option_key, gt)
            if label is None:
                continue
            page_img = get_logical_page(pages, sample_id, page_index)
            crop = crop_box(page_img, x, y, w, h)
            scores = {name: fn(crop) for name, fn in DETECTORS.items()}
            records.append(
                {
                    "sample": sample_id,
                    "field_id": field_id,
                    "field_type": field_type,
                    "option_key": option_key,
                    "label": label,
                    "scores": scores,
                }
            )
        print(f"{sample_id}: {len(records)} candidate-box records so far")

    json.dump(records, open(OUT_DIR / "raw_scores.json", "w"), indent=1)

    field_group = {
        "ranged-radio-grid": lambda r: r["field_type"] == "ranged-radio" and r["field_id"] in B.RANGED_RADIO_ROW_Y,
        "circle-scale": lambda r: r["field_type"] == "ranged-radio" and r["field_id"] in B.CIRCLE_SCALE_ROW_Y,
        "checkbox": lambda r: r["field_type"] == "checkbox",
        "radio": lambda r: r["field_type"] == "radio",
    }

    report = {}
    for method in DETECTORS:
        scores = [r["scores"][method] for r in records]
        labels = [r["label"] for r in records]
        threshold, best_f1 = best_threshold(scores, labels)
        preds = [s >= threshold for s in scores]

        report[method] = {
            "threshold": threshold,
            "overall": prf1(labels, preds),
            "by_field_group": {},
            "by_field_group_own_threshold": {},
        }
        for group_name, pred_fn in field_group.items():
            idx = [i for i, r in enumerate(records) if pred_fn(r)]
            if not idx:
                continue
            g_labels = [labels[i] for i in idx]
            g_preds = [preds[i] for i in idx]
            report[method]["by_field_group"][group_name] = prf1(g_labels, g_preds)

            # Same detector, but threshold tuned separately per field-type class
            # instead of reusing the single global threshold above.
            g_scores = [scores[i] for i in idx]
            g_threshold, _ = best_threshold(g_scores, g_labels)
            g_own_preds = [s >= g_threshold for s in g_scores]
            report[method]["by_field_group_own_threshold"][group_name] = {
                "threshold": g_threshold,
                "prf1": prf1(g_labels, g_own_preds),
            }

    json.dump(report, open(OUT_DIR / "results.json", "w"), indent=2)
    write_markdown_report(report, len(records))
    print("\nWrote results.json and results.md")


def best_threshold(scores, labels):
    candidates = sorted(set(scores))
    best_t, best_f1 = 0.5, -1.0
    for t in candidates:
        preds = [s >= t for s in scores]
        _, _, f1 = prf1(labels, preds)
        if f1 > best_f1:
            best_f1, best_t = f1, t
    return best_t, best_f1


def prf1(labels, preds):
    tp = sum(1 for l, p in zip(labels, preds) if l and p)
    fp = sum(1 for l, p in zip(labels, preds) if not l and p)
    fn = sum(1 for l, p in zip(labels, preds) if l and not p)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return round(precision, 4), round(recall, 4), round(f1, 4)


def write_markdown_report(report, n_records):
    lines = [
        "# Checkbox/radio detection benchmark (issue #15) — PROTOTYPE results",
        "",
        f"{n_records} candidate-box records across 10 samples "
        "(fields absent from ground truth excluded — see benchmark.py `ground_truth_marked`).",
        "",
        "Threshold picked per method by sweeping all observed score values and maximizing "
        "overall F1 on the full pooled set (no held-out split — 10-sample prototype, "
        "not a claim of generalization).",
        "",
    ]
    for method, data in report.items():
        p, r, f1 = data["overall"]
        lines.append(f"## {method}")
        lines.append("")
        lines.append(f"Single global threshold={data['threshold']:.4f} (tuned on the full pooled set):")
        lines.append("")
        lines.append("| group | precision | recall | F1 |")
        lines.append("|---|---|---|---|")
        lines.append(f"| **overall** | {p} | {r} | {f1} |")
        for group, (gp, gr, gf1) in data["by_field_group"].items():
            lines.append(f"| {group} | {gp} | {gr} | {gf1} |")
        lines.append("")
        lines.append("Same detector, threshold tuned separately per field-type class:")
        lines.append("")
        lines.append("| group | threshold | precision | recall | F1 |")
        lines.append("|---|---|---|---|---|")
        for group, entry in data["by_field_group_own_threshold"].items():
            gp, gr, gf1 = entry["prf1"]
            lines.append(f"| {group} | {entry['threshold']:.4f} | {gp} | {gr} | {gf1} |")
        lines.append("")
    (OUT_DIR / "results.md").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
