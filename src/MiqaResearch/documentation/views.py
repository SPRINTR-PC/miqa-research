from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.translation import get_language

from documentation.manuals import MANUALS, build_languages, canonical_url_path, docnames_for, load_page

# Sphinx's own search and index pages; the app has its own search.
SPHINX_ONLY_PAGES = {"search", "genindex"}


def _page_url(manual, url_path):
    if url_path:
        return redirect("manuals:page", manual=manual, page=url_path, permanent=True)
    return redirect("manuals:page", manual=manual, permanent=True)


@login_required
def page(request, manual, page=""):
    entry = MANUALS.get(manual)
    if entry is None or not entry.can_read(request.user) or page in SPHINX_ONLY_PAGES:
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
