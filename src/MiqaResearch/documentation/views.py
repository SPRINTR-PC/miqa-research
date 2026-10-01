import mimetypes

from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import get_language

from documentation import search as manual_search
from documentation.manuals import MANUALS, build_languages, canonical_url_path, docnames_for, find_asset, load_page

# Sphinx's own search and index pages; the app has its own search.
SPHINX_ONLY_PAGES = {"search", "genindex"}
LIVE_SEARCH_RESULTS = 8


def _page_url(manual, url_path):
    if url_path:
        return redirect("manuals:page", manual=manual, page=url_path, permanent=True)
    return redirect("manuals:page", manual=manual, permanent=True)


def _readable_manual(request, slug):
    manual = MANUALS.get(slug)
    if manual is None or not manual.can_read(request.user):
        raise Http404
    return manual


@login_required
def page(request, manual, page=""):
    entry = _readable_manual(request, manual)
    if page in SPHINX_ONLY_PAGES:
        raise Http404
    canonical = canonical_url_path(page)
    if canonical != page:
        return _page_url(manual, canonical)
    for language in build_languages(get_language()):
        for docname in docnames_for(page):
            found = load_page(entry, docname, language)
            if found is not None:
                return render(request, "documentation/page.html", {"page": found})
    raise Http404


@login_required
def search(request, manual):
    entry = _readable_manual(request, manual)
    query = request.GET.get("q", "")
    results = manual_search.search(entry, query, get_language())
    return render(request, "documentation/search.html", {"manual": entry, "query": query, "results": results})


@login_required
def search_live(request, manual):
    """The top bar's live results panel (an HTMX fragment); empty until the query is long enough."""
    entry = _readable_manual(request, manual)
    query = request.GET.get("q", "")
    if len(query.strip()) < manual_search.MIN_QUERY_LENGTH:
        return HttpResponse("")
    results = manual_search.search(entry, query, get_language())
    context = {"manual": entry, "query": query, "results": results[:LIVE_SEARCH_RESULTS]}
    return render(request, "documentation/search_panel.html", context)


def _asset_response(request, manual, relative_path, *, as_attachment):
    path = find_asset(_readable_manual(request, manual), relative_path, get_language())
    if path is None:
        raise Http404
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    response = FileResponse(path.open("rb"), content_type=content_type, as_attachment=as_attachment, filename=path.name)
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, max-age=3600"
    response["Content-Security-Policy"] = "sandbox"
    return response


@login_required
def image(request, manual, filename):
    return _asset_response(request, manual, f"_images/{filename}", as_attachment=False)


@login_required
def download(request, manual, digest, filename):
    return _asset_response(request, manual, f"_downloads/{digest}/{filename}", as_attachment=True)
