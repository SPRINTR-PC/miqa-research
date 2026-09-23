"""PROTOTYPE -- throwaway UI variants for wayfinder ticket #180 (PROM review & signing UI).

DEBUG-only route /prototype/prom-review/?variant=A|B|C. No DB, no persistence: the
fixture is sample_01's real template + real classic-OCR output, VLM simulated.
"""

import json
from functools import cache
from pathlib import Path

import pymupdf
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

FIXTURE = Path(__file__).with_name("sample_01.json")
SCAN = settings.BASE_DIR / "tests" / "example_data" / "prom_data" / "prom_samples" / "sample_01" / "scan.pdf"


@cache
def _fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def index(request):
    return render(request, "prototype_prom_review/index.html", {"fixture": _fixture()})


@cache
def _page_png(page_index: int) -> bytes:
    with pymupdf.open(SCAN) as doc:
        return doc[page_index].get_pixmap(dpi=100).tobytes("png")


def page(request, page_index: int):
    return HttpResponse(_page_png(page_index), content_type="image/png")


def form_data(request):
    # <dynamic-form getFormDataUrl> wants [{id, value}], not ParsedPromForm's [{fieldId, value}].
    return JsonResponse([{"id": d["fieldId"], "value": d["value"]} for d in _fixture()["data"]], safe=False)


@csrf_exempt
def submit(request):
    return JsonResponse({"ok": True})
