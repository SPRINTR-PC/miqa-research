"""
PROTOTYPE — throwaway code for issue #15 (checkbox/radio detection on CPU).

Hand-derived candidate box coordinates for the PROM_1_PRO_GI_GU_SWE form, in pixels
at 200dpi, measured against `sample_01/scan.pdf`. Box provenance (locating boxes on
the page) is explicitly out of scope for #15 — that's issue #16 (field matching
without template geometry). These coordinates exist only so this prototype has
something to feed the detectors; they are NOT meant to ship.

All 10 fixture samples are phone-scans of the same printed template through the same
iOS document-scanner pipeline, but each capture crops/pads the page slightly
differently (see benchmark.py's `normalize_page_size`, which resizes every rendered
page to the sample_01 canonical size for its page index before these coordinates are
applied — verified visually to line up well; see README.md).

Layout notes:
- Pages are 0-indexed here (page 0 = cover/uppgifter, page 1 = Q1-11, page 2 =
  Q12-16, page 3 = Q17-25). sample_09's manifest flags pages 2 and 3 as physically
  swapped in that one scan.pdf — benchmark.py special-cases it.
- Q1-10 are `ranged-radio` fields laid out as an 11-column (0-10) grid on page 1.
- Q17-23 are a different mark style: the respondent circles a printed digit (1-4),
  not an X-in-a-box. Candidate boxes for these are generous (56x56) crops centered
  on each digit to comfortably contain a hand-drawn circle.
- Q11-15 and Q24 are irregular one-off checkbox/radio groups, hand-labelled per
  option below.
"""

CANONICAL_PAGE_SIZE = {
    0: (1648, 2339),
    1: (1659, 2312),
    2: (1650, 2339),
    3: (1659, 2334),
}

RANGED_RADIO_GRID_PAGE = 1
RANGED_RADIO_ROW_Y = {
    "prom101_q1_avforingsproblem": 282,
    "prom101_q2_avforingar_per_dygn": 365,
    "prom101_q3_skynda_till_toaletten": 466,
    "prom101_q4_avforingslackage": 548,
    "prom101_q5_planerar_toalettbesok": 665,
    "prom101_q6_gasavgang": 765,
    "prom101_q7_kramper": 847,
    "prom101_q8_slem": 928,
    "prom101_q9_blod": 1009,
    "prom101_q10_paverkan_daglig_aktivitet": 1099,
}
RANGED_RADIO_COL_X = [699, 774, 849, 923, 998, 1072, 1146, 1221, 1295, 1370, 1445]
RANGED_RADIO_BOX_SIZE = (38, 38)

CIRCLE_SCALE_PAGE = 3
CIRCLE_SCALE_ROW_Y = {
    "prom101_q17_urinera_ofta_dagen": 557,
    "prom101_q18_urinera_ofta_natten": 632,
    "prom101_q19_skynda_till_toaletten": 744,
    "prom101_q20_somnproblem_pga_urinering": 855,
    "prom101_q21_besvarligt_ga_hemifran": 966,
    "prom101_q22_urinlackage": 1040,
    "prom101_q23_smarta_sveda_urinering": 1150,
}
CIRCLE_SCALE_COL_X = [836, 1011, 1187, 1365]
CIRCLE_SCALE_BOX_SIZE = (56, 56)

# field_id -> field_type -> {option_value: (page, x, y, w, h)}
IRREGULAR_FIELDS = {
    "prom101_q11_tillfalle": {
        "type": "checkbox",
        "options": {
            "inget_lackage_alls": (1, 549, 1198, 38, 37),
            "hostar_nyser_skrattar": (1, 818, 1198, 37, 37),
            "lyfter_tungt": (1, 1173, 1199, 37, 36),
            "reser_sig_sittande_till_staende": (1, 549, 1259, 38, 37),
            "vid_gasavgang": (1, 1174, 1260, 36, 36),
            "annat_tillfalle": (1, 549, 1325, 38, 37),
        },
    },
    "prom101_q12_anvander_bloja": {
        "type": "radio",
        "options": {
            "nej": (2, 584, 268, 38, 38),
            "ja": (2, 742, 270, 33, 33),
        },
    },
    "prom101_q12_hur_ofta": {
        "type": "checkbox",
        "options": {
            "vid_vistelse_utanfor_hemmet": (2, 739, 381, 38, 39),
            "under_dagen": (2, 1135, 380, 38, 39),
            "under_natten": (2, 1351, 381, 38, 39),
            "annat_tillfalle": (2, 740, 478, 38, 40),
        },
    },
    "prom101_q13_medicin_mot_los_avforing": {
        "type": "checkbox",
        "options": {
            "nej": (2, 586, 630, 38, 39),
            "ja_imodium": (2, 744, 631, 38, 39),
            "ja_predclysma": (2, 745, 754, 37, 38),
            "ja_annan": (2, 745, 831, 37, 38),
        },
    },
    "prom101_q14_kostvanor": {
        "type": "checkbox",
        "options": {
            "nej": (2, 588, 911, 37, 37),
            "ja_fettsnal_kost": (2, 745, 911, 37, 37),
            "ja_fiberrik_kost": (2, 1053, 910, 38, 37),
            "ja_mjolkfattig_kost": (2, 1301, 908, 38, 38),
            "ja_annat": (2, 745, 1011, 38, 35),
        },
    },
    "prom101_q15_livskvalitet": {
        "type": "radio",
        "options": {
            "mycket_nojd": (2, 588, 1090, 37, 38),
            "nojd": (2, 856, 1090, 38, 37),
            "tillfredsstallande": (2, 1054, 1089, 37, 38),
            "blandade_kanslor": (2, 1301, 1089, 38, 38),
            "missbelaten": (2, 588, 1152, 38, 38),
            "olycklig": (2, 856, 1152, 38, 38),
            "forfarligt": (2, 1054, 1152, 37, 37),
        },
    },
    "prom101_q24_livskvalitet": {
        "type": "radio",
        "options": {
            "mycket_nojd": (3, 622, 1404, 37, 39),
            "nojd": (3, 891, 1403, 38, 38),
            "tillfredsstallande": (3, 1089, 1404, 38, 38),
            "blandade_kanslor": (3, 1337, 1405, 39, 38),
            "missbelaten": (3, 622, 1467, 37, 39),
            "olycklig": (3, 892, 1466, 37, 39),
            "forfarligt": (3, 1090, 1467, 38, 39),
        },
    },
}


def ranged_radio_box(field_id, level):
    """level is an int 0-10. Returns (page, x, y, w, h)."""
    y = RANGED_RADIO_ROW_Y[field_id]
    x = RANGED_RADIO_COL_X[level]
    w, h = RANGED_RADIO_BOX_SIZE
    return (RANGED_RADIO_GRID_PAGE, x, y, w, h)


def circle_scale_box(field_id, level):
    """level is an int 1-4. Returns (page, x, y, w, h) centered on the digit."""
    y = CIRCLE_SCALE_ROW_Y[field_id]
    x = CIRCLE_SCALE_COL_X[level - 1]
    w, h = CIRCLE_SCALE_BOX_SIZE
    return (CIRCLE_SCALE_PAGE, x - w // 2, y - h // 2, w, h)


def all_candidate_boxes():
    """
    Yields (field_id, field_type, option_key, page, x, y, w, h) for every
    candidate box in scope for this prototype (ranged-radio, checkbox, radio —
    not free-text/numeric/datetime fields).
    """
    for field_id in RANGED_RADIO_ROW_Y:
        for level in range(11):
            page, x, y, w, h = ranged_radio_box(field_id, level)
            yield field_id, "ranged-radio", str(level), page, x, y, w, h

    for field_id in CIRCLE_SCALE_ROW_Y:
        for level in range(1, 5):
            page, x, y, w, h = circle_scale_box(field_id, level)
            yield field_id, "ranged-radio", str(level), page, x, y, w, h

    for field_id, spec in IRREGULAR_FIELDS.items():
        for option_key, (page, x, y, w, h) in spec["options"].items():
            yield field_id, spec["type"], option_key, page, x, y, w, h
