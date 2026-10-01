"""Sphinx configuration shared by every manual; each manual's conf.py imports it."""

copyright = "2026, Josef A. Lundman"
author = "Josef A. Lundman"

extensions = [
    "myst_parser",
    "sphinxcontrib.mermaid",
    "sphinx_view",
]

myst_enable_extensions = ["colon_fence", "dollarmath", "attrs_inline", "deflist"]

root_doc = "index"
exclude_patterns = ["locale", "Thumbs.db", ".DS_Store"]

# Translations: gettext .po catalogues under locale/<lang>/LC_MESSAGES/ (ADR 0029).
locale_dirs = ["locale/"]
gettext_compact = False
gettext_auto_build = True
translation_progress_classes = True

html_use_index = False
