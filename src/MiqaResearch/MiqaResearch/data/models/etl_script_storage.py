"""EtlScriptVersion's storage backend (#144): local disk by default, S3-compatible
object storage (RustFS or similar) when configured -- toggled by
settings.ETL_SCRIPT_STORAGE_BACKEND, used only by EtlScriptVersion.source.

Mirrors dicom_storage.DicomStorage's per-call backend resolution and the
reasoning behind it: Django resolves a FileField's ``storage=`` callable
exactly once, at model-class definition time, so a plain callable can't flip
mid-process. This re-checks the setting on every operation instead.
"""
from django.core.files.storage import FileSystemStorage, Storage
from django.utils.deconstruct import deconstructible


@deconstructible
class EtlScriptStorage(Storage):
    def _backend(self) -> Storage:
        from django.conf import settings

        if settings.ETL_SCRIPT_STORAGE_BACKEND != "s3":
            return FileSystemStorage()

        from storages.backends.s3 import S3Storage

        kwargs: dict = {
            "bucket_name": settings.ETL_SCRIPT_S3_BUCKET,
            "signature_version": "s3v4",
        }
        if settings.ETL_SCRIPT_S3_REGION_NAME:
            kwargs["region_name"] = settings.ETL_SCRIPT_S3_REGION_NAME
        if settings.ETL_SCRIPT_S3_ACCESS_KEY_ID:
            kwargs["access_key"] = settings.ETL_SCRIPT_S3_ACCESS_KEY_ID
        if settings.ETL_SCRIPT_S3_SECRET_ACCESS_KEY:
            kwargs["secret_key"] = settings.ETL_SCRIPT_S3_SECRET_ACCESS_KEY
        if settings.ETL_SCRIPT_S3_ENDPOINT_URL:
            kwargs["endpoint_url"] = settings.ETL_SCRIPT_S3_ENDPOINT_URL
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

    def path(self, name):
        return self._backend().path(name)
