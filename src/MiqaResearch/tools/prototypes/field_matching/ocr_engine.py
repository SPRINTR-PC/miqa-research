"""
PROTOTYPE -- throwaway code for issue #16 (field matching without template geometry).

Page rendering + Tesseract word-level OCR extraction.
"""

import numpy as np
import pymupdf
import pytesseract
from PIL import Image

DPI = 200


def render_pages(pdf_path):
    """Render every page of a PDF to a grayscale numpy array at DPI."""
    doc = pymupdf.open(pdf_path)
    pages = []
    for page in doc:
        pix = page.get_pixmap(dpi=DPI, colorspace=pymupdf.csGRAY)
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        pages.append(arr[:, :, 0])
    return pages


def ocr_words(gray_img, lang="swe"):
    """
    Word-level OCR via Tesseract. Returns a list of dicts:
    {text, left, top, width, height, right, bottom, cx, cy, conf, block, par, line}
    sorted into reading order (line-grouped: block/par/line, then top, then left within line).
    """
    img = Image.fromarray(gray_img)
    data = pytesseract.image_to_data(img, lang=lang, config="--psm 6", output_type=pytesseract.Output.DICT)
    words = []
    n = len(data["text"])
    for i in range(n):
        text = data["text"][i].strip()
        if not text or not any(c.isalnum() for c in text):
            # Drop punctuation-only tokens (Tesseract routinely misreads empty
            # printed checkbox squares as things like "[]", "--", "|"). These
            # normalize away to nothing during text-similarity scoring anyway
            # (textnorm.normalize strips punctuation), so keeping them contributes
            # nothing to a match's score but still corrupts its bounding box --
            # discovered via a bbox that spread across the full page width because
            # a couple of stray "[]" tokens far to the right rode along in the
            # winning window silently.
            continue
        try:
            conf = float(data["conf"][i])
        except ValueError:
            conf = -1.0
        left, top, width, height = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        words.append(
            {
                "text": text,
                "left": left,
                "top": top,
                "width": width,
                "height": height,
                "right": left + width,
                "bottom": top + height,
                "cx": left + width / 2,
                "cy": top + height / 2,
                "conf": conf,
                "block": data["block_num"][i],
                "par": data["par_num"][i],
                "line": data["line_num"][i],
            }
        )

    # Reading order: group into lines by (block, par, line), order lines by their
    # min top, order words within a line by left. This is a simple heuristic --
    # good enough for a form that's mostly single-column body text; the multi-
    # column checkbox/radio option grids are handled separately via spatial
    # region search, not this global reading order.
    line_key = lambda w: (w["block"], w["par"], w["line"])
    lines = {}
    for w in words:
        lines.setdefault(line_key(w), []).append(w)
    ordered_lines = sorted(lines.items(), key=lambda kv: min(w["top"] for w in kv[1]))
    result = []
    for _, line_words in ordered_lines:
        result.extend(sorted(line_words, key=lambda w: w["left"]))
    return result
