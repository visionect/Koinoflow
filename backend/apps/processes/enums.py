from django.db import models


class StatusChoices(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"


class VisibilityChoices(models.TextChoices):
    DEPARTMENT = "department", "Department"
    TEAM = "team", "Team"
    WORKSPACE = "workspace", "Workspace"
