"""
Root pytest configuration.

The settings module connects to Vault at import time to fetch encryption
keys.  For local test runs (no Vault available) we inject deterministic
fallback keys so that the application can be exercised without an external
dependency.  When Vault *is* available (CI / Docker) the real keys are used.
"""
import os

# Provide fallback encryption keys when Vault is not reachable so that
# `manage.py` / `pytest` can start in a local dev/test environment.
os.environ.setdefault("MIRES_FERNET_KEY", "EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc=")
os.environ.setdefault("MIRES_SENSITIVE_DATA_HASH_KEY", "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA=")