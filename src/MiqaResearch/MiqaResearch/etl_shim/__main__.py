"""The sandbox container's actual entrypoint (#161): `python -m MiqaResearch.etl_shim [root]`.

Runs after `ComposeSandboxBackend` (or a future Kubernetes backend, #165) has staged
`manifest.json` + `script.py` + `input/` under `root` (default `/sandbox`, matching
`etl_sandbox.Dockerfile`) via the runner's own I/O staging -- never a bind mount. `django.setup()`
runs first because `run_sandbox`'s own import graph (`etl_datatypes` -> `data.models`) needs the
Django app registry ready; nothing here ever opens a database connection, matching the sandbox's
network-less, DB-less contract (see `etl_shim/context.py`).
"""
import os
import sys
from pathlib import Path


def main() -> int:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "MiqaResearch.settings")
    import django
    django.setup()

    from .shim import run_sandbox

    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/sandbox")
    return run_sandbox(root).exit_code


if __name__ == "__main__":
    sys.exit(main())
