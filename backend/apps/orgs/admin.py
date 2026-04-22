from django.contrib import admin

from .models import (
    ApiKey,
    CoreSettings,
    CoreSlug,
    Department,
    FeatureFlag,
    Membership,
    ProcessAuditRule,
    Team,
    Workspace,
    WorkspaceFeatureFlag,
)


@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "workspace", "role", "created_at")
    list_filter = ("role",)


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "workspace", "created_at")
    search_fields = ("name",)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "team", "owner", "created_at")
    search_fields = ("name",)


@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    list_display = ("label", "key_prefix", "workspace", "is_active", "created_at")
    list_filter = ("is_active",)


@admin.register(CoreSlug)
class CoreSlugAdmin(admin.ModelAdmin):
    list_display = ("entity_type", "slug", "entity_id", "created_at")
    list_filter = ("entity_type",)
    search_fields = ("slug",)


@admin.register(ProcessAuditRule)
class ProcessAuditRuleAdmin(admin.ModelAdmin):
    list_display = ("workspace", "period_days", "created_at")


@admin.register(CoreSettings)
class CoreSettingsAdmin(admin.ModelAdmin):
    list_display = ("workspace", "team", "department", "created_at")
    list_filter = (
        "require_review_before_publish",
        "enable_version_history",
        "enable_api_access",
        "allow_agent_process_updates",
    )


@admin.register(FeatureFlag)
class FeatureFlagAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)


@admin.register(WorkspaceFeatureFlag)
class WorkspaceFeatureFlagAdmin(admin.ModelAdmin):
    list_display = ("workspace", "flag", "created_at")
    list_filter = ("flag",)
    search_fields = ("workspace__name", "flag__name")
