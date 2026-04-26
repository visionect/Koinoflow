from django.contrib import admin

from .models import UsageEvent


@admin.register(UsageEvent)
class UsageEventAdmin(admin.ModelAdmin):
    list_display = ("skill", "version_number", "client_type", "client_id", "called_at")
    list_filter = ("client_type",)
