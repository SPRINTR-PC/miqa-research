---
name: django-rapid-architecture
description: Django RAPID architecture (Readers, Actions, Interfaces, Data) for the MiqaResearch Django project in src/MiqaResearch. Use when building, refactoring, or structuring Django code there — models, readers, actions, views, URLs. Not for .NET or other non-Django code.
---

# Django RAPID Architecture

Scope: `src/MiqaResearch/MiqaResearch/` only. Structure code horizontally by responsibility, not as vertical Django apps. No heavy DRF generic viewsets. Every layer is a package (directory + `__init__.py`), split into domain files and re-exported via `__init__.py`.

Before adding code, read the existing package for the domain and follow its conventions; read `GLOSSARY.md` for terminology.

## Layers

Current layout (match it; don't invent `logic/`):

- Data: `MiqaResearch/data/models/`
- Readers: `MiqaResearch/readers/`
- Actions: `MiqaResearch/actions/`
- Interfaces: `MiqaResearch/interfaces/http/` (views, API, `urls.py`)

### Data (models)
- Structure, constraints, relationships only.
- NO business logic, heavy properties, or side effects in models.
- NO `save()` overrides that trigger side effects.
- One domain model (or tightly coupled group) per file, e.g. `data/models/billing.py`. Import it in `data/models/__init__.py` so Django detects it.

### Readers (reads)
- Functions encapsulating DB reads: query construction, annotations, derived values, projection to simple data structures.
- Read-only. Never mutate DB state.
- Group by domain (`readers/users.py`), export in `readers/__init__.py`.

### Actions (writes and side effects)
- Plain functions for state changes: create/update records, external calls.
- Input must be pre-validated. Actions enforce business rules, not type validation.
- Group by domain (`actions/onboarding.py`), export in `actions/__init__.py`.

### Interfaces (views and URLs)
Views do exactly three things:
1. Validate incoming HTTP data (DRF serializers for validation only, never saving).
2. Call one Reader or Action.
3. Format the response.

- Two verbs only: `GET` calls a Reader, `POST` calls an Action.
- Split views by domain file; map explicitly in `urls.py`, one URL to one view.

## Workflow for a new feature

1. Data: add/modify a file in `data/models/`, import in `__init__.py`, generate migration.
2. Logic: read → function in `readers/<domain>.py`; write → function in `actions/<domain>.py`; update the sibling `__init__.py`.
3. Interface: add/update a view file. POST: inline serializer, `.is_valid()`, pass `validated_data` to the Action. GET: call the Reader, return the response.
4. Route: map the view to a specific URL in `urls.py`.

Use the `tdd` skill for the red-green loop; test Readers/Actions through their public functions.

## Anti-patterns

- `ModelViewSet` / `ModelSerializer` to mutate data.
- Signals for business logic. Call Actions explicitly.
- Catching validation errors inside an Action. Validation belongs in the Interface.
- New files left un-imported. Always update the sibling `__init__.py`.

## Target shape

```text
MiqaResearch/
├── data/
│   ├── migrations/
│   └── models/
│       ├── __init__.py      # imports user.py, billing.py
│       ├── user.py
│       └── billing.py
├── readers/
│   ├── __init__.py          # exports from users.py
│   └── users.py
├── actions/
│   ├── __init__.py          # exports from onboarding.py
│   └── onboarding.py
├── interfaces/
│   └── http/
│       ├── api/             # JSON endpoints
│       ├── views/           # HTML/HTMX views
│       └── urls.py          # 1-to-1 URL to view
├── settings.py
├── asgi.py
└── wsgi.py
```
