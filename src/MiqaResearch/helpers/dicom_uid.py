import hashlib
import secrets

from django.db import transaction

from MiqaResearch.data.models import ResearchProject

# DICOM UID cap (PS3.5 6.2) and the UUID-derived-UID root (PS3.5 Annex B)
_DICOM_UID_MAX_LENGTH = 64
_UUID_DERIVED_UID_ROOT = "2.25."


def hash_uid(uid: str, salt: str) -> str:
    """Deterministically pseudonymize a DICOM UID for a salt (CTP-style HashUID).

    Returns "2.25." followed by the decimal digits of the big-integer value of
    SHA256(uid + salt), with a leading-zero guard and the 64-character UID cap.
    """
    digest = hashlib.sha256((uid + salt).encode("utf-8")).digest()
    digits = str(int.from_bytes(digest, "big"))
    if digits[0] == "0":
        digits = "1" + digits
    return (_UUID_DERIVED_UID_ROOT + digits)[:_DICOM_UID_MAX_LENGTH]


def get_or_create_hashuid_salt_key(research_project: ResearchProject) -> str:
    """Return the project's HashUID salt key, generating and persisting it on first use.

    The key is never rotated afterwards: rotating it would silently break
    duplicate-detection and study/series/instance linkage for everything already
    pseudonymized under the old key.
    """
    with transaction.atomic():
        project = ResearchProject.objects.select_for_update().get(pk=research_project.pk)
        if not project.dicom_hashuid_salt_key:
            project.dicom_hashuid_salt_key = secrets.token_hex(32)
            project.save(update_fields=["dicom_hashuid_salt_key"])
        research_project.dicom_hashuid_salt_key = project.dicom_hashuid_salt_key
        return project.dicom_hashuid_salt_key


def pseudonymize_uid(uid: str, research_project: ResearchProject) -> str:
    """Deterministically pseudonymize a DICOM UID for a Research Project (HashUID)."""
    return hash_uid(uid, get_or_create_hashuid_salt_key(research_project))
