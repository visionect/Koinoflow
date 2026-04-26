from django.apps import AppConfig


class SkillsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.skills"

    def ready(self):
        import apps.skills.tasks  # noqa: F401
