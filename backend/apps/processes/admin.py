from django.contrib import admin

from .models import Process, ProcessVersion, VersionFile


@admin.register(Process)
class ProcessAdmin(admin.ModelAdmin):
    list_display = ("title", "department", "status", "owner", "created_at")
    list_filter = ("status",)
    search_fields = ("title", "slug")


class VersionFileInline(admin.TabularInline):
    model = VersionFile
    extra = 0
    readonly_fields = ("path", "file_type", "size_bytes", "is_deleted")
    fields = ("path", "file_type", "size_bytes", "is_deleted")


@admin.register(ProcessVersion)
class ProcessVersionAdmin(admin.ModelAdmin):
    list_display = ("process", "version_number", "authored_by", "created_at")
    list_filter = ("process",)
    inlines = [VersionFileInline]


@admin.register(VersionFile)
class VersionFileAdmin(admin.ModelAdmin):
    list_display = ("path", "version", "file_type", "size_bytes", "is_deleted")
    list_filter = ("file_type", "is_deleted")
    search_fields = ("path",)
    raw_id_fields = ("version",)
