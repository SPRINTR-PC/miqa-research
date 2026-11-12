"""The sandbox container's actual entrypoint (#161): `python -m mires_etl [root]`.
Runs the Python shim, or -- in the R image, which sets `MIRES_ETL_SHIM_LANGUAGE=r` -- the R shim
(#166), which drives `Rscript` itself and validates its rows here.

Runs after `ComposeSandboxBackend` (or a future Kubernetes backend, #165) has staged
`manifest.json` + `script.py` + `input/` under `root` (default `/sandbox`, matching
`etl_sandbox.Dockerfile`) via the runner's own I/O staging -- never a bind mount. This package is
Django-free (#412), so there is no app setup: nothing here ever opens a database connection, matching
the sandbox's network-less, DB-less contract (see `context.py`).
"""
import os
import sys
from pathlib import Path


def main() -> int:
    from . import contract
    from .r_shim import run_r_sandbox
    from .shim import run_sandbox

    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/sandbox")
    if os.environ.get("MIRES_ETL_SHIM_LANGUAGE", contract.LANGUAGE_PYTHON) == contract.LANGUAGE_R:
        return run_r_sandbox(root).exit_code
    return run_sandbox(root).exit_code


if __name__ == "__main__":
    sys.exit(main())
