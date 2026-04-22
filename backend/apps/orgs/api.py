from datetime import timedelta

from django.db.models import Count, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from ninja import Field, Router, Schema, Status
from ninja.errors import HttpError

from apps.accounts.auth import api_or_session
from apps.accounts.permissions import check_dept_write, require_role
from apps.common.throttles import (
    AuthAnonThrottle,
    AuthUserThrottle,
    CreateAuthThrottle,
    InviteThrottle,
    MutationThrottle,
    ReadThrottle,
)
from apps.orgs.enums import EntityType, InvitationStatus, RoleChoices
from apps.orgs.models import (
    SETTINGS_FIELDS,
    CoreSettings,
    CoreSlug,
    Department,
    Membership,
    PendingInvitation,
    ProcessAuditRule,
    StalenessAlertRule,
    Team,
    Workspace,
    create_slug,
    get_effective_settings,
    resolve_slug,
    unique_slug,
)

router = Router(tags=["orgs"])


def _department_process_count_annotations():
    """Use subqueries to avoid cross-join inflation between FK and M2M counts.

    Each bucket excludes processes already counted in earlier buckets so the
    final sum (home + shared + team + workspace) has no double-counting.
    """
    from apps.processes.enums import VisibilityChoices
    from apps.processes.models import Process

    home_sq = (
        Process.objects.filter(department=OuterRef("pk"))
        .order_by()
        .values("department")
        .annotate(c=Count("*"))
        .values("c")
    )
    # Exclude processes whose home department is this one (already in home_sq)
    shared_sq = (
        Process.objects.filter(shared_with=OuterRef("pk"))
        .exclude(department_id=OuterRef("pk"))
        .order_by()
        .values("shared_with")
        .annotate(c=Count("*"))
        .values("c")
    )
    # Team-wide from sibling depts, excluding home (already done) AND
    # excluding processes explicitly shared with this dept (already in shared_sq)
    team_sq = (
        Process.objects.filter(
            visibility=VisibilityChoices.TEAM,
            department__team_id=OuterRef("team_id"),
        )
        .exclude(department_id=OuterRef("pk"))
        .exclude(shared_with=OuterRef("pk"))
        .order_by()
        .values("department__team_id")
        .annotate(c=Count("*"))
        .values("c")
    )
    # Workspace-wide from other depts, excluding home, shared, and team-wide
    # siblings (all already counted above)
    workspace_sq = (
        Process.objects.filter(
            visibility=VisibilityChoices.WORKSPACE,
            department__team__workspace_id=OuterRef("team__workspace_id"),
        )
        .exclude(department_id=OuterRef("pk"))
        .exclude(shared_with=OuterRef("pk"))
        .exclude(
            visibility=VisibilityChoices.TEAM,
            department__team_id=OuterRef("team_id"),
        )
        .order_by()
        .values("department__team__workspace_id")
        .annotate(c=Count("*"))
        .values("c")
    )
    return {
        "home_process_count": Coalesce(Subquery(home_sq[:1]), Value(0)),
        "shared_process_count": Coalesce(Subquery(shared_sq[:1]), Value(0)),
        "team_process_count": Coalesce(Subquery(team_sq[:1]), Value(0)),
        "workspace_process_count": Coalesce(Subquery(workspace_sq[:1]), Value(0)),
    }


# ── Schemas ──────────────────────────────────────────────────────────────


class UserBriefOut(Schema):
    id: str
    email: str
    first_name: str
    last_name: str


class CreateWorkspaceIn(Schema):
    name: str
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$", min_length=2, max_length=100)


class WorkspaceOut(Schema):
    id: str
    name: str
    slug: str
    created_at: str


class CreateTeamIn(Schema):
    name: str
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$", min_length=2, max_length=100)


class TeamOut(Schema):
    id: str
    name: str
    slug: str
    department_count: int
    created_at: str


class DepartmentOut(Schema):
    id: str
    name: str
    slug: str
    team_slug: str
    team_name: str
    owner: UserBriefOut | None
    process_count: int
    created_at: str


class TeamDetailOut(Schema):
    id: str
    name: str
    slug: str
    departments: list[DepartmentOut]
    created_at: str


class UpdateTeamIn(Schema):
    name: str | None = None


class CreateDepartmentIn(Schema):
    team_slug: str
    name: str
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$", min_length=2, max_length=100)
    owner_id: str | None = None


class UpdateDepartmentIn(Schema):
    name: str | None = None
    owner_id: str | None = None


class MemberOut(Schema):
    id: str
    email: str
    first_name: str
    last_name: str
    role: str
    team_id: str | None
    team_name: str | None
    department_ids: list[str]


class InviteMemberIn(Schema):
    email: str
    role: str
    team_id: str | None = None
    department_ids: list[str] = []


class InviteResponseOut(Schema):
    detail: str


class InvitationOut(Schema):
    id: str
    email: str
    role: str
    team_name: str | None
    department_names: list[str]
    invited_by_email: str | None
    status: str
    created_at: str
    expires_at: str


class TeamListOut(Schema):
    items: list[TeamOut]
    count: int


class DepartmentListOut(Schema):
    items: list[DepartmentOut]
    count: int


class MemberListOut(Schema):
    items: list[MemberOut]
    count: int


class InvitationListOut(Schema):
    items: list[InvitationOut]
    count: int


class AuditRuleOut(Schema):
    id: str
    period_days: int
    created_at: str


class AuditRuleListOut(Schema):
    items: list[AuditRuleOut]
    count: int


class CreateAuditRuleIn(Schema):
    period_days: int


class AuditRuleBriefOut(Schema):
    id: str
    period_days: int


class StalenessAlertRuleBriefOut(Schema):
    id: str
    period_days: int
    notify_admins: bool
    notify_team_managers: bool
    notify_process_owner: bool


class StalenessAlertRuleOut(Schema):
    id: str
    period_days: int
    notify_admins: bool
    notify_team_managers: bool
    notify_process_owner: bool
    created_at: str


class StalenessAlertRuleListOut(Schema):
    items: list[StalenessAlertRuleOut]
    count: int


class CreateStalenessAlertRuleIn(Schema):
    period_days: int
    notify_admins: bool = True
    notify_team_managers: bool = False
    notify_process_owner: bool = True


class UpdateStalenessAlertRuleIn(Schema):
    period_days: int | None = None
    notify_admins: bool | None = None
    notify_team_managers: bool | None = None
    notify_process_owner: bool | None = None


class SettingsOut(Schema):
    id: str | None
    workspace_id: str
    team_id: str | None
    department_id: str | None
    require_review_before_publish: bool | None
    enable_version_history: bool | None
    enable_api_access: bool | None
    require_change_summary: bool | None
    allow_agent_process_updates: bool | None
    process_audit: AuditRuleBriefOut | None
    staleness_alert: StalenessAlertRuleBriefOut | None


class EffectiveSettingsOut(Schema):
    require_review_before_publish: bool | None
    enable_version_history: bool | None
    enable_api_access: bool | None
    require_change_summary: bool | None
    allow_agent_process_updates: bool | None
    process_audit: AuditRuleBriefOut | None
    staleness_alert: StalenessAlertRuleBriefOut | None


class UpsertSettingsIn(Schema):
    workspace_id: str
    team_id: str | None = None
    department_id: str | None = None
    require_review_before_publish: bool | None = None
    enable_version_history: bool | None = None
    enable_api_access: bool | None = None
    require_change_summary: bool | None = None
    allow_agent_process_updates: bool | None = None
    process_audit_id: str | None = None
    staleness_alert_id: str | None = None


# ── Helpers ──────────────────────────────────────────────────────────────


def _user_brief(user):
    if user is None:
        return None
    return {
        "id": str(user.id),
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
    }


def _get_slug(entity_type: str, entity_id) -> str:
    """Look up the slug for an entity from the CoreSlug table."""
    try:
        return CoreSlug.objects.get(entity_type=entity_type, entity_id=entity_id).slug
    except CoreSlug.DoesNotExist:
        return ""


def _workspace_out(ws):
    return {
        "id": str(ws.id),
        "name": ws.name,
        "slug": _get_slug(EntityType.WORKSPACE, ws.id),
        "created_at": ws.created_at.isoformat(),
    }


def _team_out(team, department_count=0):
    return {
        "id": str(team.id),
        "name": team.name,
        "slug": _get_slug(EntityType.TEAM, team.id),
        "department_count": department_count,
        "created_at": team.created_at.isoformat(),
    }


def _department_out(dept):
    home = getattr(dept, "home_process_count", 0)
    shared = getattr(dept, "shared_process_count", 0)
    team = getattr(dept, "team_process_count", 0)
    workspace = getattr(dept, "workspace_process_count", 0)
    return {
        "id": str(dept.id),
        "name": dept.name,
        "slug": _get_slug(EntityType.DEPARTMENT, dept.id),
        "team_slug": _get_slug(EntityType.TEAM, dept.team_id),
        "team_name": dept.team.name,
        "owner": _user_brief(dept.owner),
        "process_count": home + shared + team + workspace,
        "created_at": dept.created_at.isoformat(),
    }


def _membership_out(m):
    return {
        "id": str(m.user.id),
        "email": m.user.email,
        "first_name": m.user.first_name,
        "last_name": m.user.last_name,
        "role": m.role,
        "team_id": str(m.team_id) if m.team_id else None,
        "team_name": m.team.name if m.team else None,
        "department_ids": [str(d.id) for d in m.departments.all()],
    }


def _audit_rule_brief(rule):
    if rule is None:
        return None
    return {"id": str(rule.id), "period_days": rule.period_days}


def _staleness_alert_brief(rule):
    if rule is None:
        return None
    return {
        "id": str(rule.id),
        "period_days": rule.period_days,
        "notify_admins": rule.notify_admins,
        "notify_team_managers": rule.notify_team_managers,
        "notify_process_owner": rule.notify_process_owner,
    }


def _invitation_out(inv):
    return {
        "id": str(inv.id),
        "email": inv.email,
        "role": inv.role,
        "team_name": inv.team.name if inv.team else None,
        "department_names": [d.name for d in inv.departments.all()],
        "invited_by_email": inv.invited_by.email if inv.invited_by else None,
        "status": inv.status,
        "created_at": inv.created_at.isoformat(),
        "expires_at": inv.expires_at.isoformat(),
    }


def _resolve_team_by_slug(workspace, slug):
    """Resolve a Team from its slug within a workspace via CoreSlug."""
    try:
        cs = resolve_slug(EntityType.TEAM, slug, scope_workspace=workspace)
        return Team.objects.get(id=cs.entity_id, workspace=workspace)
    except (CoreSlug.DoesNotExist, Team.DoesNotExist):
        raise HttpError(404, "Team not found")


# ── Workspace Endpoints ─────────────────────────────────────────────────


@router.post(
    "/workspaces",
    response={201: WorkspaceOut},
    auth=api_or_session,
    throttle=[CreateAuthThrottle()],
)
def create_workspace(request, payload: CreateWorkspaceIn):
    from django.conf import settings
    from django.db import transaction

    from apps.billing.enums import BillingPeriod, SubscriptionStatus
    from apps.billing.models import Customer, Plan, Subscription, WorkspaceSubscription
    from apps.orgs.enums import PlanChoices

    with transaction.atomic():
        slug = unique_slug(EntityType.WORKSPACE, payload.slug)
        workspace = Workspace.objects.create(name=payload.name)
        create_slug(EntityType.WORKSPACE, workspace.id, slug)
        Membership.objects.create(
            user=request.user,
            workspace=workspace,
            role=RoleChoices.ADMIN,
        )
        ProcessAuditRule.objects.create(workspace=workspace, period_days=90)

        if settings.ENABLE_BILLING:
            trial_plan, _ = Plan.objects.get_or_create(
                tier=PlanChoices.TRIAL,
                billing_period=BillingPeriod.MONTHLY,
                defaults={
                    "name": "Trial",
                    "price_cents": 0,
                    "is_active": True,
                },
            )
            customer = Customer.objects.create(
                workspace=workspace,
                email=request.user.email,
                first_name=request.user.first_name,
                last_name=request.user.last_name,
            )
            now = timezone.now()
            subscription = Subscription.objects.create(
                customer=customer,
                plan=trial_plan,
                status=SubscriptionStatus.IN_TRIAL,
                trial_start=now,
                trial_end=now + timedelta(days=30),
            )
            WorkspaceSubscription.objects.create(
                workspace=workspace,
                subscription=subscription,
            )

    return Status(201, _workspace_out(workspace))


@router.get(
    "/workspaces/{slug}",
    response=WorkspaceOut,
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
def get_workspace(request, slug: str):
    workspace = request.workspace
    if not workspace:
        raise HttpError(404, "Workspace not found")
    ws_slug = _get_slug(EntityType.WORKSPACE, workspace.id)
    if ws_slug != slug:
        raise HttpError(404, "Workspace not found")
    return _workspace_out(workspace)


# ── Member Endpoints ─────────────────────────────────────────────────────


@router.get("/members", response=MemberListOut, auth=api_or_session, throttle=[ReadThrottle()])
@require_role(RoleChoices.ADMIN, RoleChoices.TEAM_MANAGER, RoleChoices.MEMBER)
def list_members(request, limit: int = 50, offset: int = 0):
    workspace = request.workspace
    membership = request.membership
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)
    qs = (
        Membership.objects.filter(workspace=workspace)
        .select_related("user", "team")
        .prefetch_related("departments")
    )

    if membership.role == RoleChoices.ADMIN:
        pass
    elif membership.role == RoleChoices.TEAM_MANAGER:
        if membership.team:
            team_dept_ids = set(
                Department.objects.filter(team=membership.team).values_list("id", flat=True)
            )
            member_ids = set(
                Membership.objects.filter(
                    workspace=workspace, departments__id__in=team_dept_ids
                ).values_list("user_id", flat=True)
            )
            member_ids.add(membership.user_id)
            qs = qs.filter(user_id__in=member_ids)
        else:
            qs = qs.filter(user_id=membership.user_id)
    else:
        my_dept_ids = set(membership.departments.values_list("id", flat=True))
        if my_dept_ids:
            peer_user_ids = set(
                Membership.objects.filter(
                    workspace=workspace, departments__id__in=my_dept_ids
                ).values_list("user_id", flat=True)
            )
            peer_user_ids.add(membership.user_id)
            qs = qs.filter(user_id__in=peer_user_ids)
        else:
            qs = qs.filter(user_id=membership.user_id)

    qs = qs.distinct()
    count = qs.count()
    items = [_membership_out(m) for m in qs[offset : offset + limit]]
    return {"items": items, "count": count}


@router.post(
    "/members",
    response=InviteResponseOut,
    auth=api_or_session,
    throttle=[InviteThrottle()],
)
@require_role(RoleChoices.ADMIN, RoleChoices.TEAM_MANAGER)
def invite_member(request, payload: InviteMemberIn):
    """
    Always returns a generic 200 regardless of whether the email is registered
    or the user is already a member, preventing email enumeration.
    """
    from apps.accounts.models import User

    workspace = request.workspace
    membership = request.membership
    generic_response = {"detail": "Invitation sent"}

    if payload.role not in (RoleChoices.ADMIN, RoleChoices.TEAM_MANAGER, RoleChoices.MEMBER):
        raise HttpError(400, "Invalid role")

    if membership.role == RoleChoices.TEAM_MANAGER:
        if payload.role != RoleChoices.MEMBER:
            raise HttpError(403, "Team managers can only invite members")
        if not membership.team:
            raise HttpError(403, "You are not assigned to a team")

    team = None
    if payload.role == RoleChoices.TEAM_MANAGER:
        if not payload.team_id:
            raise HttpError(400, "team_id required for team_manager role")
        try:
            team = Team.objects.get(id=payload.team_id, workspace=workspace)
        except Team.DoesNotExist:
            raise HttpError(400, "Invalid team")

    departments = []
    dept_ids = payload.department_ids
    if membership.role == RoleChoices.TEAM_MANAGER:
        if not dept_ids:
            raise HttpError(400, "department_ids required when inviting a member")
        team_dept_ids = set(
            str(pk)
            for pk in Department.objects.filter(team=membership.team).values_list("id", flat=True)
        )
        for did in dept_ids:
            if did not in team_dept_ids:
                raise HttpError(403, f"Department {did} is outside your team")

    if dept_ids:
        departments = list(Department.objects.filter(id__in=dept_ids, team__workspace=workspace))
        if len(departments) != len(dept_ids):
            raise HttpError(400, "One or more department IDs are invalid")

    # ── Trial member limit ────────────────────────────────────────────────
    from apps.billing.limits import get_member_limit

    member_limit = get_member_limit(workspace)
    if member_limit is not None:
        current_members = Membership.objects.filter(workspace=workspace).count()
        pending_invitations = PendingInvitation.objects.filter(
            workspace=workspace, status=InvitationStatus.PENDING
        ).count()
        if current_members + pending_invitations >= member_limit:
            raise HttpError(
                402,
                f"Your trial is limited to {member_limit} members. "
                "Upgrade to a paid plan to invite more.",
            )

    already_member = False
    try:
        user = User.objects.get(email=payload.email)
        if Membership.objects.filter(workspace=workspace, user=user).exists():
            already_member = True
    except User.DoesNotExist:
        pass

    if already_member:
        return generic_response

    if PendingInvitation.objects.filter(
        workspace=workspace, email=payload.email, status=InvitationStatus.PENDING
    ).exists():
        return generic_response

    invitation = PendingInvitation.objects.create(
        workspace=workspace,
        email=payload.email,
        role=payload.role,
        team=team,
        invited_by=request.user,
        token=PendingInvitation.generate_token(),
        expires_at=timezone.now() + timedelta(days=7),
    )
    if departments:
        invitation.departments.set(departments)

    from apps.orgs.tasks import send_invitation_email

    send_invitation_email(str(invitation.id))

    return generic_response


@router.delete("/members/{user_id}", auth=api_or_session, throttle=[MutationThrottle()])
@require_role(RoleChoices.ADMIN, RoleChoices.TEAM_MANAGER)
def remove_member(request, user_id: str):
    workspace = request.workspace
    membership = request.membership

    try:
        target = (
            Membership.objects.select_related("user", "team")
            .prefetch_related("departments")
            .get(workspace=workspace, user_id=user_id)
        )
    except Membership.DoesNotExist:
        raise HttpError(404, "Member not found")

    if target.user_id == request.user.id:
        raise HttpError(400, "Cannot remove yourself")

    if membership.role == RoleChoices.TEAM_MANAGER:
        if target.role != RoleChoices.MEMBER:
            raise HttpError(403, "Team managers can only remove members")
        if not membership.team:
            raise HttpError(403, "You are not assigned to a team")
        target_dept_ids = set(str(d.id) for d in target.departments.all())
        team_dept_ids = set(
            str(pk)
            for pk in Department.objects.filter(team=membership.team).values_list("id", flat=True)
        )
        if not target_dept_ids.intersection(team_dept_ids):
            raise HttpError(403, "Member is not in your team")

    target.delete()
    return {"ok": True}


# ── Invitation Endpoints ──────────────────────────────────────────────────


@router.get(
    "/invitations",
    response=InvitationListOut,
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
@require_role(RoleChoices.ADMIN, RoleChoices.TEAM_MANAGER)
def list_invitations(request, limit: int = 50, offset: int = 0):
    workspace = request.workspace
    membership = request.membership
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)
    qs = (
        PendingInvitation.objects.filter(workspace=workspace, status=InvitationStatus.PENDING)
        .select_related("team", "invited_by")
        .prefetch_related("departments")
        .order_by("-created_at")
    )

    if membership.role == RoleChoices.TEAM_MANAGER and membership.team:
        qs = qs.filter(Q(team=membership.team) | Q(invited_by=request.user))

    count = qs.count()
    items = [_invitation_out(inv) for inv in qs[offset : offset + limit]]
    return {"items": items, "count": count}


@router.delete("/invitations/{invitation_id}", auth=api_or_session, throttle=[MutationThrottle()])
@require_role(RoleChoices.ADMIN, RoleChoices.TEAM_MANAGER)
def cancel_invitation(request, invitation_id: str):
    workspace = request.workspace
    membership = request.membership
    try:
        invitation = PendingInvitation.objects.get(
            id=invitation_id, workspace=workspace, status=InvitationStatus.PENDING
        )
    except PendingInvitation.DoesNotExist:
        raise HttpError(404, "Invitation not found")

    if membership.role == RoleChoices.TEAM_MANAGER:
        if not membership.team or invitation.team_id != membership.team.id:
            raise HttpError(403, "Cannot cancel invitations outside your team")

    invitation.status = InvitationStatus.CANCELLED
    invitation.save(update_fields=["status", "updated_at"])
    return {"ok": True}


@router.post(
    "/invitations/{token}/accept",
    auth=api_or_session,
    throttle=[AuthAnonThrottle(), AuthUserThrottle()],
)
def accept_invitation(request, token: str):
    try:
        invitation = (
            PendingInvitation.objects.select_related("team")
            .prefetch_related("departments")
            .get(token=token, status=InvitationStatus.PENDING)
        )
    except PendingInvitation.DoesNotExist:
        raise HttpError(404, "Invitation not found or already used")

    if invitation.expires_at < timezone.now():
        invitation.status = InvitationStatus.EXPIRED
        invitation.save(update_fields=["status", "updated_at"])
        raise HttpError(410, "Invitation has expired")

    if request.user.email.lower() != invitation.email.lower():
        raise HttpError(403, "This invitation was sent to a different email address")

    from django.db import IntegrityError, transaction

    with transaction.atomic():
        if Membership.objects.filter(workspace=invitation.workspace, user=request.user).exists():
            invitation.status = InvitationStatus.ACCEPTED
            invitation.save(update_fields=["status", "updated_at"])
            return {"detail": "You are already a member of this workspace"}

        try:
            new_membership = Membership.objects.create(
                user=request.user,
                workspace=invitation.workspace,
                role=invitation.role,
                team=invitation.team,
            )
        except IntegrityError:
            return {"detail": "You are already a member of this workspace"}

        dept_ids = list(invitation.departments.values_list("id", flat=True))
        if dept_ids:
            new_membership.departments.set(dept_ids)

        invitation.status = InvitationStatus.ACCEPTED
        invitation.save(update_fields=["status", "updated_at"])

    return {"detail": "Invitation accepted"}


# ── Team Endpoints ───────────────────────────────────────────────────────


@router.get("/teams", response=TeamListOut, auth=api_or_session, throttle=[ReadThrottle()])
def list_teams(request, limit: int = 50, offset: int = 0):
    workspace = request.workspace
    if not workspace:
        raise HttpError(403, "No workspace context")
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)
    qs = (
        Team.objects.filter(workspace=workspace)
        .annotate(department_count=Count("departments"))
        .order_by("name")
    )
    count = qs.count()
    items = [_team_out(t, t.department_count) for t in qs[offset : offset + limit]]
    return {"items": items, "count": count}


@router.post(
    "/teams",
    response={201: TeamOut},
    auth=api_or_session,
    throttle=[CreateAuthThrottle()],
)
@require_role(RoleChoices.ADMIN)
def create_team(request, payload: CreateTeamIn):
    workspace = request.workspace
    slug = unique_slug(EntityType.TEAM, payload.slug, scope_workspace=workspace)
    team = Team.objects.create(workspace=workspace, name=payload.name)
    create_slug(EntityType.TEAM, team.id, slug, scope_workspace=workspace)
    return Status(201, _team_out(team))


@router.get("/teams/{slug}", response=TeamDetailOut, auth=api_or_session, throttle=[ReadThrottle()])
def get_team(request, slug: str):
    workspace = request.workspace
    if not workspace:
        raise HttpError(403, "No workspace context")
    team = _resolve_team_by_slug(workspace, slug)

    departments = (
        Department.objects.filter(team=team)
        .select_related("team", "owner")
        .annotate(**_department_process_count_annotations())
        .order_by("name")
    )
    return {
        "id": str(team.id),
        "name": team.name,
        "slug": _get_slug(EntityType.TEAM, team.id),
        "departments": [_department_out(d) for d in departments],
        "created_at": team.created_at.isoformat(),
    }


@router.patch("/teams/{slug}", response=TeamOut, auth=api_or_session, throttle=[MutationThrottle()])
@require_role(RoleChoices.ADMIN)
def update_team(request, slug: str, payload: UpdateTeamIn):
    workspace = request.workspace
    team = _resolve_team_by_slug(workspace, slug)
    if payload.name is not None:
        team.name = payload.name
        team.save(update_fields=["name", "updated_at"])
    dept_count = team.departments.count()
    return _team_out(team, dept_count)


@router.delete("/teams/{slug}", auth=api_or_session, throttle=[MutationThrottle()])
@require_role(RoleChoices.ADMIN)
def delete_team(request, slug: str):
    workspace = request.workspace
    team = _resolve_team_by_slug(workspace, slug)
    team.delete()
    return {"ok": True}


# ── Department Endpoints ─────────────────────────────────────────────────


@router.get(
    "/departments",
    response=DepartmentListOut,
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
def list_departments(request, team: str | None = None, limit: int = 50, offset: int = 0):
    workspace = request.workspace
    if not workspace:
        raise HttpError(403, "No workspace context")
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)
    qs = (
        Department.objects.filter(team__workspace=workspace)
        .select_related("team", "owner")
        .annotate(**_department_process_count_annotations())
        .order_by("name")
    )
    if team:
        try:
            cs = resolve_slug(EntityType.TEAM, team, scope_workspace=workspace)
            qs = qs.filter(team_id=cs.entity_id)
        except CoreSlug.DoesNotExist:
            return {"items": [], "count": 0}
    count = qs.count()
    items = [_department_out(d) for d in qs[offset : offset + limit]]
    return {"items": items, "count": count}


@router.get(
    "/departments/{id}",
    response=DepartmentOut,
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
def get_department(request, id: str):
    workspace = request.workspace
    if not workspace:
        raise HttpError(403, "No workspace context")
    try:
        dept = (
            Department.objects.filter(id=id, team__workspace=workspace)
            .select_related("team", "owner")
            .annotate(**_department_process_count_annotations())
            .get()
        )
    except Department.DoesNotExist:
        raise HttpError(404, "Department not found")
    return _department_out(dept)


@router.post(
    "/departments",
    response={201: DepartmentOut},
    auth=api_or_session,
    throttle=[CreateAuthThrottle()],
)
@require_role(RoleChoices.ADMIN, RoleChoices.TEAM_MANAGER)
def create_department(request, payload: CreateDepartmentIn):
    workspace = request.workspace
    team = _resolve_team_by_slug(workspace, payload.team_slug)

    membership = request.membership
    if membership.role == RoleChoices.TEAM_MANAGER:
        if not membership.team or membership.team_id != team.id:
            raise HttpError(403, "Department is outside your assigned team")

    slug = unique_slug(EntityType.DEPARTMENT, payload.slug, scope_team=team)

    owner = None
    if payload.owner_id:
        if not Membership.objects.filter(workspace=workspace, user_id=payload.owner_id).exists():
            raise HttpError(400, "Owner is not a workspace member")
        from apps.accounts.models import User

        owner = User.objects.get(id=payload.owner_id)

    dept = Department.objects.create(team=team, name=payload.name, owner=owner)
    create_slug(EntityType.DEPARTMENT, dept.id, slug, scope_team=team)
    dept = (
        Department.objects.filter(id=dept.id)
        .select_related("team", "owner")
        .annotate(**_department_process_count_annotations())
        .first()
    )
    return Status(201, _department_out(dept))


@router.patch(
    "/departments/{id}",
    response=DepartmentOut,
    auth=api_or_session,
    throttle=[MutationThrottle()],
)
@require_role(RoleChoices.ADMIN, RoleChoices.TEAM_MANAGER)
def update_department(request, id: str, payload: UpdateDepartmentIn):
    workspace = request.workspace
    try:
        dept = Department.objects.select_related("team", "owner").get(
            id=id, team__workspace=workspace
        )
    except Department.DoesNotExist:
        raise HttpError(404, "Department not found")

    check_dept_write(request, dept)

    update_fields = ["updated_at"]
    if payload.name is not None:
        dept.name = payload.name
        update_fields.append("name")
    if payload.owner_id is not None:
        if not Membership.objects.filter(workspace=workspace, user_id=payload.owner_id).exists():
            raise HttpError(400, "Owner is not a workspace member")
        from apps.accounts.models import User

        dept.owner = User.objects.get(id=payload.owner_id)
        update_fields.append("owner")
    dept.save(update_fields=update_fields)
    dept = (
        Department.objects.filter(id=dept.id)
        .select_related("team", "owner")
        .annotate(**_department_process_count_annotations())
        .first()
    )
    return _department_out(dept)


@router.delete("/departments/{id}", auth=api_or_session, throttle=[MutationThrottle()])
@require_role(RoleChoices.ADMIN, RoleChoices.TEAM_MANAGER)
def delete_department(request, id: str):
    workspace = request.workspace
    try:
        dept = Department.objects.select_related("team").get(id=id, team__workspace=workspace)
    except Department.DoesNotExist:
        raise HttpError(404, "Department not found")

    check_dept_write(request, dept)

    dept.delete()
    return {"ok": True}


# ── Settings Endpoints ──────────────────────────────────────────────────


@router.get(
    "/settings",
    response=EffectiveSettingsOut,
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
@require_role(RoleChoices.ADMIN, RoleChoices.TEAM_MANAGER, RoleChoices.MEMBER)
def get_settings(request, team_id: str | None = None, department_id: str | None = None):
    workspace = request.workspace
    effective = get_effective_settings(workspace.id, team_id=team_id, department_id=department_id)
    effective["process_audit"] = _audit_rule_brief(effective.get("process_audit"))
    effective["staleness_alert"] = _staleness_alert_brief(effective.get("staleness_alert"))
    return effective


@router.patch("/settings", response=SettingsOut, auth=api_or_session, throttle=[MutationThrottle()])
@require_role(RoleChoices.ADMIN)
def upsert_settings(request, payload: UpsertSettingsIn):
    workspace = request.workspace
    if str(workspace.id) != payload.workspace_id:
        raise HttpError(403, "Cannot modify settings for another workspace")

    if payload.department_id and not payload.team_id:
        raise HttpError(400, "team_id is required when department_id is set")

    lookup = {
        "workspace": workspace,
        "team_id": payload.team_id,
        "department_id": payload.department_id,
    }
    settings_row, _ = CoreSettings.objects.get_or_create(**lookup)

    for field in SETTINGS_FIELDS:
        val = getattr(payload, field)
        if val is not None:
            setattr(settings_row, field, val)

    if payload.process_audit_id is not None:
        if payload.process_audit_id == "":
            settings_row.process_audit = None
        else:
            try:
                rule = ProcessAuditRule.objects.get(
                    id=payload.process_audit_id,
                    workspace=workspace,
                )
            except ProcessAuditRule.DoesNotExist:
                raise HttpError(404, "Audit rule not found")
            settings_row.process_audit = rule

    if payload.staleness_alert_id is not None:
        if payload.staleness_alert_id == "":
            settings_row.staleness_alert = None
        else:
            try:
                alert_rule = StalenessAlertRule.objects.get(
                    id=payload.staleness_alert_id,
                    workspace=workspace,
                )
            except StalenessAlertRule.DoesNotExist:
                raise HttpError(404, "Staleness alert rule not found")
            settings_row.staleness_alert = alert_rule

    settings_row.save()

    settings_row = CoreSettings.objects.select_related("process_audit", "staleness_alert").get(
        id=settings_row.id
    )

    return {
        "id": str(settings_row.id),
        "workspace_id": str(settings_row.workspace_id),
        "team_id": str(settings_row.team_id) if settings_row.team_id else None,
        "department_id": str(settings_row.department_id) if settings_row.department_id else None,
        "require_review_before_publish": settings_row.require_review_before_publish,
        "enable_version_history": settings_row.enable_version_history,
        "enable_api_access": settings_row.enable_api_access,
        "require_change_summary": settings_row.require_change_summary,
        "allow_agent_process_updates": settings_row.allow_agent_process_updates,
        "process_audit": _audit_rule_brief(settings_row.process_audit),
        "staleness_alert": _staleness_alert_brief(settings_row.staleness_alert),
    }


# ── Audit Rule Endpoints ────────────────────────────────────────────────


@router.get(
    "/audit-rules",
    response=AuditRuleListOut,
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
@require_role(RoleChoices.ADMIN)
def list_audit_rules(request, limit: int = 50, offset: int = 0):
    workspace = request.workspace
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)
    qs = ProcessAuditRule.objects.filter(workspace=workspace).order_by("period_days")
    count = qs.count()
    items = [
        {
            "id": str(r.id),
            "period_days": r.period_days,
            "created_at": r.created_at.isoformat(),
        }
        for r in qs[offset : offset + limit]
    ]
    return {"items": items, "count": count}


@router.post(
    "/audit-rules",
    response={201: AuditRuleOut},
    auth=api_or_session,
    throttle=[CreateAuthThrottle()],
)
@require_role(RoleChoices.ADMIN)
def create_audit_rule(request, payload: CreateAuditRuleIn):
    workspace = request.workspace
    if payload.period_days < 1:
        raise HttpError(400, "period_days must be at least 1")
    rule = ProcessAuditRule.objects.create(
        workspace=workspace,
        period_days=payload.period_days,
    )
    return Status(
        201,
        {
            "id": str(rule.id),
            "period_days": rule.period_days,
            "created_at": rule.created_at.isoformat(),
        },
    )


@router.delete("/audit-rules/{rule_id}", auth=api_or_session, throttle=[MutationThrottle()])
@require_role(RoleChoices.ADMIN)
def delete_audit_rule(request, rule_id: str):
    workspace = request.workspace
    try:
        rule = ProcessAuditRule.objects.get(id=rule_id, workspace=workspace)
    except ProcessAuditRule.DoesNotExist:
        raise HttpError(404, "Audit rule not found")
    rule.delete()
    return {"ok": True}


# ── Staleness Alert Rule Endpoints ──────────────────────────────────────


@router.get(
    "/staleness-alert-rules",
    response=StalenessAlertRuleListOut,
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
@require_role(RoleChoices.ADMIN)
def list_staleness_alert_rules(request, limit: int = 50, offset: int = 0):
    workspace = request.workspace
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)
    qs = StalenessAlertRule.objects.filter(workspace=workspace).order_by("period_days")
    count = qs.count()
    items = [
        {
            "id": str(r.id),
            "period_days": r.period_days,
            "notify_admins": r.notify_admins,
            "notify_team_managers": r.notify_team_managers,
            "notify_process_owner": r.notify_process_owner,
            "created_at": r.created_at.isoformat(),
        }
        for r in qs[offset : offset + limit]
    ]
    return {"items": items, "count": count}


@router.post(
    "/staleness-alert-rules",
    response={201: StalenessAlertRuleOut},
    auth=api_or_session,
    throttle=[CreateAuthThrottle()],
)
@require_role(RoleChoices.ADMIN)
def create_staleness_alert_rule(request, payload: CreateStalenessAlertRuleIn):
    workspace = request.workspace
    if payload.period_days < 1:
        raise HttpError(400, "period_days must be at least 1")
    rule = StalenessAlertRule.objects.create(
        workspace=workspace,
        period_days=payload.period_days,
        notify_admins=payload.notify_admins,
        notify_team_managers=payload.notify_team_managers,
        notify_process_owner=payload.notify_process_owner,
    )
    return Status(
        201,
        {
            "id": str(rule.id),
            "period_days": rule.period_days,
            "notify_admins": rule.notify_admins,
            "notify_team_managers": rule.notify_team_managers,
            "notify_process_owner": rule.notify_process_owner,
            "created_at": rule.created_at.isoformat(),
        },
    )


@router.patch(
    "/staleness-alert-rules/{rule_id}",
    response=StalenessAlertRuleOut,
    auth=api_or_session,
    throttle=[MutationThrottle()],
)
@require_role(RoleChoices.ADMIN)
def update_staleness_alert_rule(request, rule_id: str, payload: UpdateStalenessAlertRuleIn):
    workspace = request.workspace
    try:
        rule = StalenessAlertRule.objects.get(id=rule_id, workspace=workspace)
    except StalenessAlertRule.DoesNotExist:
        raise HttpError(404, "Staleness alert rule not found")

    if payload.period_days is not None:
        if payload.period_days < 1:
            raise HttpError(400, "period_days must be at least 1")
        rule.period_days = payload.period_days
    if payload.notify_admins is not None:
        rule.notify_admins = payload.notify_admins
    if payload.notify_team_managers is not None:
        rule.notify_team_managers = payload.notify_team_managers
    if payload.notify_process_owner is not None:
        rule.notify_process_owner = payload.notify_process_owner

    rule.save()
    return {
        "id": str(rule.id),
        "period_days": rule.period_days,
        "notify_admins": rule.notify_admins,
        "notify_team_managers": rule.notify_team_managers,
        "notify_process_owner": rule.notify_process_owner,
        "created_at": rule.created_at.isoformat(),
    }


@router.delete(
    "/staleness-alert-rules/{rule_id}", auth=api_or_session, throttle=[MutationThrottle()]
)
@require_role(RoleChoices.ADMIN)
def delete_staleness_alert_rule(request, rule_id: str):
    workspace = request.workspace
    try:
        rule = StalenessAlertRule.objects.get(id=rule_id, workspace=workspace)
    except StalenessAlertRule.DoesNotExist:
        raise HttpError(404, "Staleness alert rule not found")
    rule.delete()
    return {"ok": True}
