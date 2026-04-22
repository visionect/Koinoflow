from django.apps import AppConfig


class ConnectorsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.connectors"

    def ready(self):
        import apps.connectors.tasks  # noqa: F401
