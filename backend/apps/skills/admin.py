from django.contrib import admin

from .models import Skill, SkillVersion, VersionFile


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ("title", "department", "status", "owner", "created_at")
    list_filter = ("status",)
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
