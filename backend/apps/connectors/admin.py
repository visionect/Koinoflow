from django.contrib import admin

from apps.connectors.models import (
    CandidateSource,
    CaptureCandidate,
    ConnectorCredential,
    ExtractionJob,
    SyncedPage,
    SyncJob,
)


@admin.register(ConnectorCredential)
class ConnectorCredentialAdmin(admin.ModelAdmin):
    list_display = ("workspace", "provider", "site_url", "status", "connected_by", "created_at")
    list_filter = ("provider", "status")
    readonly_fields = ("id", "created_at", "updated_at")
    exclude = ("access_token", "refresh_token")


@admin.register(SyncJob)
class SyncJobAdmin(admin.ModelAdmin):
    list_display = (
        "credential",
        "job_type",
        "status",
        "pages_scanned",
        "pages_updated",
        "started_at",
        "finished_at",
    )
    list_filter = ("job_type", "status")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(SyncedPage)
class SyncedPageAdmin(admin.ModelAdmin):
    list_display = ("title", "credential", "space_key", "last_score", "last_synced_at")
    list_filter = ("credential__provider", "space_key")
    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "checksum",
        "extraction_checksum",
        "last_score",
    )
    search_fields = ("title",)


@admin.register(ExtractionJob)
class ExtractionJobAdmin(admin.ModelAdmin):
    list_display = (
        "credential",
        "status",
        "pages_scored",
        "pages_extracted",
        "candidates_created",
        "started_at",
        "finished_at",
    )
    list_filter = ("status",)
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(CaptureCandidate)
class CaptureCandidateAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "credential",
        "automation_tier",
        "probability_score",
        "status",
        "created_at",
    )
    list_filter = ("automation_tier", "status", "credential__provider")
    readonly_fields = ("id", "created_at", "updated_at", "promoted_skill")
    search_fields = ("title",)


@admin.register(CandidateSource)
class CandidateSourceAdmin(admin.ModelAdmin):
    list_display = ("candidate", "synced_page")
    readonly_fields = ("id", "created_at", "updated_at")
