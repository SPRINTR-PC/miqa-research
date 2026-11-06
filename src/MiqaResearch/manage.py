#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MiqaResearch.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc

    # Add custom functionality to ignore directories in collectstatic
    if 'collectstatic' in sys.argv:
        try:
            import django
            from django.conf import settings
            django.setup()
            ignore_dirs = getattr(settings, 'STATIC_ROOT_IGNORES', [])
            for ignore_dir in ignore_dirs:
                if '--ignore' not in sys.argv or ignore_dir not in sys.argv:
                    sys.argv.extend(['--ignore', ignore_dir])
        except Exception:
            # Fallback if settings are not yet loaded or other issues
            pass

    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
