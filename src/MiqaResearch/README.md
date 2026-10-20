# MiqaResearch

## Developers

### Consent fixture (dev/test data)
2000 fake participant consents, 10 clinics, 1 research project (`SPRiNTR`). Generator: `src/MiqaResearch/MiqaResearch/data/fixtures/consent_data.py`. Output: `consent_data.json` next to it.

Load (run from `src/MiqaResearch/`):

```{note}
If you are using the docker-compose setup for development, run the command without `uv run` from within the web-container.
```

```bash
uv run python manage.py loaddata consent_data.py
```

- The label is `consent_data.py` (the generator), not `.json`. The project's `loaddata` override regenerates `consent_data.json`, then loads it.
- Requires `MIRES_DEBUG=true`. Outside DEBUG it fails with `loaddata is disabled outside DEBUG`.
- Requires a reachable, migrated DB (`uv run python manage.py migrate`).
- Participant hash fields (`person_source_value_hash`, `name_hash`) use `SENSITIVE_DATA_HASH_KEY`, which is only set when `MIRES_USE_VAULT` is on. Without Vault, use the fixed dev key: `DJANGO_SETTINGS_MODULE=MiqaResearch.settings_viewer_harness uv run python manage.py loaddata consent_data.py`.
- The command rewrites the tracked `consent_data.json` (dates are relative to now), so a git diff afterwards is expected.
- Loading the committed JSON directly (`loaddata MiqaResearch/data/fixtures/consent_data.json`) skips regeneration: stale dates, hashes only if generated with a key. Still requires DEBUG.
- Regenerate JSON only, no DB: `uv run python MiqaResearch/data/fixtures/consent_data.py` (no hash key, so hash fields are omitted).
- In Docker, run the same `manage.py loaddata consent_data.py` inside the web container.
- Idempotency of re-running is unverified.