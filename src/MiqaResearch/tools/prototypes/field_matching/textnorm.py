"""
PROTOTYPE -- throwaway code for issue #16.

Text normalization + fuzzy matching for label localization. Swedish diacritics
(å/ä/ö) are meaningful letters, not accents -- but Tesseract does sometimes mangle
them (e.g. "å" -> "a" or a stray symbol), so we score both a diacritics-preserved
and a diacritics-stripped comparison and take whichever is better. This costs
nothing extra (both are cheap) and consistently recovers a few otherwise-missed
matches without giving up precision on words that are genuinely different only in
their diacritics (e.g. two labels that differ solely by en dash vs em dash are
unaffected either way).
"""

import re
import unicodedata
from difflib import SequenceMatcher

_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WS_RE = re.compile(r"\s+")


def _strip_diacritics(s):
    decomposed = unicodedata.normalize("NFKD", s)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def normalize(s, strip_diacritics=False):
    s = s.lower()
    if strip_diacritics:
        s = _strip_diacritics(s)
    s = _PUNCT_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    return s


def tokenize(s, strip_diacritics=False):
    return normalize(s, strip_diacritics).split()


def similarity(a, b):
    """Best of diacritics-preserved and diacritics-stripped SequenceMatcher ratio."""
    s1 = SequenceMatcher(None, normalize(a, False), normalize(b, False)).ratio()
    s2 = SequenceMatcher(None, normalize(a, True), normalize(b, True)).ratio()
    return max(s1, s2)
