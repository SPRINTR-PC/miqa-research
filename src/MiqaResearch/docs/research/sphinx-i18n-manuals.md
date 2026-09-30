# Research: Sphinx i18n options for the MyST manuals

Resolves issue #229 (parent map #227). This file records findings and ends with a recommendation. The decision itself belongs to #231.

Pinned versions come from `src/MiqaResearch/.venv/lib/python3.14/site-packages`: **Sphinx 9.1.0**, **myst-parser 5.1.0**, **django-sphinx-view 26.1**, **Babel 2.18.0** (a Sphinx dependency), sphinx-rtd-theme 3.1.0. The experiment ran **sphinx-intl 2.4.0** through `uvx`; the project does not depend on it.

Sources:
- **[sphinx-intl-doc]**: https://www.sphinx-doc.org/en/master/usage/advanced/intl.html
- **[sphinx-conf]**: https://www.sphinx-doc.org/en/master/usage/configuration.html (the i18n and gettext options)
- **[sphinx-src]**: the installed `sphinx/transforms/i18n.py`, `sphinx/builders/__init__.py`, `sphinx/builders/gettext.py`, `sphinx/util/i18n.py` and `sphinx/config.py`
- **[intl-qs]**: https://sphinx-intl.readthedocs.io/en/master/quickstart.html
- **[dsv-src]**: the installed `sphinx_view/{__init__,builders,views}.py` and `templates/sphinx_view/page.html`
- **[dsv-doc]**: https://noumenal.es/django-sphinx-view/
- **[myst-doc]**: https://myst-parser.readthedocs.io/en/latest/configuration.html. It says nothing about i18n, so gettext support for `.md` comes entirely from Sphinx.
- **[repo]**: `MiqaResearch/settings.py`, `MiqaResearch/urls.py` and `documentation/manuals/*/conf.py`
- **[exp]**: a throwaway copy of `documentation/manuals/user` in a scratch directory, built with the project venv. Nothing from it was committed.

## 1. Current state of the repo

- Django i18n is half-enabled. `USE_I18N = True` and `LANGUAGE_CODE = 'en-us'` are set. `LANGUAGES`, `LOCALE_PATHS`, `LocaleMiddleware` and `i18n_patterns` are all absent [repo settings.py:568-576, MIDDLEWARE at :339; urls.py]. As a result, `get_language()` is always `en-us` today. Templates already call `{% get_current_language %}` in places (for example `templates/02_upload_data/index.html`).
- The manual `conf.py` files set neither `language` nor `locale_dirs`. They use the defaults: `language='en'` and `locale_dirs=['locales']`, resolved relative to srcdir [sphinx-conf; sphinx-src config.py:230-231].
- `conf.py` still does `from recommonmark.parser import CommonMarkParser` and sets `source_parsers` and a list-form `source_suffix`. The `.md` files are still parsed by MyST: the `(label)=` targets resolve in the output [exp]. The import still matters, though: **sphinx-intl runs `conf.py`**, so it failed with `ModuleNotFoundError: recommonmark` until recommonmark was added to its environment [exp]. Removing the stray recommonmark (already noted on #227) avoids this.
- `SphinxViewBuilder` is the stock `JSONHTMLBuilder` with `name='json'` plus a rendered `toctree` fragment. It writes one `.fjson` per page and a `globalcontext.json` [dsv-src builders.py]. `DocumentationView` reads files from one fixed `json_build_dir` and tries `<path>index.fjson`, then `<path>.fjson`. Otherwise it raises 404 [dsv-src views.py:13-31]. It has **no notion of language** [dsv-src; dsv-doc does not mention i18n]. (26.1 also leaves two `print()` debug calls in `get_doc_json`.)
- The JSON body uses **relative links**, for example `href="src/etl-pipelines/"` and `#heading-…` [exp]. The same build therefore works under any URL prefix, including a language prefix.

## 2. How Sphinx gettext i18n works (the mechanism behind option A)

1. `sphinx-build -b gettext` extracts every translatable node into `.pot` catalogs [sphinx-intl-doc].
2. `sphinx-intl update -p _build/gettext -l <lang>` creates or merges `locales/<lang>/LC_MESSAGES/*.po` [intl-qs; exp].
3. `sphinx-build -D language=<lang>` builds the translated output. `gettext_auto_build=True` (the default) compiles `.po` to `.mo` with Babel during the build [sphinx-conf; sphinx-src builders/__init__.py:254, util/i18n.py:94-110]. **No `sphinx-intl build` or `msgfmt` step is needed** [exp: the `.mo` files appeared after a plain `sphinx-build`].

MyST-specific findings:
- msgids are the **MyST source text**, for example `The **ETL Pipelines** tab …` and `[Who can do what](#heading-etl-pipelines-access)` [exp].
- The translated msgstr is re-parsed with the **same parser as the source file**. `_publish_msgstr` picks the parser through `get_filetype(config.source_suffix, source_path)` [sphinx-src transforms/i18n.py:51-90]. A Markdown msgstr containing `**bold**` and a `[link](#label)` rendered as `<strong>` and a resolved internal reference [exp]. Translators write Markdown, not rST.
- Sphinx's own UI strings are translated too. The headerlink title became "Länk till denna rubrik", and `globalcontext.json` carries `"language": "sv"` [exp].
- `gettext_compact` defaults to `True`, which gives one catalog per top-level directory (`src.pot`, `index.pot`) [sphinx-conf; exp]. sphinx-intl recommends `gettext_compact = False`, which gives one `.po` per page [intl-qs].
- Images: `figure_language_filename` (default `{root}.{language}{ext}`) swaps in per-language figures when they exist [sphinx-conf].

### Fallback for untranslated content (option A)
- Fallback works **per message (paragraph, heading or table cell)**, not per page. An empty msgstr marks the node `translated=False` and leaves the source text in place [sphinx-src transforms/i18n.py:437-440, 519]. With 5 of 91 messages translated, the Swedish build had every page, with translated headings and paragraphs mixed with English ones [exp].
- A language build therefore **always contains every page**. A missing page cannot 404.
- Stale translations cannot leak. When the English text changes, the msgid changes, so the old msgstr no longer matches and the paragraph falls back to English. `sphinx-intl update` keeps the old entry as *fuzzy*, and fuzzy entries are ignored unless `gettext_allow_fuzzy_translations=True` [sphinx-conf; sphinx-src].
- Mixed-language pages can be flagged. `translation_progress_classes` (Sphinx 7.1 or later) adds `translated`/`untranslated` CSS classes, and `|translation progress|` gives per-page statistics [sphinx-intl-doc; sphinx-conf; sphinx-src transforms/i18n.py:648-680].

## 3. Options compared

| | **A. gettext `.po` (sphinx-intl)** | **B. Per-language source trees** | **C. Suffix files in one tree** (`page.sv.md`) |
|---|---|---|---|
| Source of truth | One English MyST tree plus `locales/<lang>/LC_MESSAGES/*.po` | One full MyST tree per language, each with its own `conf.py` setting `language` | One tree, with language variants as sibling files |
| Sphinx support | First-class, documented workflow [sphinx-intl-doc] | Plain Sphinx: N independent projects | Not supported. The toctree/glob would pick up every variant, and it needs a custom extension or excludes |
| MyST | msgids and msgstrs are Markdown and are parsed by MyST [exp] | Native | Native |
| Untranslated fallback | Automatic, per paragraph, and never stale (§2) | None. A missing page 404s, so Django must fall back to the English build per page. A stale page silently shows outdated text, with no drift detection | Would need custom logic |
| Structure drift | None. Every language has the English toctree, labels and anchors | Trees diverge (pages, labels, anchors), which breaks deep links and context help | Partial |
| Translator workflow | Standard PO tooling (Weblate, Poedit, Transifex through sphinx-intl) | Edit Markdown directly; easy for prose rewrites | Edit Markdown |
| Build output | One JSON dir per (manual, language) | Same | One dir, needs custom routing |
| Extra deps | sphinx-intl as a **dev-only** dependency (used for `update`). Babel is already present | None | Custom code |

Other options considered and rejected:
- **Runtime translation in Django** (translating the fjson body with Django gettext) cannot work: the body is prebuilt HTML, not message IDs.
- **Machine translation at request time** is out of scope, because #227 excludes producing translations.
- **Hybrid A+B** (gettext by default, plus a whole-page override that ships a translated `.md` for a single language) is possible later with Sphinx `exclude_patterns`/`tags`. Nothing needs it now.

## 4. Composition with django-sphinx-view and Django's active language

`DocumentationView` takes one `json_build_dir` [dsv-src]. Every option therefore needs a **thin subclass** that chooses the directory per request:

```python
class ManualView(DocumentationView):
    manual: str  # "user" | "technical"
    def get_doc_json(self):  # sketch
        active = to_locale(get_language())            # "sv", "pt_BR", "en_US"
        default = to_locale(settings.LANGUAGE_CODE)   # "en_US"
        for lang in dict.fromkeys([active, active.split("_")[0], default, default.split("_")[0]]):
            self.json_build_dir = BUILD_ROOT / self.manual / lang
            try:
                return super().get_doc_json()
            except Http404:
                continue
        raise Http404
```

- **Layout:** `documentation/builds/<manual>/<lang>/` for JSON, with a per-language doctree dir (`-d …/<lang>/.doctrees`).
- **Language code mapping:** Django uses `en-us` and `pt-br`, while Sphinx and gettext use `en` and `pt_BR`. `django.utils.translation.to_locale()` handles the case and separator, and the lookup should try the full locale and then the base language before falling back to `settings.LANGUAGE_CODE`.
- **Active language:** nothing activates a language yet (§1). There are two ways to do it:
  - Add `LocaleMiddleware` and `LANGUAGES` but no `i18n_patterns`. URLs stay `/manuals/user/…`, and the language comes from the session/cookie or `Accept-Language`. `LocaleMiddleware` adds `Vary: Accept-Language`. This matches the rest of the app, whose URLs are not prefixed.
  - Use `i18n_patterns` (`/sv/manuals/user/…`). This also works, because fjson links are relative (§1), but it would be the only prefixed part of the app.
- **Fallback layers:**
  - With A, missing paragraphs fall back inside Sphinx.
  - With A or B, a language with no build at all falls back to the English dir in the view.
  - With B, individual missing pages also fall back through the same view loop, but outdated pages are not detected.
- The `base.html` shell should set `<html lang>` from the active language. The page `title`, `body`, `toc` and `toctree` are already in the target language.

## 5. Build-time cost

These numbers come from the current user manual (2 pages, 91 messages) on a laptop [exp]:

| Step | Time |
|---|---|
| `sphinx-build -b gettext` (extraction, dev-time only) | 0.53 s |
| English JSON build | 0.68 s |
| Swedish JSON build (includes compiling `.po` to `.mo`) | 0.75 s |
| Incremental rebuild, no changes | 0.68 s |
| Switching `language` with a **shared** doctree dir | full re-read, because `language` is an `env`-level config and `[config changed ('language')]` invalidates the environment |

- The cost is one full `sphinx-build` per (manual × language), and it grows linearly with the number of languages. Options A and B cost about the same. A only adds `.mo` compilation, which takes milliseconds.
- In the Docker image build, the step is a loop over manuals and languages with separate `-d` doctree dirs. There is no extraction and no sphinx-intl. `-j auto` is possible because sphinx_view declares `parallel_read_safe` [dsv-src __init__.py:17-20].
- `.pot` extraction and `sphinx-intl update` run only when translators refresh catalogs, in a dev or CI job. Commit the `.po` files and gitignore the `.mo` files.

## 6. Recommendation

**Option A: gettext `.po` via sphinx-intl, one English MyST source tree per manual.**

- It gives automatic, never-stale, per-paragraph English fallback, and every language build has every page.
- It keeps one structure, so toctrees, labels and anchors match across languages. That keeps deep links and context help stable (see #227, not yet specified).
- MyST works end to end: translators see Markdown msgids and write Markdown msgstrs.
- There is no runtime dependency. sphinx-intl is dev-only, and Babel is already installed.
- Build cost is one `sphinx-build` per manual and language, which is negligible today.

Concrete plumbing for the spec (#231):
1. In each manual's `conf.py`: `locale_dirs = ["locales/"]`, `gettext_compact = False`, and optionally `translation_progress_classes = "untranslated"`. Also remove the recommonmark import and `source_parsers`.
2. Add `sphinx-intl` to the dev dependency group, with a `make`/script target for `gettext` plus `sphinx-intl update -l <lang>`.
3. In the Docker build, loop over manual × `MANUAL_LANGUAGES` to produce `documentation/builds/<manual>/<lang>/` with per-language doctrees. Start with `en` only.
4. Add a `DocumentationView` subclass that resolves `<manual>/<to_locale(get_language())>`, then the base language, then `LANGUAGE_CODE`.
5. On the Django side, add `LANGUAGES` and `LocaleMiddleware` (no `i18n_patterns`) when a second language arrives. The view works unchanged with only English.

Revisit B only if a language needs whole-page rewrites instead of translation. Even then, prefer the per-page hybrid (§3) over full parallel trees.
