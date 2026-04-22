from django.apps import AppConfig


class UsageConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.usage"

    def ready(self):
        import apps.usage.tasks  # noqa: F401
