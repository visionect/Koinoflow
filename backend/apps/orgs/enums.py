from django.db import models


class PlanChoices(models.TextChoices):
    TRIAL = "trial", "Trial"
    STARTER = "starter", "Starter"
    GROWTH = "growth", "Growth"
    ENTERPRISE = "enterprise", "Enterprise"


class RoleChoices(models.TextChoices):
    ADMIN = "admin", "Admin"
    TEAM_MANAGER = "team_manager", "Team Manager"
    MEMBER = "member", "Member"


class EntityType(models.TextChoices):
    WORKSPACE = "workspace"
    TEAM = "team"
    DEPARTMENT = "department"


class InvitationStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ACCEPTED = "accepted", "Accepted"
    EXPIRED = "expired", "Expired"
    CANCELLED = "cancelled", "Cancelled"
