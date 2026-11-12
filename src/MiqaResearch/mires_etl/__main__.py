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
        exit_code = run_r_sandbox(root).exit_code
    else:
        exit_code = run_sandbox(root).exit_code
    copy_image_manifest(root / contract.OUTPUT_DIRNAME)
    return exit_code


def copy_image_manifest(output_dir: Path) -> None:
    """Copy the image's baked package manifest into `output_dir` (#413). Written after the Script
    ran, so a Script cannot forge it; silently skipped when the file is absent (dev runs)."""
    from . import contract

    source = Path(os.environ.get("MIRES_ETL_PACKAGES_FILE", contract.IMAGE_PACKAGES_PATH))
    try:
        content = source.read_bytes()
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / contract.PACKAGES_FILENAME).write_bytes(content)
    except OSError:
        pass


if __name__ == "__main__":
    sys.exit(main())
