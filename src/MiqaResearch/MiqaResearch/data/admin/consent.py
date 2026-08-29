from django.contrib import admin
from unfold.admin import ModelAdmin

from MiqaResearch.data.models import ParticipantConsent


@admin.register(ParticipantConsent)
class ParticipantConsentAdmin(ModelAdmin):
    list_display = ("clinic", "consent_type", "study_participant", "status", "consent_signed_date", "consent_revoked_date")
    list_display_links = ("clinic", "consent_type", "study_participant", "status", "consent_signed_date", "consent_revoked_date")
    list_filter = ("consent_type", "clinic", "status")
    search_fields = ("study_participant__id",)
    readonly_fields = ("id", "study_participant", "status","consent_signed_date", "last_updated", "consent_revoked_date")

    class Meta:
        model = ParticipantConsent
