"""
PROTOTYPE -- throwaway code for issue #16 (field matching without template geometry).

Run: python tools/prototypes/field_matching/benchmark.py
(from the project root, i.e. src/MiqaResearch/)

Renders all 10 real fixture scans, OCRs every page, runs the field-matching
pipeline (label localization -> region carving -> option/box discovery -> mark
detection), compares assigned values to each sample's ground_truth.json, and
writes results.json / results.md into this directory. No Django import needed.
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tools.prototypes.field_matching import geometry, ocr_engine, template_flatten
from tools.prototypes.field_matching.pipeline import ACTIVE_THRESHOLDS, run_pipeline

ROOT = Path(__file__).resolve().parents[3]
SAMPLES_DIR = ROOT / "tests/example_data/prom_data/prom_samples"
TEMPLATE_PATH = ROOT / "tests/example_data/prom_data/templates/PROM_1_PRO_GI_GU_SWE.json"
OUT_DIR = Path(__file__).resolve().parent

BOX_MARK_TYPES = ("checkbox", "radio", "ranged-radio")


def group_for_field(f):
    if f.type == "ranged-radio":
        return "ranged-radio-grid" if len(f.options) > 6 else "circle-scale"
    return f.type


def gt_as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def evaluate_sample(sample_id, fields, gt_data):
    sample_dir = SAMPLES_DIR / sample_id
    pdf_path = sample_dir / "scan.pdf"
    gt = {row["fieldId"]: row["value"] for row in gt_data["data"]}

    pages_gray = ocr_engine.render_pages(pdf_path)
    pages_words = [ocr_engine.ocr_words(g) for g in pages_gray]
    pages_boxes = [geometry.find_square_boxes(g) for g in pages_gray]

    results = run_pipeline(fields, pages_words, pages_gray, pages_boxes)

    records = []
    for f in fields:
        rec = results[f.id]
        in_gt = f.id in gt
        correct = None
        if f.type in BOX_MARK_TYPES and in_gt:
            predicted = set(rec["predicted"] or [])
            expected = set(gt_as_list(gt[f.id]))
            if f.type == "checkbox":
                correct = predicted == expected
            else:  # radio, ranged-radio: single expected value
                correct = len(predicted) == 1 and predicted == expected
        records.append(
            {
                "sample_id": sample_id,
                "field_id": f.id,
                "type": f.type,
                "group": group_for_field(f),
                "anchor_found": rec["anchor_found"],
                "label_match_score": round(rec["label_match_score"], 3),
                "page": rec["page"],
                "predicted": rec["predicted"],
                "ground_truth": gt.get(f.id),
                "in_ground_truth": in_gt,
                "correct": correct,
                "escalate": rec["escalate"],
                "signals": rec["signals"],
            }
        )
    return records


def collect_option_scores(all_records):
    """
    Per-box (score, marked_by_ground_truth) pairs, pooled across all samples,
    restricted to fields present in ground truth -- same evaluation policy #15
    used. This is what lets us recalibrate thresholds *for this pipeline's own*
    auto-discovered-box crops instead of blindly trusting #15's hand-labelled-crop
    thresholds (see README.md: the two crop-generation paths aren't pixel-
    identical, so a threshold recalibration is an expected, honest step here).
    """
    by_group = {}
    for r in all_records:
        if r["type"] not in BOX_MARK_TYPES or not r["in_ground_truth"]:
            continue
        expected = set(gt_as_list(r["ground_truth"]))
        for value, score, group in r["signals"].get("option_scores", []):
            marked_gt = str(value) in expected
            by_group.setdefault(group, []).append((score, marked_gt))
    return by_group


def sweep_best_threshold(pairs):
    """Same methodology as #15: try every observed score as a candidate threshold, maximize F1."""
    candidates = sorted({round(s, 4) for s, _ in pairs})
    best = {"threshold": 0.5, "precision": 0.0, "recall": 0.0, "f1": 0.0}
    for t in candidates:
        tp = sum(1 for s, m in pairs if s >= t and m)
        fp = sum(1 for s, m in pairs if s >= t and not m)
        fn = sum(1 for s, m in pairs if s < t and m)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        if f1 > best["f1"]:
            best = {"threshold": t, "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4)}
    return best


def recompute_predicted(record, thresholds):
    scores = record["signals"].get("option_scores")
    if scores is None:
        return record["predicted"], record["correct"]
    predicted = [v for v, s, g in scores if s >= thresholds[g]]
    if not record["in_ground_truth"]:
        return predicted, None
    expected = set(gt_as_list(record["ground_truth"]))
    if record["type"] == "checkbox":
        correct = set(predicted) == expected
    else:
        correct = len(predicted) == 1 and set(predicted) == expected
    return predicted, correct


def aggregate(all_records):
    by_group = {}
    for r in all_records:
        if r["type"] not in BOX_MARK_TYPES or not r["in_ground_truth"]:
            continue
        g = by_group.setdefault(r["group"], {"n": 0, "correct": 0})
        g["n"] += 1
        g["correct"] += int(bool(r["correct"]))

    label_hits = sum(1 for r in all_records if r["anchor_found"])
    label_total = len(all_records)

    escalated = sum(1 for r in all_records if r["escalate"])

    return {
        "per_group_accuracy": {
            g: {"n": v["n"], "correct": v["correct"], "accuracy": round(v["correct"] / v["n"], 4) if v["n"] else None}
            for g, v in sorted(by_group.items())
        },
        "label_localization_hit_rate": round(label_hits / label_total, 4) if label_total else None,
        "label_localization_hits": label_hits,
        "label_localization_total": label_total,
        "escalation_rate": round(escalated / label_total, 4) if label_total else None,
        "escalated_fields": escalated,
    }


def main():
    template = template_flatten.load_template(TEMPLATE_PATH)
    fields = template_flatten.flatten(template)

    sample_dirs = sorted(p.name for p in SAMPLES_DIR.iterdir() if p.is_dir())
    all_records = []
    per_sample_summary = {}

    for sample_id in sample_dirs:
        t0 = time.time()
        gt_data = json.loads((SAMPLES_DIR / sample_id / "ground_truth.json").read_text(encoding="utf-8"))
        records = evaluate_sample(sample_id, fields, gt_data)
        all_records.extend(records)
        summary = aggregate(records)
        per_sample_summary[sample_id] = summary
        dt = time.time() - t0
        print(f"{sample_id}: label_hit_rate={summary['label_localization_hit_rate']} "
              f"per_group={summary['per_group_accuracy']} ({dt:.1f}s)")

    overall_v15 = aggregate(all_records)

    # Recalibration pass: reuse #15's threshold-sweep methodology, but against
    # THIS pipeline's own auto-discovered-box crops rather than #15's hand-
    # labelled ones (see collect_option_scores docstring).
    option_scores_by_group = collect_option_scores(all_records)
    recalibration = {g: sweep_best_threshold(pairs) for g, pairs in option_scores_by_group.items()}
    new_thresholds = {g: v["threshold"] for g, v in recalibration.items()}

    all_records_v2 = []
    for r in all_records:
        r2 = dict(r)
        r2["predicted"], r2["correct"] = recompute_predicted(r, new_thresholds)
        all_records_v2.append(r2)
    overall_recal = aggregate(all_records_v2)

    (OUT_DIR / "raw_records.json").write_text(json.dumps(all_records, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "results.json").write_text(
        json.dumps(
            {
                "overall_using_issue15_thresholds": overall_v15,
                "overall_using_recalibrated_thresholds": overall_recal,
                "recalibration": recalibration,
                "per_sample_using_issue15_thresholds": per_sample_summary,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    def group_table(overall):
        out = ["| group | n | correct | accuracy |", "|---|---|---|---|"]
        for g, v in overall["per_group_accuracy"].items():
            out.append(f"| {g} | {v['n']} | {v['correct']} | {v['accuracy']} |")
        return out

    lines = ["# Field matching benchmark (issue #16) -- PROTOTYPE results", ""]
    lines.append(f"Label localization hit rate (all {overall_v15['label_localization_total']} field-anchors, "
                  f"all field types, all 10 samples): **{overall_v15['label_localization_hit_rate']}** "
                  f"({overall_v15['label_localization_hits']}/{overall_v15['label_localization_total']})")
    lines.append("")
    lines.append(f"Escalation rate (fields flagged for VLM fallback per the escalation contract): "
                 f"**{overall_v15['escalation_rate']}** ({overall_v15['escalated_fields']}/{overall_v15['label_localization_total']})")
    lines.append("")
    lines.append("## Value-assignment accuracy, using issue #15's thresholds verbatim")
    lines.append("")
    lines.extend(group_table(overall_v15))
    lines.append("")
    lines.append("## Threshold recalibration (this pipeline's own box crops vs #15's hand-labelled crops)")
    lines.append("")
    lines.append("| group | #15 threshold | recalibrated threshold | precision | recall | F1 |")
    lines.append("|---|---|---|---|---|---|")
    for g, v in sorted(recalibration.items()):
        lines.append(f"| {g} | {ACTIVE_THRESHOLDS.get(g)} | {v['threshold']} | {v['precision']} | {v['recall']} | {v['f1']} |")
    lines.append("")
    lines.append("## Value-assignment accuracy, using recalibrated thresholds")
    lines.append("")
    lines.extend(group_table(overall_recal))
    lines.append("")
    lines.append("## Per-sample summary (using issue #15's thresholds)")
    lines.append("")
    lines.append("| sample | label hit rate | ranged-radio-grid | circle-scale | checkbox | radio |")
    lines.append("|---|---|---|---|---|---|")
    for sample_id, s in per_sample_summary.items():
        pg = s["per_group_accuracy"]
        row = lambda k: f"{pg[k]['accuracy']}" if k in pg else "n/a"
        lines.append(f"| {sample_id} | {s['label_localization_hit_rate']} | {row('ranged-radio-grid')} | "
                     f"{row('circle-scale')} | {row('checkbox')} | {row('radio')} |")
    (OUT_DIR / "results.md").write_text("\n".join(lines), encoding="utf-8")

    print("\nWrote results.json, results.md, raw_records.json")
    print("using #15 thresholds:", json.dumps(overall_v15, indent=2))
    print("using recalibrated thresholds:", json.dumps(overall_recal, indent=2))
    print("recalibration:", json.dumps(recalibration, indent=2))


if __name__ == "__main__":
    main()
