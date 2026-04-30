from datetime import timedelta

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone

from tasks.registry import register_task


@register_task("index_skill_discovery_embedding")
def index_skill_discovery_embedding(version_id: str, force: bool = False):
    from apps.skills.discovery import index_skill_version

    indexed = index_skill_version(version_id, force=force)
    return str(indexed.id) if indexed else None


def _staleness_email_html(
    skill_title: str,
    department_name: str,
    workspace_name: str,
    days_stale: int | None,
    skill_url: str,
) -> str:
    return render_to_string(
        "email/staleness_alert.html",
        {
            "skill_title": skill_title,
            "department_name": department_name,
            "workspace_name": workspace_name,
            "days_stale": days_stale,
            "skill_url": skill_url,
        },
    ).strip()


def _staleness_email_text(
    skill_title: str,
    department_name: str,
    workspace_name: str,
    days_stale: int | None,
    skill_url: str,
) -> str:
    return render_to_string(
        "email/staleness_alert.txt",
        {
            "skill_title": skill_title,
            "department_name": department_name,
            "workspace_name": workspace_name,
            "days_stale": days_stale,
            "skill_url": skill_url,
        },
    ).strip()


STALENESS_BATCH_SIZE = 200


@register_task("staleness_check")
def staleness_check():
    from django.db.models import OuterRef, Subquery

    from apps.orgs.models import FK_SETTINGS_FIELDS
    from apps.skills.enums import StatusChoices
    from apps.skills.models import Skill
    from apps.usage.models import UsageEvent

    last_used_sq = (
        UsageEvent.objects.filter(skill=OuterRef("pk"))
        .order_by("-called_at")
        .values("called_at")[:1]
    )
    published = (
        Skill.objects.filter(status=StatusChoices.PUBLISHED)
        .select_related("department__team")
        .annotate(last_used_at=Subquery(last_used_sq))
    )

    from tasks import task_backend

    now = timezone.now()
    settings_caches: dict = {}

    for skill in published.iterator(chunk_size=STALENESS_BATCH_SIZE):
        ws_id = skill.department.team.workspace_id
        team_id = skill.department.team_id
        dept_id = skill.department_id

        if ws_id not in settings_caches:
            settings_caches[ws_id] = _build_settings_index(
                ws_id,
                FK_SETTINGS_FIELDS,
            )

        settings_index = settings_caches[ws_id]
        rule = _resolve_staleness_rule(settings_index, ws_id, team_id, dept_id)
        if rule is None:
            continue

        cutoff = now - timedelta(days=rule.period_days)
        is_stale = skill.last_used_at is None or skill.last_used_at < cutoff
        if is_stale:
            task_backend.enqueue("send_staleness_alert", skill_id=str(skill.id))


def _resolve_staleness_rule(settings_index, ws_id, team_id, dept_id):
    for key in [
        (ws_id, team_id, dept_id),
        (ws_id, team_id, None),
        (ws_id, None, None),
    ]:
        row = settings_index.get(key)
        if row and row.staleness_alert_id is not None:
            return row.staleness_alert
    return None


def _build_settings_index(workspace_id, fk_fields):
    """Fetch all CoreSettings rows for a workspace (every scope level)."""
    from apps.orgs.models import CoreSettings

    all_settings = list(
        CoreSettings.objects.filter(workspace_id=workspace_id).select_related(*fk_fields)
    )
    return {(s.workspace_id, s.team_id, s.department_id): s for s in all_settings}


@register_task("send_staleness_alert")
def send_staleness_alert(skill_id: str):
    from apps.orgs.enums import RoleChoices
    from apps.orgs.models import FK_SETTINGS_FIELDS, CoreSettings, Membership
    from apps.skills.models import Skill

    try:
        skill = Skill.objects.select_related("owner", "department__team__workspace").get(
            id=skill_id
        )
    except Skill.DoesNotExist:
        return

    dept = skill.department
    team = dept.team
    workspace = team.workspace

    # Resolve effective staleness alert rule for this skill's scope
    from django.db.models import Q

    scope_filter = (
        Q(workspace=workspace, team__isnull=True, department__isnull=True)
        | Q(workspace=workspace, team=team, department__isnull=True)
        | Q(workspace=workspace, team=team, department=dept)
    )
    all_settings = list(
        CoreSettings.objects.filter(scope_filter).select_related(*FK_SETTINGS_FIELDS)
    )
    settings_index = {(s.workspace_id, s.team_id, s.department_id): s for s in all_settings}

    rule = None
    for key in [
        (workspace.id, team.id, dept.id),
        (workspace.id, team.id, None),
        (workspace.id, None, None),
    ]:
        row = settings_index.get(key)
        if row and row.staleness_alert_id is not None:
            rule = row.staleness_alert
            break

    if rule is None:
        return

    # Collect recipient emails
    recipient_emails: set[str] = set()

    if rule.notify_admins:
        for m in Membership.objects.filter(
            workspace=workspace, role=RoleChoices.ADMIN
        ).select_related("user"):
            if m.user.email:
                recipient_emails.add(m.user.email)

    if rule.notify_team_managers:
        for m in Membership.objects.filter(
            workspace=workspace, team=team, role=RoleChoices.TEAM_MANAGER
        ).select_related("user"):
            if m.user.email:
                recipient_emails.add(m.user.email)

    if rule.notify_skill_owner and skill.owner and skill.owner.email:
        recipient_emails.add(skill.owner.email)

    if not recipient_emails:
        return

    from apps.usage.models import UsageEvent

    last_usage = UsageEvent.objects.filter(skill=skill).order_by("-called_at").first()
    days_stale = None if last_usage is None else (timezone.now() - last_usage.called_at).days

    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173")
    from apps.orgs.models import CoreSlug, EntityType

    try:
        ws_slug = CoreSlug.objects.get(
            entity_type=EntityType.WORKSPACE, entity_id=workspace.id
        ).slug
    except CoreSlug.DoesNotExist:
        ws_slug = str(workspace.id)

    skill_url = f"{frontend_url}/{ws_slug}/skills/{skill.id}"

    from apps.common.email_service import get_email_backend

    backend = get_email_backend()
    for email in recipient_emails:
        backend.send(
            to=email,
            subject=f"[Koinoflow] Stale skill: {skill.title}",
            html=_staleness_email_html(
                skill_title=skill.title,
                department_name=dept.name,
                workspace_name=workspace.name,
                days_stale=days_stale,
                skill_url=skill_url,
            ),
            text=_staleness_email_text(
                skill_title=skill.title,
                department_name=dept.name,
                workspace_name=workspace.name,
                days_stale=days_stale,
                skill_url=skill_url,
            ),
            from_email=settings.ALERTS_FROM_EMAIL,
        )
