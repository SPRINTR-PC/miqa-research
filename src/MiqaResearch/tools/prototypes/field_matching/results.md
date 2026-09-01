# Field matching benchmark (issue #16) -- PROTOTYPE results

Label localization hit rate (all 370 field-anchors, all field types, all 10 samples): **0.9622** (356/370)

Escalation rate (fields flagged for VLM fallback per the escalation contract): **0.4297** (159/370)

## Value-assignment accuracy, using issue #15's thresholds verbatim

| group | n | correct | accuracy |
|---|---|---|---|
| checkbox | 37 | 1 | 0.027 |
| circle-scale | 70 | 1 | 0.0143 |
| radio | 30 | 0 | 0.0 |
| ranged-radio-grid | 99 | 20 | 0.202 |

## Threshold recalibration (this pipeline's own box crops vs #15's hand-labelled crops)

| group | #15 threshold | recalibrated threshold | precision | recall | F1 |
|---|---|---|---|---|---|
| checkbox | 0.279 | 0.2234 | 0.9286 | 0.5909 | 0.7222 |
| circle-scale | 0.1095 | 0.0528 | 0.2923 | 1.0 | 0.4524 |
| radio | 0.2794 | 0.0 | 0.2051 | 1.0 | 0.3404 |
| ranged-radio-grid | 0.2682 | 0.1834 | 0.4808 | 0.3788 | 0.4237 |

## Value-assignment accuracy, using recalibrated thresholds

| group | n | correct | accuracy |
|---|---|---|---|
| checkbox | 37 | 5 | 0.1351 |
| circle-scale | 70 | 1 | 0.0143 |
| radio | 30 | 3 | 0.1 |
| ranged-radio-grid | 99 | 24 | 0.2424 |

## Per-sample summary (using issue #15's thresholds)

| sample | label hit rate | ranged-radio-grid | circle-scale | checkbox | radio |
|---|---|---|---|---|---|
| sample_01 | 0.9459 | 0.4 | 0.1429 | 0.0 | 0.0 |
| sample_02 | 0.973 | 0.4 | 0.0 | 0.0 | 0.0 |
| sample_03 | 0.9459 | 0.3 | 0.0 | 0.25 | 0.0 |
| sample_04 | 0.973 | 0.2 | 0.0 | 0.0 | 0.0 |
| sample_05 | 0.973 | 0.4 | 0.0 | 0.0 | 0.0 |
| sample_06 | 0.9459 | 0.0 | 0.0 | 0.0 | 0.0 |
| sample_07 | 0.973 | 0.0 | 0.0 | 0.0 | 0.0 |
| sample_08 | 0.973 | 0.0 | 0.0 | 0.0 | 0.0 |
| sample_09 | 0.9459 | 0.1 | 0.0 | 0.0 | 0.0 |
| sample_10 | 0.973 | 0.2 | 0.0 | 0.0 | 0.0 |