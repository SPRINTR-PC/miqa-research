# Research: how django-sphinx-view 26 works

Resolves #228 (parent map #227). Findings only. No spec decisions locked here.

Legend: **[S]** = read in package source (26.1 sdist from PyPI, sha256 `529b8c70…39e5`, matches `uv.lock`; identical to `.venv/…/sphinx_view/`). **[D]** = package's own docs (`docs/source/index.rst`, same sdist; published at https://noumenal.es/django-sphinx-view/). **[G]** = GitHub repo/issues (https://github.com/carltongibson/django-sphinx-view). **[E]** = empirically checked this session (Sphinx 9.1.0, myst-parser 5.1.0, sphinxcontrib-mermaid 2.1.0, sphinxcontrib-serializinghtml 2.0.0, Django 6.0, repo `.venv`).

## TL;DR

- Whole package = 3 files, ~50 lines: a Sphinx builder (`SphinxViewBuilder`), a Django view (`DocumentationView`), a 12-line template. [S]
- Sphinx builds to **JSON** (`.fjson` per page); Django view reads that file per request and renders `doc.body|safe` into a template extending a configurable base. No Sphinx at request time. [S][D]
- Everything else (static assets, search, access control, i18n, multiple projects) is **left to us**. Package is a thin seam; plan to subclass the view (or write our own ~30 lines).
- Blockers/gotchas for this repo:
  1. `import sphinx_view` imports Sphinx (`builders.py`), but Sphinx is **dev-only** here → prod image (`uv sync --no-dev`) would fail on `INSTALLED_APPS`/import. [S][E]
  2. **Path traversal**: `..` in URL escapes `json_build_dir` (reads any `*.fjson` / `*/index.fjson`). `/manuals/user/../technical/` could serve Technical Manual through the User-Manual route → bypasses admin-only rule. [E]
  3. Leftover `print()` calls in `get_doc_json` write every request path to stdout. [S][E]
  4. Our `base.html` has only `{% block main %}`; package template expects `title`, `doc`, `toc` blocks. [S][repo]
- Licence LGPL-2.1. [G]

## Sources

- PyPI sdist `django_sphinx_view-26.1.tar.gz` (released 2026-02-23) [S][D]
- Installed: `src/MiqaResearch/.venv/lib/python3.14/site-packages/sphinx_view/{__init__,builders,views}.py`, `templates/sphinx_view/page.html` [S]
- `sphinxcontrib/serializinghtml/__init__.py` 2.0.0 (base class `JSONHTMLBuilder`) [S]
- `sphinxcontrib/mermaid/__init__.py` 2.1.0 (`install_js`) [S]
- GitHub repo, commits, issues #13, #16, #17, #24, #25 [G]

## 1. Builder / output format

- `sphinx_view.setup(app)` registers `SphinxViewBuilder` with `override=True`; builder `name = 'json'`, so adding `"sphinx_view"` to `extensions` replaces Sphinx's stock `json` builder. [S] `__init__.py`, `builders.py`
- `SphinxViewBuilder(JSONHTMLBuilder)` only overrides `get_doc_context` to add `doc['toctree']` = rendered **global** toctree HTML (`TocTree(env).get_toctree_for(docname, builder, collapse=True)`), `''` if none. [S] (fix for toctree being dropped as a callable: 26.1 commit `2fa368e`, PR #31 [G])
- Extension is optional; without it stock JSON builder runs and there is no `toctree` key. [D]
- Build: `sphinx-build -b json <src> <out>` or `make json` (quickstart Makefile `%:` catch-all → `sphinx-build -M json`, output `_build/json`). [D][repo Makefile]
- Output layout (from `JSONHTMLBuilder`/`SerializingHTMLBuilder`) [S][E]:
  - `<docname>.fjson` per page (`index.fjson`, `src/page.fjson`); keys incl. `title`, `body`, `toc` (page-local TOC HTML), `toctree`, `prev`, `next`, `parents`, `meta`, `metatags`, `display_toc`, `sourcename`, `current_page_name`.
  - `globalcontext.json` (project, `language`, `css_files`, `script_files`, theme options…).
  - `searchindex.json`, `search.fjson` (stub, empty body), `genindex.fjson`, `objects.inv`.
  - `_images/` (copied images), `_static/` (Sphinx + theme JS/CSS), `_sources/`, `environment.pickle`, `last_build`.
- URLs are directory style: `get_target_uri` → `''` for `index`, `docname + '/'` otherwise. Links in `body` are relative (e.g. `href="src/page/"`, `prev.link = '../../'`). [S][E]
- Theme is irrelevant: builder sets `self.theme = None`, no template bridge. Theme extensions still run hooks (RTD theme's `_static/css|fonts|js` get copied; furo breaks the JSON build, issue #25 open [G]). → Drop `sphinx_rtd_theme` from manuals' `extensions`/`html_theme` when we go JSON-only. [S][E][G]
- Verified: repo's `documentation/manuals/technical` builds cleanly with `-b json` (1 warning: missing `_static`). `recommonmark` `source_parsers` in conf has no effect (not a Sphinx 9 config value; myst handles `.md`). [E]

## 2. URL routing and view API

`sphinx_view.DocumentationView(TemplateView)` [S] `views.py`:

| Attr / method | Default | Role |
|---|---|---|
| `json_build_dir: Path` | `None` (required) | root of JSON build |
| `base_template_name` | `"base.html"` | put in context; page template `{% extends base_template_name %}` |
| `template_name` | `"sphinx_view/page.html"` | page template |
| `get_doc_json()` | — | maps `kwargs["path"]` to file; returns parsed JSON or `Http404` |
| `get_context_data()` | — | adds `base_template_name`, `doc` |

Routing contract [D][S][E]:

```python
path("docs<path:path>", DocumentationView.as_view(json_build_dir=Path(...), base_template_name="docs_base.html"), name="documentation")
```

- `path` kwarg **must start and end with `/`**. Lookup order: `path[1:] + "index.fjson"`, then `path[1:-1] + ".fjson"`. [S]
- No trailing slash → `Http404` (not redirect; `APPEND_SLASH` doesn't help because URL resolves). `/docs` (empty) doesn't match `<path:path>` → 404. Need explicit redirect route for bare prefix. [E]
- No `reverse()` helper for pages; links inside `body` are relative, so the **mount prefix is free** (e.g. `manuals/user/`). [E]
- `genindex/`, `search/` resolve but render empty (no body). [E]
- Security gotcha (verified with Django test client): `/manuals/user/../../out/json/` and `/manuals/user/%2e%2e/json/` return 200 by reading outside `json_build_dir`. Limited to `.fjson`/`index.fjson` files, but crosses between manuals if build dirs are siblings. Browsers normalise `..`; raw clients don't; Django doesn't. Fix in subclass: `candidate.resolve().is_relative_to(base.resolve())`, or reject paths containing `..`. [E]
- Two `print()` calls in `get_doc_json` (path + candidate) → noise in Granian logs. Override `get_doc_json` anyway (for the fix above) and drop them. [S]
- Open upstream: #16 (system check for `json_build_dir`), #17 (per-page templates via `:page_template:` meta — **not** in 26.1), #24 (404 handler), #5 (show deployed version). [G]

## 3. Templates: can pages extend our `base.html`?

Yes, but not as-is. [S][D]

- Shipped `sphinx_view/page.html`: `{% extends base_template_name %}` + blocks `title` (`doc.title`), `doc` (`doc.body|safe`), `toc` (`doc.toc|safe`). Base "should provide `title`, `doc`, and `toc` blocks". Global `doc.toctree` not rendered by default. [S][D]
- Our `templates/base.html` has only `{% block main %}` and a hard-coded `<title>MIQA research</title>`. [repo]
- Fit: set `template_name` to our own template (e.g. `manuals/page.html`) that `{% extends "base.html" %}` and fills `main` with a layout: sidebar `{{ doc.toctree|safe }}`, content `{{ doc.body|safe }}`, on-page `{{ doc.toc|safe }}`, prev/next from `doc.prev`/`doc.next`. `base_template_name` then unused. Optionally add `{% block title %}` to `base.html`. Navbar/theme toggle come for free (they're in `base.html`). [S][repo]
- Styling: body is plain Sphinx/docutils HTML (`section`, `h1 > a.headerlink`, `div.highlight` Pygments spans, `div.admonition`, `table.docutils`, `ul li.toctree-l1/.current`). No classes of ours → need a scoped `.manual-content` prose style in `mires.css` (+ Pygments light/dark CSS; `pygmentize -S … -f html` or `_static/pygments.css`). Headerlink glyph is `` (FontAwesome private-use, from RTD) — hide or restyle. [E]
- `|safe` on build output: trust boundary = our repo content at image build time. OK, but note raw HTML in MyST is passed through. [S]

## 4. Static assets (images, mermaid JS)

Package does **nothing** for assets. [S]

- Images → copied to `<out>/_images/`, body refs relative, e.g. `src="../../_images/logo.svg"` from `/…/src/page/` → resolves to `<mount>/_images/logo.svg`. View rejects that URL (no trailing slash → 404). [E]
  Options: (a) serve `<out>/_images/` at `<mount>/_images/` via small auth-checked `FileResponse` view (keeps admin-only for Technical Manual images); (b) copy into `STATIC_ROOT` at image build + rewrite URLs (loses access control; static is public). Repo has no whitenoise; static served by Granian/infra. [repo]
- Mermaid: body contains only `<pre class="mermaid">…</pre>`. `sphinxcontrib.mermaid.install_js` adds the loader via `app.add_js_file(None, body=…, type="module")` pointing at **jsDelivr CDN** (`mermaid@11.12.1` default); JSON dump flattens JS entries to filenames, so the inline init is lost (`script_files` ends in `''`). [S][E]
  → We must ship mermaid ourselves: vendor `mermaid.esm.min.mjs` under `static/js/`, load it on manual pages, `mermaid.run({querySelector: 'pre.mermaid'})`, re-run after HTMX swaps and on theme toggle (dark/light `theme` init). Avoids CDN dependency. [S]
- `_static/` Sphinx JS (`doctools.js`, `searchtools.js`, jQuery via RTD) is not needed by our pages; don't serve it. `environment.pickle`, `.buildinfo`, `_sources/` must **not** be web-exposed. [E]

## 5. Sphinx search

Not supported by the package ("Indices and tables… This is TODO" in its docs; roadmap lists only view + future template bridge). [D][S]

- Build does produce `searchindex.json` (keys `docnames`, `filenames`, `titles`, `terms`, `titleterms`, `alltitles`, `indexentries`, `objects`…), per-language stemmed by Sphinx. `search.fjson` is a stub. [E]
- Options: (a) server-side Django view reading `searchindex.json` (term → doc ids; stem query with `snowballstemmer`, already a Sphinx dep), results rendered via HTMX — fits stack, per-language, access-controlled; (b) client-side reuse of Sphinx `searchtools.js` (expects `searchindex.js` via `Search.setIndex`, plus `documentation_options.js`, `language_data.js`) — wrap the JSON; more JS glue; (c) Postgres FTS over `.fjson` bodies at deploy. Decision belongs to the map's open "Search" item.

## 6. Multiple Sphinx projects (user + technical)

Supported by construction: `json_build_dir` is per `as_view()`; route each project separately. [D][S]

```python
path("manuals/user<path:path>", UserManualView.as_view(json_build_dir=BUILD / "user" / "en"), name="user_manual"),
path("manuals/technical<path:path>", TechnicalManualView.as_view(json_build_dir=BUILD / "technical" / "en"), name="technical_manual"),
```

- Relative links stay inside each mount. Cross-manual links: plain absolute URLs or intersphinx (needs `objects.inv`; built). [E]
- Must apply the traversal fix (§2), else the two routes aren't isolated. [E]
- Both conf.py are near-identical → shared base conf worth considering (not a package concern).

## 7. Access control hooks

None built in; docs say "subclass `DocumentationView` to require authentication". It's a plain `TemplateView`, so standard mixins/decorators apply. [D][S]

- User Manual: `LoginRequiredMixin` (repo uses `@login_required` on function views, e.g. `interfaces/http/views/monitor/index.py`). [repo]
- Technical Manual: `UserPassesTestMixin.test_func` (which admin predicate → map ticket). Or `login_required(...)(View.as_view(...))` in `urls.py`.
- Apply same check to image serving (§4) and search (§5) endpoints.

## 8. i18n

No built-in language support in the package. [S]

- Sphinx side: set `language` in conf / `-D language=sv`; translations via gettext (`sphinx-build -b gettext` → `.pot`, `sphinx-intl` → `locale/<lang>/LC_MESSAGES/*.po`, `locale_dirs`). Build once per language into its own dir, e.g. `_build/json/<lang>/`. `globalcontext.json` records `language`; search index stemmed per language. [E] (Sphinx intl docs: https://www.sphinx-doc.org/en/master/usage/advanced/intl.html — standard mechanism, not re-fetched)
- Django side: override `json_build_dir` resolution per request: `get_doc_json` picks `BUILD/<manual>/<django.utils.translation.get_language()>`, fall back to `en` if dir missing. Repo already has `USE_I18N = True`, `LANGUAGE_CODE = 'en-us'` → normalise `en-us` → `en`. [repo]
- Keep URLs language-neutral (no `i18n_patterns` needed) since relative links stay within the chosen build.

## 9. Fit with this repo: concrete issues found

1. **Dependency split**: `django-sphinx-view` is a prod dep, but `sphinx`, `myst-parser`, `sphinxcontrib-mermaid` are in `[dependency-groups] dev`. `uv export --frozen --no-dev` lists `django-sphinx-view==26.1` and **no** `sphinx`/`sphinxcontrib-serializinghtml`; the wheel declares no runtime deps (only `test` extra). `sphinx_view/__init__.py` imports `builders` → `sphinxcontrib.serializinghtml` → Sphinx. So `INSTALLED_APPS += ["sphinx_view"]` or `from sphinx_view import DocumentationView` → `ModuleNotFoundError` in the prod image. [S][E]
   Options: (a) move Sphinx toolchain to a `docs` group used only in the Dockerfile builder stage and write our own ~30-line view + template in the `documentation` app (no runtime import of `sphinx_view`; still use `sphinx_view` as the Sphinx extension at build); (b) make Sphinx a prod dep (bloat, but simplest).
   Given (a) we'd keep only the builder from the package; view behaviour we'd override anyway (traversal, prints, i18n, auth, template).
2. **Docker build**: Dockerfile has no docs step and builder stage runs `uv sync --no-dev`. Needs `sphinx-build -b json` per manual × language in a build stage, copy `_build/json/**` minus `environment.pickle`/`_sources`/`_static` into final image. [repo]
3. Manual `conf.py`: drop `sphinx_rtd_theme`, `recommonmark` import/`source_parsers`; add empty `_static` or remove `html_static_path`; `:ref:` roles in MyST `index.md` render literally (use `{ref}` syntax or drop "Indices and tables"). [E][repo]
4. `.gitignore` (working copy, uncommitted) lists `documentation/manual/{technical,user}/_build/` — path is `manuals/` (plural), so it wouldn't match. [repo]
5. `documentation` app commented out in `settings.py:306`; needed only if we host templates/views there.

## Open questions for the map

- Keep `sphinx_view.DocumentationView` (subclass) vs own view? (Recommendation input: own view, keep builder — see §9.1.)
- Image serving: auth-checked view vs public static.
- Search approach (§5).
- Which admin predicate for Technical Manual.
