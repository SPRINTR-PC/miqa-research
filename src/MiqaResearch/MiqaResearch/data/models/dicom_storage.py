"""DicomFile's storage backend (#122): local disk by default, S3-compatible
object storage (RustFS or similar) when configured -- toggled by
settings.DICOM_STORAGE_BACKEND, used only by DicomFile.file.

Django resolves a FileField's ``storage=`` callable exactly once, when the
model class is defined (app-loading time), so a plain callable can't flip
mid-process. DicomStorage instead re-checks the setting on every operation by
delegating to a freshly built backend each call, so switching backends needs
neither a new migration (this proxy's deconstructed form never changes) nor a
process restart.

Not registered under settings.STORAGES["dicom"]: nothing else in the app
needs to look this storage up by name, and a STORAGES entry would still be
resolved once at startup like any other named storage, so it wouldn't help
with the per-call re-checking above.
"""
from datetime import UTC

from django.core.files.storage import FileSystemStorage, Storage
from django.utils.deconstruct import deconstructible


@deconstructible
class DicomStorage(Storage):
    def _backend(self) -> Storage:
        from django.conf import settings

        if settings.DICOM_STORAGE_BACKEND != "s3":
            return FileSystemStorage()

        from storages.backends.s3 import S3Storage

        kwargs: dict = {
            "bucket_name": settings.DICOM_S3_BUCKET,
            "signature_version": "s3v4",
        }
        if settings.DICOM_S3_REGION_NAME:
            kwargs["region_name"] = settings.DICOM_S3_REGION_NAME
        if settings.DICOM_S3_ACCESS_KEY_ID:
            kwargs["access_key"] = settings.DICOM_S3_ACCESS_KEY_ID
        if settings.DICOM_S3_SECRET_ACCESS_KEY:
            kwargs["secret_key"] = settings.DICOM_S3_SECRET_ACCESS_KEY
        if settings.DICOM_S3_ENDPOINT_URL:
            kwargs["endpoint_url"] = settings.DICOM_S3_ENDPOINT_URL
            # Path-style addressing: S3-compatible endpoints (RustFS et al.)
            # generally can't rely on virtual-hosted-style DNS wildcards.
            kwargs["addressing_style"] = "path"
        return S3Storage(**kwargs)

    def _open(self, name, mode="rb"):
        return self._backend()._open(name, mode)

    def _save(self, name, content):
        return self._backend()._save(name, content)

    def delete(self, name):
        return self._backend().delete(name)

    def exists(self, name):
        return self._backend().exists(name)

    def size(self, name):
        return self._backend().size(name)

    def url(self, name):
        return self._backend().url(name)

    def read_range(self, name: str, offset: int, length: int) -> bytes:
        """Read `length` bytes at `offset` of the stored file without fetching the rest (#274).

        Local disk: seek + read. S3: a ranged GET (django-storages' S3File would
        download the whole object on first read).
        """
        if length <= 0:
            return b""
        backend = self._backend()
        if isinstance(backend, FileSystemStorage):
            with open(backend.path(name), "rb") as fd:
                fd.seek(offset)
                return fd.read(length)
        from storages.utils import clean_name

        key = backend._normalize_name(clean_name(name))
        response = backend.bucket.Object(key).get(Range=f"bytes={offset}-{offset + length - 1}")
        return response["Body"].read()

    def iter_blobs(self, prefix: str = ""):
        """Yield `(name, size, last_modified)` for every blob whose name starts with `prefix` (#420).

        Streamed: S3 one list page at a time, local disk via `os.scandir`. `name` is the storage
        key (what `DicomFile.file.name` holds), `last_modified` is timezone-aware.
        """
        backend = self._backend()
        if isinstance(backend, FileSystemStorage):
            yield from self._iter_local(backend, prefix)
            return
        location = backend.location.strip("/")
        key_prefix = f"{location}/{prefix}" if location else prefix
        paginator = backend.connection.meta.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=backend.bucket_name, Prefix=key_prefix):
            for obj in page.get("Contents", []):
                name = obj["Key"][len(location) + 1:] if location else obj["Key"]
                yield name, obj["Size"], obj["LastModified"]

    @staticmethod
    def _iter_local(backend, prefix):
        import os
        from datetime import datetime

        root = backend.location
        directory, _, _ = prefix.rpartition("/")
        stack = [os.path.join(root, directory)]
        while stack:
            current = stack.pop()
            try:
                entries = list(os.scandir(current))
            except FileNotFoundError:
                continue
            for entry in entries:
                if entry.is_dir(follow_symlinks=False):
                    stack.append(entry.path)
                    continue
                name = os.path.relpath(entry.path, root).replace(os.sep, "/")
                if not name.startswith(prefix):
                    continue
                st = entry.stat()
                yield name, st.st_size, datetime.fromtimestamp(st.st_mtime, tz=UTC)

    def path(self, name):
        # Delegates to the local backend's implementation; the S3 backend's
        # base Storage.path() correctly raises NotImplementedError instead.
        return self._backend().path(name)
