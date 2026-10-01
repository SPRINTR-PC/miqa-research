from django.core.checks import Warning

from documentation.manuals import MANUALS, SOURCE_LANGUAGE


def check_manual_builds(app_configs=None, **kwargs):
    """Warn when a registered manual has no English build to serve."""
    return [
        Warning(
            f"The {manual.title} has no English build at {manual.build_dir(SOURCE_LANGUAGE)}.",
            hint="Run `python documentation/build_manuals.py` (needs the `docs` uv group).",
            id="documentation.W001",
        )
        for manual in MANUALS.values()
        if not (manual.build_dir(SOURCE_LANGUAGE) / "index.fjson").is_file()
    ]
