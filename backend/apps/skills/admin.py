from django.contrib import admin

from .models import (
    Skill,
    SkillExecutionQuotaCounter,
    SkillExecutionRun,
    SkillExecutionSpec,
    SkillVersion,
    VersionFile,
)


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ("title", "department", "status", "execution_enabled", "owner", "created_at")
    list_filter = ("status", "execution_enabled")
    search_fields = ("title", "slug")


class VersionFileInline(admin.TabularInline):
    model = VersionFile
    extra = 0
    readonly_fields = ("path", "file_type", "size_bytes", "is_deleted")
    fields = ("path", "file_type", "size_bytes", "is_deleted")


@admin.register(SkillVersion)
class SkillVersionAdmin(admin.ModelAdmin):
    list_display = ("skill", "version_number", "authored_by", "created_at")
    list_filter = ("skill",)
    inlines = [VersionFileInline]


@admin.register(VersionFile)
class VersionFileAdmin(admin.ModelAdmin):
    list_display = ("path", "version", "file_type", "size_bytes", "is_deleted")
    list_filter = ("file_type", "is_deleted")
    search_fields = ("path",)
    raw_id_fields = ("version",)


@admin.register(SkillExecutionSpec)
class SkillExecutionSpecAdmin(admin.ModelAdmin):
    list_display = ("skill", "version", "runtime", "latency_class", "max_runs_per_day")
    list_filter = ("runtime", "latency_class", "network_policy")
    raw_id_fields = ("skill", "version")


@admin.register(SkillExecutionRun)
class SkillExecutionRunAdmin(admin.ModelAdmin):
    list_display = ("skill", "version", "status", "caller_type", "created_at", "finished_at")
    list_filter = ("status", "caller_type")
    search_fields = ("skill__slug", "external_job_name")
    raw_id_fields = ("workspace", "skill", "version", "spec", "department", "user", "agent")


@admin.register(SkillExecutionQuotaCounter)
class SkillExecutionQuotaCounterAdmin(admin.ModelAdmin):
    list_display = ("workspace", "skill", "day", "run_count")
    list_filter = ("day",)
    raw_id_fields = ("workspace", "skill")
