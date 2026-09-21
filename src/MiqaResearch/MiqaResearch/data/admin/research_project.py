from django.contrib import admin
from unfold.admin import ModelAdmin

from MiqaResearch.data.models import ResearchProject, ResearchProjectRole, ResearchProjectUserRoleMap
from MiqaResearch.data.models.research_project import ResearchProjectClinicMap


@admin.register(ResearchProject)
class ResearchProjectAdmin(ModelAdmin):
    list_display = ("name", "description",)
    list_display_links = ("name", "description",)
    list_filter = ("name",)
    search_fields = ("name", "description")

    class Meta:
        model = ResearchProject


@admin.register(ResearchProjectRole)
class ResearchProjectRoleAdmin(ModelAdmin):
    list_display = ("name", "description", "created_at", "updated_at", "deleted_at")
    list_display_links = ("name", "description",  "created_at", "updated_at", "deleted_at")
    list_filter = ("name",)
    search_fields = ("name", "description")
    readonly_fields = ("created_at", "updated_at",)

    class Meta:
        model = ResearchProjectRole


@admin.register(ResearchProjectUserRoleMap)
class ResearchProjectUserRoleMapAdmin(ModelAdmin):
    list_display = ("user", "project", "role",)
    list_display_links = ("user", "project", "role",)
    list_filter = ("project", "role")
    search_fields = ("user", "project",)

    class Meta:
        model = ResearchProjectUserRoleMap


@admin.register(ResearchProjectClinicMap)
class ResearchProjectClinicMapAdmin(ModelAdmin):
    list_display = ("project", "clinic",)
    list_display_links = ("project", "clinic",)
    list_filter = ("project", "clinic")
    search_fields = ("project", "clinic",)

    class Meta:
        model = ResearchProjectClinicMap