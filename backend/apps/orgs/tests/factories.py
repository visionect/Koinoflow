from datetime import timedelta

import factory
from django.utils import timezone

from apps.orgs.enums import EntityType, InvitationStatus, RoleChoices
from apps.orgs.models import (
    ApiKey,
    CoreSettings,
    CoreSlug,
    Department,
    Membership,
    PendingInvitation,
    SkillAuditRule,
    StalenessAlertRule,
    Team,
    Workspace,
)


class WorkspaceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Workspace

    name = factory.Sequence(lambda n: f"Workspace {n}")
    slug = factory.Sequence(lambda n: f"workspace-{n}")

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        slug = kwargs.pop("slug", None)
        obj = model_class.objects.create(**kwargs)
        if slug:
            CoreSlug.objects.create(
                entity_type=EntityType.WORKSPACE,
                entity_id=obj.id,
                slug=slug,
            )
        return obj


class MembershipFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Membership

    user = factory.SubFactory("apps.accounts.tests.factories.UserFactory")
    workspace = factory.SubFactory(WorkspaceFactory)
    role = RoleChoices.ADMIN


class TeamFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Team

    workspace = factory.SubFactory(WorkspaceFactory)
    name = factory.Sequence(lambda n: f"Team {n}")
    slug = factory.Sequence(lambda n: f"team-{n}")

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        slug = kwargs.pop("slug", None)
        obj = model_class.objects.create(**kwargs)
        if slug:
            CoreSlug.objects.create(
                entity_type=EntityType.TEAM,
                entity_id=obj.id,
                slug=slug,
                scope_workspace=obj.workspace,
            )
        return obj


class DepartmentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Department

    team = factory.SubFactory(TeamFactory)
    name = factory.Sequence(lambda n: f"Department {n}")
    slug = factory.Sequence(lambda n: f"department-{n}")

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        slug = kwargs.pop("slug", None)
        obj = model_class.objects.create(**kwargs)
        if slug:
            CoreSlug.objects.create(
                entity_type=EntityType.DEPARTMENT,
                entity_id=obj.id,
                slug=slug,
                scope_team=obj.team,
            )
        return obj


class SkillAuditRuleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SkillAuditRule

    workspace = factory.SubFactory(WorkspaceFactory)
    period_days = 90


class StalenessAlertRuleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = StalenessAlertRule

    workspace = factory.SubFactory(WorkspaceFactory)
    period_days = 30
    notify_admins = True
    notify_team_managers = False
    notify_skill_owner = True


class CoreSettingsFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CoreSettings

    workspace = factory.SubFactory(WorkspaceFactory)
    skill_audit = factory.SubFactory(
        SkillAuditRuleFactory,
        workspace=factory.SelfAttribute("..workspace"),
    )


class PendingInvitationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PendingInvitation

    workspace = factory.SubFactory(WorkspaceFactory)
    email = factory.Faker("email")
    role = RoleChoices.MEMBER
    invited_by = factory.SubFactory("apps.accounts.tests.factories.UserFactory")
    token = factory.LazyFunction(PendingInvitation.generate_token)
    status = InvitationStatus.PENDING
    expires_at = factory.LazyFunction(lambda: timezone.now() + timedelta(days=7))


class ApiKeyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ApiKey
        exclude = ["_generated"]

    _generated = factory.LazyFunction(ApiKey.generate)
    workspace = factory.SubFactory(WorkspaceFactory)
    label = factory.Sequence(lambda n: f"Key {n}")
    key_hash = factory.LazyAttribute(lambda o: o._generated[1])
    key_prefix = factory.LazyAttribute(lambda o: o._generated[2])
