"""Settings for the local Playwright viewer harness (#278) only: dev settings + DEBUG + demo keys.

Without Vault, `settings.py` leaves FERNET_KEY/SENSITIVE_DATA_HASH_KEY unset, so DICOM ingestion
(UID pseudonymization) and WADO /metadata can't run. The harness uses its own database
(see .dev-data/webcomponents/browser-tests/harness-env.ts), so fixed demo keys are safe there.
Never use this module for anything but that harness: it refuses to load unless the harness sets
MIRES_VIEWER_HARNESS=1 and Vault is off (harness-env.ts), so pointing a deployment at it fails fast.
"""
import os

from django.core.exceptions import ImproperlyConfigured

if os.environ.get("MIRES_VIEWER_HARNESS") != "1" or os.environ.get("MIRES_USE_VAULT", "").lower() in ("1", "true"):
    raise ImproperlyConfigured("settings_viewer_harness is for the local Playwright viewer harness only")

from MiqaResearch.settings import *  # noqa: E402, F403

DEBUG = True
FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="
# The debug toolbar's handle sits over the viewer's inspector and intercepts clicks (#282).
DEBUG_TOOLBAR_CONFIG = {"SHOW_TOOLBAR_CALLBACK": lambda request: False}
