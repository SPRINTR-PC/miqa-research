from asgiref.sync import async_to_sync
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import reverse
from unfold.admin import ModelAdmin

from MiqaResearch.actions.etl.exceptions import EtlLocationInUse
from MiqaResearch.actions.etl.sources import create_location_grant, delete_location_grant
from MiqaResearch.data.models import (
    EtlJob,
    EtlJobInput,
    EtlLocationGrant,
    EtlPendingGroup,
    EtlProcessedFile,
    EtlProjectSettings,
    EtlScript,
    EtlScriptVersion,
    EtlSourceLocation,
    PipelineBinding,
)


@admin.register(EtlScript)
class EtlScriptAdmin(ModelAdmin):
    list_display = ("name", "origin", "project", "archived_at")
    list_filter = ("origin",)
    search_fields = ("name",)

    class Meta:
        model = EtlScript


@admin.register(EtlScriptVersion)
class EtlScriptVersionAdmin(ModelAdmin):
    list_display = ("script", "version", "sha256", "created_at")
    list_filter = ("script",)
    search_fields = ("sha256",)

    class Meta:
        model = EtlScriptVersion


@admin.register(PipelineBinding)
class PipelineBindingAdmin(ModelAdmin):
    list_display = ("project", "source_bucket", "source_prefix", "raw_retention", "raw_bucket", "raw_prefix")
    list_filter = ("project", "raw_retention")
    search_fields = ("source_bucket", "source_prefix")

    class Meta:
        model = PipelineBinding


@admin.register(EtlJob)
class EtlJobAdmin(ModelAdmin):
    list_display = ("binding", "status", "raw_retention", "started_at", "finished_at", "created_at")
    list_filter = ("status", "raw_retention", "binding")

    class Meta:
        model = EtlJob


@admin.register(EtlJobInput)
class EtlJobInputAdmin(ModelAdmin):
    list_display = ("job", "bucket", "key", "source_status", "cleanup_attempts", "source_handled_at")
    list_filter = ("job", "source_status")
    search_fields = ("bucket", "key")

    class Meta:
        model = EtlJobInput


@admin.register(EtlProcessedFile)
class EtlProcessedFileAdmin(ModelAdmin):
    list_display = ("binding", "bucket", "key", "first_seen_at")
    list_filter = ("binding",)
    search_fields = ("bucket", "key")

    class Meta:
        model = EtlProcessedFile


@admin.register(EtlProjectSettings)
class EtlProjectSettingsAdmin(ModelAdmin):
    list_display = ("project", "log_retention_days", "max_script_source_bytes")
    list_filter = ("project",)

    class Meta:
        model = EtlProjectSettings


@admin.register(EtlLocationGrant)
class EtlLocationGrantAdmin(ModelAdmin):
    """Same rules as the Sources section (#268), through the same actions: adds and deletes are
    audited, a grant a Source Location or Binding needs isn't deleted, and an existing grant's
    project/bucket/prefix are fixed (delete and re-add instead). No bulk delete, which would skip
    the check."""
    list_display = ("project", "bucket", "prefix")
    list_filter = ("project",)
    search_fields = ("bucket", "prefix")

    def get_readonly_fields(self, request, obj=None):
        return ("project", "bucket", "prefix") if obj else ()

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    def save_model(self, request, obj, form, change):
        if change:
            return
        created = async_to_sync(create_location_grant)(
            project=obj.project, user=request.user, request=request, bucket=obj.bucket, prefix=obj.prefix)
        obj.pk = created.pk

    def delete_view(self, request, object_id, extra_context=None):
        if request.method != "POST":
            return super().delete_view(request, object_id, extra_context)
        grant = self.get_object(request, object_id)
        if grant is None or not self.has_delete_permission(request, grant):
            return super().delete_view(request, object_id, extra_context)
        try:
            async_to_sync(delete_location_grant)(project=grant.project, user=request.user, request=request, grant=grant)
        except EtlLocationInUse as error:
            self.message_user(request, str(error), messages.ERROR)
            return HttpResponseRedirect(reverse("admin:data_etllocationgrant_change", args=[object_id]))
        self.message_user(request, "The location grant was deleted.", messages.SUCCESS)
        return HttpResponseRedirect(reverse("admin:data_etllocationgrant_changelist"))

    class Meta:
        model = EtlLocationGrant


@admin.register(EtlSourceLocation)
class EtlSourceLocationAdmin(ModelAdmin):
    """Read-only (#268): Source Locations are managed in the ETL tab's Sources section, which keeps
    each one inside a grant of its own project and audits every change."""
    list_display = ("name", "project", "bucket", "prefix")
    list_filter = ("project",)
    search_fields = ("name", "bucket", "prefix")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    class Meta:
        model = EtlSourceLocation


@admin.register(EtlPendingGroup)
class EtlPendingGroupAdmin(ModelAdmin):
    list_display = ("binding", "group_key", "last_seen_at")
    list_filter = ("binding",)
    search_fields = ("group_key",)

    class Meta:
        model = EtlPendingGroup
