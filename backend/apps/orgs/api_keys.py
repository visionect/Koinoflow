from ninja import Router, Schema, Status
from ninja.errors import HttpError

from apps.accounts.auth import api_or_session
from apps.accounts.permissions import require_role
from apps.common.throttles import ApiKeyCreateThrottle, MutationThrottle, ReadThrottle
from apps.orgs.api import UserBriefOut, _user_brief
from apps.orgs.enums import RoleChoices
from apps.orgs.models import ApiKey, Department, Team

router = Router(tags=["api-keys"])


# ── Schemas ──────────────────────────────────────────────────────────────


class ApiKeyOut(Schema):
    id: str
    label: str
    key_prefix: str
    is_active: bool
    expires_at: str | None
    created_at: str
    created_by: UserBriefOut | None
    role: str
    team_id: str | None
    team_name: str | None
    department_ids: list[str]


class CreateApiKeyIn(Schema):
    label: str
    expires_at: str | None = None
    role: str = RoleChoices.ADMIN
    team_id: str | None = None
    department_ids: list[str] = []


class CreateApiKeyOut(Schema):
    id: str
    label: str
    key_prefix: str
    raw_key: str
    expires_at: str | None
    created_at: str
    role: str


class ApiKeyListOut(Schema):
    items: list[ApiKeyOut]
    count: int


class ApiKeyRoleOut(Schema):
    value: str
    label: str
    description: str
    requires_team: bool
    requires_departments: bool


ROLE_DESCRIPTIONS = {
    RoleChoices.ADMIN: "Full access to all processes",
    RoleChoices.TEAM_MANAGER: "Access to one team's processes",
    RoleChoices.MEMBER: "Access to specific departments only",
}


# ── Helpers ──────────────────────────────────────────────────────────────


def _api_key_out(key):
    return {
        "id": str(key.id),
        "label": key.label,
        "key_prefix": key.key_prefix,
        "is_active": key.is_active,
        "expires_at": key.expires_at.isoformat() if key.expires_at else None,
        "created_at": key.created_at.isoformat(),
        "created_by": _user_brief(key.created_by),
        "role": key.role,
        "team_id": str(key.team_id) if key.team_id else None,
        "team_name": key.team.name if key.team else None,
        "department_ids": [str(d.id) for d in key.departments.all()],
    }


# ── Endpoints ────────────────────────────────────────────────────────────


@router.get(
    "/api-key-roles",
    response=list[ApiKeyRoleOut],
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
@require_role(RoleChoices.ADMIN)
def list_api_key_roles(request):
    return [
        {
            "value": choice.value,
            "label": choice.label,
            "description": ROLE_DESCRIPTIONS.get(choice, ""),
            "requires_team": choice == RoleChoices.TEAM_MANAGER,
            "requires_departments": choice == RoleChoices.MEMBER,
        }
        for choice in RoleChoices
    ]


@router.get("/api-keys", response=ApiKeyListOut, auth=api_or_session, throttle=[ReadThrottle()])
@require_role(RoleChoices.ADMIN)
def list_api_keys(request, limit: int = 50, offset: int = 0):
    workspace = request.workspace
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)
    qs = (
        ApiKey.objects.filter(workspace=workspace)
        .select_related("created_by", "team")
        .prefetch_related("departments")
        .order_by("-created_at")
    )
    count = qs.count()
    items = [_api_key_out(k) for k in qs[offset : offset + limit]]
    return {"items": items, "count": count}


@router.post(
    "/api-keys",
    response={201: CreateApiKeyOut},
    auth=api_or_session,
    throttle=[ApiKeyCreateThrottle()],
)
@require_role(RoleChoices.ADMIN)
def create_api_key(request, payload: CreateApiKeyIn):
    workspace = request.workspace

    if payload.role not in (RoleChoices.ADMIN, RoleChoices.TEAM_MANAGER, RoleChoices.MEMBER):
        raise HttpError(400, "Invalid role")

    team = None
    if payload.role == RoleChoices.TEAM_MANAGER:
        if not payload.team_id:
            raise HttpError(400, "team_id required for team_manager role")
        try:
            team = Team.objects.get(id=payload.team_id, workspace=workspace)
        except Team.DoesNotExist:
            raise HttpError(404, "Team not found")

    departments = []
    if payload.role == RoleChoices.MEMBER:
        if not payload.department_ids:
            raise HttpError(400, "department_ids required for member role")
        departments = list(
            Department.objects.filter(id__in=payload.department_ids, team__workspace=workspace)
        )
        if len(departments) != len(payload.department_ids):
            raise HttpError(400, "One or more department IDs are invalid")

    raw_key, key_hash, key_prefix = ApiKey.generate()

    from django.utils.dateparse import parse_datetime

    expires_at = None
    if payload.expires_at:
        expires_at = parse_datetime(payload.expires_at)
        if not expires_at:
            raise HttpError(400, "Invalid expires_at format (use ISO 8601)")

    api_key = ApiKey.objects.create(
        workspace=workspace,
        created_by=request.user if request.user.is_authenticated else None,
        key_hash=key_hash,
        key_prefix=key_prefix,
        label=payload.label,
        expires_at=expires_at,
        role=payload.role,
        team=team,
    )
    if departments:
        api_key.departments.set(departments)

    return Status(
        201,
        {
            "id": str(api_key.id),
            "label": api_key.label,
            "key_prefix": api_key.key_prefix,
            "raw_key": raw_key,
            "expires_at": api_key.expires_at.isoformat() if api_key.expires_at else None,
            "created_at": api_key.created_at.isoformat(),
            "role": api_key.role,
        },
    )


@router.delete("/api-keys/{id}", auth=api_or_session, throttle=[MutationThrottle()])
@require_role(RoleChoices.ADMIN)
def revoke_api_key(request, id: str):
    workspace = request.workspace
    try:
        api_key = ApiKey.objects.get(id=id, workspace=workspace)
    except ApiKey.DoesNotExist:
        raise HttpError(404, "API key not found")
    api_key.is_active = False
    api_key.save(update_fields=["is_active", "updated_at"])
    return {"ok": True}
