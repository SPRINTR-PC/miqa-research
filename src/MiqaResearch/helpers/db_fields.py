import hashlib
import hmac
import logging

from cryptography.fernet import Fernet, InvalidToken

from django.conf import settings
from django.db import models

logger = logging.getLogger(__name__)


def get_fernet():
    """Initialises the Fernet cipher using a key from Django Settings"""
    if not hasattr(settings, "FERNET_KEY"):
        raise ValueError("FERNET_KEY is not set in settings")
    return Fernet(settings.FERNET_KEY)


def get_deterministic_hash(value):
    """Generates a deterministic SHA-256 hash using the ... key from settings as salt."""
    salt = settings.SENSITIVE_DATA_HASH_KEY.encode("utf-8")
    return hmac.new(salt, value.encode("utf-8"), hashlib.sha256).hexdigest()


class SearchableEncryptedCharField(models.CharField):
    description = "A searchable encrypted character field, encrypted using Fernet and a deterministic hash for searchability."

    def __init__(self, *args, **kwargs):
        self.hash_field_name = kwargs.pop("hash_field_name", None)

        kwargs["max_length"] = kwargs.get("max_length", 500)
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        if self.hash_field_name:
            kwargs["hash_field_name"] = self.hash_field_name
        return name, path, args, kwargs

    def contribute_to_class(self, cls, name, private_only=False):
        """
        This method is called when the model class is constructed. Here, it's used to dynamically add the hash field to
        the model.
        """
        super().contribute_to_class(cls, name, private_only)

        self.hash_field_name = self.hash_field_name or f"{name}_hash"

        # Prevent adding the dynamically added hash-field during the migration as Django's makemigrations will have
        # already added the field and included it in the migration file
        if cls.__module__ == "__fake__":
            return

        # Avoid adding the field if it already exists (e.g. explicitly defined in the model)
        if any(f.name == self.hash_field_name for f in cls._meta.local_fields):
            return

        hash_field = models.CharField(
            max_length=64,
            blank=True,
            null=True,
            db_index=True,
            editable=False,  # Prevents the field from showing up in admin or model forms
        )
        cls.add_to_class(self.hash_field_name, hash_field)

    def pre_save(self, model_instance, add):
        plaintext_value = getattr(model_instance, self.attname)

        if plaintext_value is not None:
            hashed_value = get_deterministic_hash(plaintext_value)
            setattr(model_instance, self.hash_field_name, hashed_value)
        else:
            setattr(model_instance, self.hash_field_name, None)

        return plaintext_value

    def get_prep_value(self, value):
        """Encrypts the plaintext right before it is inserted into the INSERT/UPDATE statement"""
        if value is None or value == "":
            return value

        fernet = get_fernet()
        encrypted_bytes = fernet.encrypt(value.encode("utf-8"))
        return encrypted_bytes.decode("utf-8")

    def from_db_value(self, value, expression, connection):
        """Decrypts the ciphertext as it is pulled out of the database."""
        if value is None or value == "":
            return value

        fernet = get_fernet()
        try:
            decrypted_bytes = fernet.decrypt(value.encode("utf-8"))
            return decrypted_bytes.decode("utf-8")
        except InvalidToken:
            # Return a failsafe value in case the key changed or data was corrupted
            logger.error(f"Failed to decrypt value: {value}. Returning failsafe value", exc_info=True)
            return "[DECRYPTION_ERROR]"
