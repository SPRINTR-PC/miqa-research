"""PROTOTYPE — throwaway (#233 Manual page layout in the MIQA shell). Do not merge.

Three layout variants of a manual page inside the MIQA shell, switchable via
``?variant=A|B|C`` (remembered in a cookie so in-manual links keep it). Reads a
dev JSON build from ``documentation/builds/user/en`` — build it with:

    .venv/bin/sphinx-build -E -b json documentation/manuals/user documentation/builds/user/en
"""
import json
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render

BUILD = Path(settings.BASE_DIR) / "documentation" / "builds" / "user" / "en"
VARIANTS = {
    "A": "Docs three-column",
    "B": "Reading column + contents drawer",
    "C": "App-style chapter tabs",
}


@login_required
def manual_layout(request, page=""):
    variant = request.GET.get("variant") or request.COOKIES.get("proto_manual_variant") or "A"
    if variant not in VARIANTS:
        variant = "A"
    page = page.strip("/")
    candidate = (BUILD / page / "index.fjson") if not page else (BUILD / f"{page}.fjson")
    if not candidate.resolve().is_relative_to(BUILD.resolve()) or not candidate.exists():
        raise Http404
    doc = json.loads(candidate.read_text())
    root = json.loads((BUILD / "index.fjson").read_text())
    response = render(request, "prototype/manual_layout.html", {
        "doc": doc,
        # Whole-manual toctree, rendered relative to the manual root; only valid on the index page.
        # Variants use the page's own `toctree` (Sphinx renders it relative to the page).
        "root_title": root["title"],
        "root_link": "../" * len(page.split("/")) if page else "./",
        "variant": variant,
        "proto_debug": settings.DEBUG,
        "variant_name": VARIANTS[variant],
        "variants": VARIANTS,
        "show_untranslated": request.GET.get("untranslated") == "1",
        "is_staff_reader": request.user.is_superuser or request.user.is_staff,
    })
    response.set_cookie("proto_manual_variant", variant)
    return response
