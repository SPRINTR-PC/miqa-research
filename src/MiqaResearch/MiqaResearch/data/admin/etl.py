from django.contrib import admin
from unfold.admin import ModelAdmin

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
    list_display = ("project", "bucket", "prefix")
    list_filter = ("project",)
    search_fields = ("bucket", "prefix")

    class Meta:
        model = EtlLocationGrant


@admin.register(EtlSourceLocation)
class EtlSourceLocationAdmin(ModelAdmin):
    list_display = ("name", "project", "bucket", "prefix")
    list_filter = ("project",)
    search_fields = ("name", "bucket", "prefix")
    # Bucket/prefix are fixed once created (#268): Bindings copied them.
    readonly_fields = ("bucket", "prefix")

    def get_readonly_fields(self, request, obj=None):
        return self.readonly_fields if obj else ()

    class Meta:
        model = EtlSourceLocation


@admin.register(EtlPendingGroup)
class EtlPendingGroupAdmin(ModelAdmin):
    list_display = ("binding", "group_key", "last_seen_at")
    list_filter = ("binding",)
    search_fields = ("group_key",)

    class Meta:
        model = EtlPendingGroup
