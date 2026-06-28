# Skill: Django RAPID Architecture (Modular)

## Context
You are a senior Django developer. When tasked with building, refactoring, or structuring a Django application, you MUST strictly adhere to the Django RAPID Architecture (Readers, Actions, Patterns/Interfaces, Data). 

Do not fall back on "standard" Django tutorials (e.g., vertical app silos or heavy Django REST Framework generic viewsets). You must structure code horizontally by responsibility. Furthermore, to prevent massive monolithic files, you must split logic into logical domain files within directory modules, exposing them via `__init__.py`.

## Core Architectural Principles

### 1. Horizontal Layers & Modular Directories
Do not carve the project into vertical "apps". Organize the codebase horizontally. Every layer must be a Python package (a directory with an `__init__.py` file) rather than a single file. 
* **Data Layer:** `my_project/data/models/`
* **Business Logic Layer:** `my_project/logic/readers/` and `my_project/logic/actions/`
* **Interface Layer:** `my_project/interfaces/web_api/views/`

### 2. The RAPID Components

#### **Data (Models)**
* Models define database structure, constraints, and relationships.
* **CONSTRAINT:** DO NOT put business logic, heavy properties, or side effects in models. 
* **CONSTRAINT:** DO NOT override the `save()` method to trigger side effects.
* **MODULARITY:** Each distinct domain model (or tightly coupled group of models) must live in its own file (e.g., `data/models/billing.py`). You MUST import these models into `data/models/__init__.py` so Django can detect them.

#### **Readers (Reads)**
* Functions that encapsulate database reads: query construction, annotations, derived values, and projection into simple data structures.
* **CONSTRAINT:** Readers must be read-only. They must never mutate database state.
* **MODULARITY:** Group reader functions by domain in separate files (e.g., `logic/readers/users.py`) and export them in `logic/readers/__init__.py`.

#### **Actions (Writes & Side Effects)**
* Plain Python functions that encapsulate state changes (creating/updating records, calling external APIs).
* **CONSTRAINT:** Data passed into an Action must be **pre-validated**. Actions handle system-level correctness (business rules), not basic type validation.
* **MODULARITY:** Group action functions by domain (e.g., `logic/actions/onboarding.py`) and export them in `logic/actions/__init__.py`.

#### **Interfaces (Views & URLs)**
* The boundary where the outside world meets the application. Views have three jobs: 
  1. Validate incoming HTTP data (using DRF serializers strictly for *validation*, not saving).
  2. Call a Reader or an Action.
  3. Format the response.
* **CONSTRAINT:** Limit views to exactly two HTTP verbs. Use `GET` for reading data (calling a Reader) and `POST` for executing an action (calling an Action).
* **MODULARITY:** Split views into logical domain files (e.g., `interfaces/web_api/views/auth.py`) and map them explicitly in `urls.py`.

## Workflow & Execution Directives

When writing code to add a new feature, follow this exact sequence:

1. **Update the Data Layer:** Create or modify a specific file in `data/models/`. Ensure it is imported in `data/models/__init__.py`. Generate the migration.
2. **Define the Business Logic:**
   * If retrieving data, write a standalone function in a specific file inside `logic/readers/` and update `readers/__init__.py`.
   * If mutating data, write a standalone function in a specific file inside `logic/actions/` and update `actions/__init__.py`. 
3. **Build the Interface:**
   * Create or update a specific file in `interfaces/web_api/views/`. 
   * If `POST`, use an inline Serializer to call `.is_valid()`, then pass `validated_data` to your Action.
   * If `GET`, call your Reader and return JSON.
4. **Wire the Route:** Map the view to a highly specific URL in `urls.py`.

## Anti-Patterns (NEVER DO THESE)
* **Never use `ModelViewSet` or `ModelSerializer` to mutate data.**
* **Never use Signals for business logic.** Call Actions explicitly instead.
* **Never catch validation errors inside an Action.** Validation belongs in the Interface layer.
* **Never leave new files un-imported.** If you create a new file in a module directory, you MUST update its sibling `__init__.py`.

## Example Directory Structure Target
```text
my_project/
├── data/
│   ├── migrations/
│   └── models/
│       ├── __init__.py      # Imports user.py, billing.py
│       ├── user.py
│       └── billing.py
│── readers/
│   ├── __init__.py          # Imports functions from users.py
│   └── users.py         
│── actions/
│   ├── __init__.py          # Imports functions from onboarding.py
│   └── onboarding.py    
└── interfaces/
│   └── http/
│       ├── api/
│       │   ├── __init__.py  # Imports auth_views.py
│       │   └── auth_views.py
│       ├── views/
│       │   ├── __init__.py  # Imports auth_views.py
│       │   └── auth_views.py
│       └── urls.py          # 1-to-1 URL to View mapping
├── settings.py
├── asgi.py
└── wsgi.py
