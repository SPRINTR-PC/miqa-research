(heading-help-links)=
# Help Links

A **Help Link** is a "?" button (or an inline link) beside a feature in the app. It opens the
manual section that explains the feature in a new tab.

## Labels

Help Links point at a section by its label, never by its path, so the manual can be
reorganised without breaking them. Give the section a MyST label with the prefix
`app-<area>-<topic>`:

```md
(app-dashboard-overview)=
# The Dashboard
```

An `app-*` label is an API: don't rename or remove it while the app links to it.

`build_manuals.py` writes every label to `labels.json` (label → page, anchor, title) for each
manual and language. The English file decides which labels exist; the title of the active
language is used for the tooltip, falling back to English.

## Linking from the app

In a template:

```django
{% load manuals %}
{% manual_link "user" "app-dashboard-overview" %}
{% manual_link "user" "app-dashboard-overview" text="Read about the Dashboard" %}
```

In Python, `documentation.help_links.manual_url(request, "user", "app-dashboard-overview")`
returns the URL, or `None` when the user can't read that manual.

The link renders nothing for anonymous visitors and for users who can't read the manual (the
Technical Manual is for Superusers and Staff Users only). An unknown label raises in DEBUG; in
production it renders nothing and logs a warning.

## Checks

The `manuals`-marked tests build the manuals and check that every `manual_link` and
`manual_url` label in the app's templates and code exists in the English `labels.json`.
