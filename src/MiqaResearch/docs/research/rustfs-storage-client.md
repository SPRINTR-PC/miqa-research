# S3-compatible storage client library options for RustFS (issue #108)

Research for [issue #108](../../../../issues/108) ("Research: S3-compatible storage client library
options for RustFS"), part of the storage wayfinder map [issue #98](../../../../issues/98).
**Recommendation-only** — no application code, templates, or dependencies were added as part of this
ticket.

## 0. Starting facts (confirmed by direct inspection, 2026-09-17)

- `src/MiqaResearch/docker-compose.dev-test.yml` already runs RustFS as service `mires_fs`
  (`image: rustfs/rustfs:latest`), publishing `9000:9000` (S3 API) and `9001:9001` (console), with
  `RUSTFS_ACCESS_KEY=MiresAccessKey` / `RUSTFS_SECRET_KEY=MiresSecretKey`.
- `src/MiqaResearch/pyproject.toml` lists Django `==6.0.*` (`requires-python = ">=3.14"`) and has
  **no** `boto3`, `django-storages`, or `minio` dependency. There is no `STORAGES` setting anywhere in
  the codebase — Django is on the implicit default local-filesystem storage.
- The app stores DICOM files, including whole-slide pathology images that can be multi-GB, so
  streaming reads/writes and presigned URLs (to avoid proxying large payloads through a Django worker)
  are first-order concerns, not nice-to-haves.

## 1. Options investigated

### 1a. `django-storages` — `S3Storage` (formerly `S3Boto3Storage`) pointed at a custom `endpoint_url`

[django-storages' current docs](https://django-storages.readthedocs.io/en/latest/backends/amazon-S3.html)
document the Amazon S3 backend as `storages.backends.s3.S3Storage` (the class was renamed from
`S3Boto3Storage` in django-storages 1.14; `S3Boto3Storage` remains as a deprecated alias in recent
releases). It wraps `boto3` internally and is built to point at any S3-compatible endpoint via the
`endpoint_url` option, which the docs describe as the "Custom S3 URL to use when connecting to S3,
including scheme" — exactly the RustFS use case (`http://mires_fs:9000` in compose, `http://localhost:9000`
from the host). The docs explicitly recommend also setting `region_name` alongside a custom `endpoint_url`
"to avoid authorization query parameter errors."

This is the path of least resistance: one well-known, actively maintained third-party dependency, a
`STORAGES` dict, and no custom code to write or maintain. It is also the same backend most Django/S3
tutorials and Stack Overflow answers assume, so community troubleshooting is abundant.

### 1b. Raw `boto3` in a bespoke `django.core.files.storage.Storage` subclass

[Django's own storage docs](https://docs.djangoproject.com/en/stable/ref/files/storage/) describe the
`Storage` base class contract: a custom backend implements `_open()`, `_save()`, `exists()`, `delete()`,
`size()`, `url()`, plus optional `listdir()` / `get_*_time()` methods, and is wired in via
`STORAGES["default"]["BACKEND"] = "app.storage.MyStorage"`. Writing this by hand against `boto3`
(`boto3.client("s3", endpoint_url=..., ...)`) gives full control over exactly which S3 calls are made
(useful if RustFS needs workarounds — see §4) but means owning file existence checks, name collision
handling, presigned URL generation, and streaming upload/download logic that `django-storages` already
provides and has hardened over many releases. For a research-stage project this is more surface area to
maintain for no compatibility benefit over 1a, since both ultimately call the same `boto3` S3 client.

### 1c. `minio` (official MinIO Python SDK)

The [minio-py README](https://github.com/minio/minio-py/blob/master/README.md) documents `presigned_get_object`,
`presigned_put_object`, and `presigned_post_policy` for presigned URLs, and `put_object`/`fput_object` /
`get_object` for object transfer. Critically, **minio-py is not a Django `Storage` backend** — it is a
bare S3-compatible client library, the same category as `boto3` itself. Using it from Django means writing
the same custom `Storage` subclass work as option 1b (§1b), just calling `minio` methods instead of
`boto3` methods. Third-party Django wrappers exist (`django-minio-storage`, `django-minio-backend`), but
they add a second bespoke dependency layer on top of a second S3 client library, for no capability that
`django-storages`/`boto3` lacks. `django-minio-storage`'s own docs concede the practical case for
minio-py's existence is that the boto3-based adapters were "hard to configure" for MinIO — a friction
`django-storages`' explicit `endpoint_url`/`addressing_style`/`signature_version` options have since
addressed directly.

### 1d. Other candidates found

- **`django-rustfs`** (<https://github.com/CasualEngineerZombie/django-rustfs>, PyPI package `django-rustfs`,
  latest release `0.3.0`) is a RustFS-specific Django storage backend, pitched as needing "four core
  settings versus 10+" for `django-storages`. It is very young: 1 GitHub star, 0 forks, only two PyPI
  releases (`0.2.0`, `0.3.0`) at research time. Its own README roadmap lists **multipart upload and
  streaming responses as future/planned work, not implemented today** — a direct problem for this
  project's multi-GB whole-slide-image files. Not viable for production use yet; worth re-checking if it
  matures, but not now.
- **Plain `botocore`** without `boto3` — no practical benefit over `boto3` for this use case; `boto3` is
  the maintained, documented, high-level SDK and is what `django-storages` already depends on.
- **RustFS's own SDK guidance**: RustFS's [Python SDK guide](https://docs.rustfs.com/en/developer/sdk/python)
  states plainly that "RustFS ships no first-party SDKs — it is S3-compatible, so you use the official AWS
  SDK for Python, Boto3, configured to point at your RustFS server." `minio-py` is not mentioned anywhere
  in RustFS's own docs. RustFS's guide's example client config: `endpoint_url='http://localhost:9000'`
  (port 9000, not the 9001 console port), `region_name='us-east-1'`, and
  `Config(signature_version='s3v4', s3={'addressing_style': 'path'})`.

## 2. `STORAGES` configuration example (Django 6.0, django-storages + boto3)

```python
# settings.py
STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": env("RUSTFS_DICOM_BUCKET", default="mires-dicom"),
            "access_key": env("RUSTFS_ACCESS_KEY"),
            "secret_key": env("RUSTFS_SECRET_KEY"),
            "endpoint_url": env("RUSTFS_ENDPOINT_URL", default="http://mires_fs:9000"),
            "region_name": "us-east-1",
            "addressing_style": "path",     # RustFS's own SDK guide recommends path-style
            "signature_version": "s3v4",    # SigV4; RustFS claims early SigV2+SigV4 support, but
                                             # SigV4 is what every modern boto3/aws-cli default sends
            "querystring_auth": True,       # generate presigned URLs from .url()
            "querystring_expire": 3600,     # presigned URL TTL, seconds
            "file_overwrite": False,
        },
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}
```

Notes from the docs:

- `region_name` should always accompany a custom `endpoint_url`, per the django-storages docs, "to avoid
  authorization query parameter errors."
- `signature_version` defaults to SigV4 (`s3v4`) in django-storages/boto3; set it to `"s3"` only if a
  target explicitly needs legacy SigV2 — not needed for RustFS, which supports SigV4.
- `AWS_S3_MAX_MEMORY_SIZE`/`transfer_config` OPTIONS keys exist to tune the boto3 `TransferConfig` used
  under the hood (multipart threshold/chunksize, max concurrency) — relevant directly to large
  whole-slide-image handling, see §3.

## 3. Presigned URLs and large-file streaming

- **Presigned URLs**: `django-storages`' `S3Storage.url()` generates a presigned URL automatically when
  `querystring_auth=True` (the default), using boto3's `generate_presigned_url` under the hood — no extra
  code needed to hand a browser or a worker a direct-to-RustFS URL instead of proxying bytes through
  Django. `minio-py` exposes the same capability more explicitly via `presigned_get_object`/
  `presigned_put_object` (["minio-py README"](https://github.com/minio/minio-py/blob/master/README.md)),
  but only if a bespoke `Storage` subclass is written around it (§1c).
- **Streaming, not buffering, large files**: boto3's [S3 upload guide](https://docs.aws.amazon.com/boto3/latest/guide/s3-uploading-files.html)
  documents `upload_fileobj()`/`download_fileobj()` as streaming a file-like object in chunks rather than
  loading it fully into memory, and internally uses `boto3.s3.transfer.TransferConfig` to control the
  multipart threshold and part size for large objects — this is exactly the mechanism needed for
  multi-GB whole-slide images. `django-storages`' `S3Storage` uses this same boto3 transfer machinery for
  `_save()`/`_open()`, so large-file streaming is inherited "for free" rather than something this project
  has to hand-roll. A hand-rolled `boto3` or `minio-py` backend (§1b/§1c) would need to reimplement
  correct chunked/multipart handling itself to get the same behavior.
- **Multipart correctness against RustFS specifically is the actual risk**, independent of which client
  library is chosen — see §4. Multiple RustFS bugs found below are in the multipart/checksum path, which
  any of boto3, django-storages, or minio-py would hit identically since they all ultimately speak the
  same S3 multipart wire protocol to the same server.

## 4. RustFS compatibility — sourced findings

RustFS's own [GitHub README](https://github.com/rustfs/rustfs) describes itself as "S3-compatible,"
"strictly adhere[ing] to S3 API standards," and "an early adopter of the S3 API (V2 and V4)" — i.e. it
claims both SigV2 and SigV4 signature support. RustFS's docs reference an external
`docs/architecture/s3-compatibility-matrix.md` / `docs.rustfs.com/features/s3-compatibility/` page
distinguishing "✅ Available (shipped, CI-gated)" vs "🧪 Preview (opt-in/bounded)" features, **but that
page returned HTTP 404 when fetched during this research (2026-09-17)**, so its detailed feature-by-feature
contents could not be directly verified — treat the matrix's existence as documented but its current
contents as unconfirmed.

What *is* directly verifiable is RustFS's own GitHub issue tracker (`rustfs/rustfs`), which shows a
recurring, actively-being-fixed pattern of S3-compatibility gaps specifically in the checksum/multipart/
presigned-URL area — exactly the area this project's large DICOM uploads depend on:

- **[#3506](https://github.com/rustfs/rustfs/issues/3506)** (RustFS `1.0.0-beta.8`, June 2026): multipart
  uploads carrying the AWS SDK's now-default flexible checksum (CRC32/CRC64NVME) failed with
  `500 InternalError: checksum mismatch`, while the same upload succeeded either as a single-part PUT or
  with the checksum explicitly disabled (`AWS_REQUEST_CHECKSUM_CALCULATION=when_required`). The report
  notes this affects any AWS-SDK-default client — "`aws-cli` (≥2.23), `aws-sdk-go-v2`, `boto3` (≥1.36) for
  large objects." Closed (fixed) the same month.
- **[#4800](https://github.com/rustfs/rustfs/issues/4800)**: AWS's newer additional-checksum algorithms
  (XXHash3/64/128, CRC32C, CRC64NVME) were **silently dropped** — `PutObject` returned `200 OK` but
  `head_object` returned no checksum at all, "a trap" per the reporter, moving ~10 GB files. Addressed via
  **[#4805](https://github.com/rustfs/rustfs/issues/4805)** ("add native S3 additional checksum support").
- **[#7678](https://github.com/rustfs/rustfs/issues/7678)** (RustFS `1.0.0-rc.6`, reported 2026-09-11):
  presigned `UploadPart` requests with a signed `x-amz-checksum-sha256` query parameter returned
  `500 InternalError`; removing the checksum (falling back to CRC32) succeeded. Fixed via
  **[PR #7748](https://github.com/rustfs/rustfs/pull/7748)**, merged **2026-09-14** — three days before
  this research was written, underscoring how fast-moving and recently-rough this specific edge is.
- **[#1731](https://github.com/rustfs/rustfs/issues/1731)**: the .NET SDK's multipart uploads failed with
  checksum validation enabled unless the whole stream was buffered into memory first (i.e. made seekable);
  workaround was `DisableDefaultChecksumValidation = true`. Reported Feb 2026, closed (fixed) April 2026 —
  the same class of bug as #3506/#7678 but for a different SDK, suggesting the underlying multipart
  checksum handling has been a repeated soft spot across client ecosystems, not a boto3-only quirk.
- **[#7853](https://github.com/rustfs/rustfs/issues/7853)**: concurrent `UploadPart` requests at default
  client concurrency (`aws-cli` default: 10 concurrent 8 MB parts) failed intermittently with
  `503 ServiceUnavailable` on objects as small as ~1 GiB (found via Harbor's S3 registry driver pushing
  Docker image layers, and reproduced with plain `aws-cli`). Serializing part uploads
  (`s3.max_concurrent_requests=1`) was a reliable workaround. Closed 2026-09-14.
- **[#3374](https://github.com/rustfs/rustfs/issues/3374)**: SigV2 presigned URL verification was broken
  in RustFS `alpha.91+` due to an `x-amz-request-id` header injection bug — a concrete counterexample to
  treating RustFS's "SigV2 support" claim as unconditionally solid; closed (fixed).
- No evidence either way was found on RustFS's handling of `django-storages`-specific code paths (no
  GitHub issues mention `django-storages` by name), nor a working, current `minio-py`-against-RustFS bug
  report — the compatibility signal that exists is almost entirely from `aws-cli`/`boto3`/`aws-sdk-go-v2`/
  `aws-sdk-rust`/.NET SDK users, which is the same underlying wire protocol both `django-storages` and a
  hand-rolled `boto3` backend would use.

**Pattern to take away**: RustFS is genuinely S3-compatible for the common path (basic PUT/GET/multipart
without flexible checksums, presigned URLs without a signed checksum in the query string), but its
handling of AWS's *newer* opt-in flexible-checksum features (the ones recent `boto3`/AWS-SDK versions
increasingly enable by default) has been a recurring source of bugs, several fixed only in the last few
months and one merged three days before this research. This is a moving target, not a settled one — expect
to re-verify against whatever RustFS version is pinned in `docker-compose.dev-test.yml` at implementation
time, and to test actual multi-GB multipart uploads against it directly rather than trusting the
compatibility claim alone.

## 5. Recommendation

**Use `django-storages`' `S3Storage` backend (boto3-based) pointed at RustFS via `endpoint_url`, with
explicit `region_name="us-east-1"`, `addressing_style="path"`, and `signature_version="s3v4"`** (§2).

Rationale:

- It is the only option of the four that requires **zero new code to write or maintain** — a `STORAGES`
  dict plus environment-driven credentials/endpoint. Both the raw-`boto3`-custom-backend (§1b) and
  `minio-py`-custom-backend (§1c) paths mean hand-implementing and maintaining `Storage._save`/`_open`/
  `url()`/presigned-URL/multipart-streaming logic that `django-storages` already has and has hardened
  across many releases, for no S3-compatibility benefit — RustFS's documented and observed compatibility
  gaps (§4) are in the *server's* handling of the multipart/checksum wire protocol, which is identical
  regardless of which Python client library sends the requests.
- It gets streaming large-file support (`upload_fileobj`/`download_fileobj`, boto3 `TransferConfig`) "for
  free" (§3) — directly relevant to multi-GB whole-slide images — and presigned URLs via `.url()` with no
  extra code, letting large DICOM transfers go client-to-RustFS directly instead of proxying through a
  Django worker process.
- `django-rustfs` (§1d) is not viable yet: its own roadmap admits multipart/streaming aren't implemented,
  which is disqualifying for this project's largest files.
- `minio-py` offers no capability `django-storages`/`boto3` lacks for this project, and RustFS's own docs
  point developers at `boto3`, not `minio-py`, as the client to use.

**Caveat to carry into implementation**: given the concentration of real, recently-fixed RustFS bugs
specifically around *flexible checksums on multipart uploads and presigned `UploadPart` requests*
(§4), the implementation ticket should (a) pin/record the exact RustFS image tag or digest used in
`docker-compose.dev-test.yml` rather than trusting `:latest`, since fixes for this exact class of bug have
landed as recently as three days before this research, and (b) include an explicit test that performs a
real multipart upload of a multi-hundred-MB+ file against the dev-test RustFS container before relying on
it for whole-slide-image storage, since the compatibility matrix page itself could not be verified
directly (§4) and boto3's checksum-calculation default (`when_supported`, which sends CRC64NVME/CRC32 by
default in modern SDK versions) is exactly the trigger condition seen in #3506 and #7678.

## Sources

- django-storages Amazon S3 backend docs (`S3Storage`, `endpoint_url`, `region_name`, `signature_version`,
  `querystring_auth`/`querystring_expire`): https://django-storages.readthedocs.io/en/latest/backends/amazon-S3.html
- Django `Storage` base class / custom storage backend docs: https://docs.djangoproject.com/en/stable/ref/files/storage/
- minio-py README (presigned URL methods, `put_object`/`fput_object`): https://github.com/minio/minio-py/blob/master/README.md
- django-minio-storage docs (rationale for minio-py over boto3-based adapters for MinIO): https://django-minio-storage.readthedocs.io/
- django-rustfs repository (maturity, roadmap gaps): https://github.com/CasualEngineerZombie/django-rustfs
- django-rustfs PyPI release history (`0.2.0`, `0.3.0`): https://pypi.org/pypi/django-rustfs/json
- RustFS GitHub repository / README (S3 compatibility claims, SigV2/SigV4, protocol support): https://github.com/rustfs/rustfs
- RustFS S3 compatibility matrix page (returned HTTP 404 at research time, 2026-09-17): https://docs.rustfs.com/features/s3-compatibility/
- RustFS Python SDK guide (recommends boto3, example endpoint/signature config): https://docs.rustfs.com/en/developer/sdk/python
- RustFS issue #3506 — multipart + default checksum fails on beta.8: https://github.com/rustfs/rustfs/issues/3506
- RustFS issue #4800 — additional checksums silently dropped: https://github.com/rustfs/rustfs/issues/4800
- RustFS issue #4805 — native S3 additional checksum support added: https://github.com/rustfs/rustfs/issues/4805
- RustFS issue #7678 — presigned UploadPart with signed SHA256 checksum returns 500: https://github.com/rustfs/rustfs/issues/7678
- RustFS PR #7748 — fix for presigned UploadPart checksum queries, merged 2026-09-14: https://github.com/rustfs/rustfs/pull/7748
- RustFS issue #1731 — .NET SDK multipart + checksum validation failure: https://github.com/rustfs/rustfs/issues/1731
- RustFS issue #7853 — concurrent UploadPart 503 at default client concurrency (found via Harbor): https://github.com/rustfs/rustfs/issues/7853
- RustFS issue #3374 — SigV2 presigned URL verification broken in alpha.91+: https://github.com/rustfs/rustfs/issues/3374
- boto3 S3 upload guide (`upload_fileobj`, `TransferConfig`, streaming behavior): https://docs.aws.amazon.com/boto3/latest/guide/s3-uploading-files.html
- Repo files inspected directly: `src/MiqaResearch/pyproject.toml`, `src/MiqaResearch/docker-compose.dev-test.yml`
