from django.db import models
from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password
import secrets

class BearerToken(models.Model):
    token_hash = models.CharField(max_length=255, unique=True, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bearer_tokens")
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "mires_bearer_token"
        verbose_name = "Bearer Token"
        verbose_name_plural = "Bearer Tokens"

    def __str__(self):
        return f"Token for {self.user.email} (created {self.created_at})"

    @classmethod
    def generate_token(cls, user):
        plain_token = secrets.token_urlsafe(32)
        token_hash = make_password(plain_token)
        instance = cls.objects.create(user=user, token_hash=token_hash)
        instance.plain_token = plain_token
        return instance

    def verify_token(self, plain_token):
        return check_password(plain_token, self.token_hash)
