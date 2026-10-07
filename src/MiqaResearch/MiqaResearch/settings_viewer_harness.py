"""Settings for the local Playwright viewer harness (#278) only: dev settings + DEBUG + demo keys.

Without Vault, `settings.py` leaves FERNET_KEY/SENSITIVE_DATA_HASH_KEY unset, so DICOM ingestion
(UID pseudonymization) and WADO /metadata can't run. The harness uses its own database
(see .dev-data/webcomponents/browser-tests/harness-env.ts), so fixed demo keys are safe there.
Never use this module for anything but that harness.
"""
from MiqaResearch.settings import *  # noqa: F403

DEBUG = True
FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="
