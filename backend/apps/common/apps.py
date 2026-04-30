from django.apps import AppConfig


class CommonConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.common"

    def ready(self):
        # Run critical settings validation on startup.
        # This can be disabled by setting VALIDATE_CRITICAL_SETTINGS = False
        # in local.py (after importing base).
        from django.conf import settings

        if getattr(settings, "VALIDATE_CRITICAL_SETTINGS", True):
            from config.settings.base import _validate_critical_settings

            _validate_critical_settings()
