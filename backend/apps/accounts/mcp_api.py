from django.db.models import Max, Q
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError
from oauth2_provider.models import AccessToken, Application, RefreshToken

from apps.accounts.auth import api_or_session
from apps.accounts.models import McpConnectionScope, ScopeType
from apps.accounts.permissions import require_role
from apps.common.throttles import MutationThrottle, ReadThrottle
from apps.orgs.enums import RoleChoices

router = Router(tags=["mcp"])


# ── Schemas ──────────────────────────────────────────────────────────────


class McpConnectionUserOut(Schema):
    id: str
    email: str


class DepartmentBriefOut(Schema):
    id: str
    name: str
    team_name: str


class McpConnectionScopeOut(Schema):
    scope_type: str
    team_id: str | None
    team_name: str | None
    department_ids: list[str]
    departments: list[DepartmentBriefOut]


class McpConnectionOut(Schema):
    id: str
    client_name: str
    user: McpConnectionUserOut | None
    scopes: str
    created_at: str
    last_used_at: str | None
    is_active: bool
    connection_scope: McpConnectionScopeOut | None


class McpConnectionListOut(Schema):
    items: list[McpConnectionOut]
    count: int


class McpConnectionScopeIn(Schema):
    scope_type: str
    team_id: str | None = None
    department_ids: list[str] = []


# ── Helpers ──────────────────────────────────────────────────────────────


def _scope_out(scope: McpConnectionScope | None) -> dict | None:
    if scope is None:
        return None
    depts = list(scope.departments.select_related("team").all())
    return {
        "scope_type": scope.scope_type,
        "team_id": str(scope.team_id) if scope.team_id else None,
        "team_name": scope.team.name if scope.team else None,
        "department_ids": [str(d.id) for d in depts],
        "departments": [{"id": str(d.id), "name": d.name, "team_name": d.team.name} for d in depts],
    }


def _connection_out(app: Application, token_info: dict, scope: McpConnectionScope | None) -> dict:
    user = token_info.get("user")
    return {
        "id": str(app.id),
        "client_name": app.name,
        "user": ({"id": str(user.id), "email": user.email} if user else None),
        "scopes": token_info.get("scopes", ""),
        "created_at": app.created.isoformat(),
        "last_used_at": (
            token_info["last_used_at"].isoformat() if token_info.get("last_used_at") else None
        ),
        "is_active": token_info.get("is_active", False),
        "connection_scope": _scope_out(scope),
    }


def _get_connection_app(connection_id: str, workspace):
    """Look up an OAuth Application that belongs to this workspace."""
    try:
        app = Application.objects.get(id=connection_id)
    except (Application.DoesNotExist, ValueError):
        raise HttpError(404, "MCP connection not found")

    has_workspace_tokens = AccessToken.objects.filter(
        application=app,
        user__memberships__workspace=workspace,
    ).exists()
    if not has_workspace_tokens:
        raise HttpError(404, "MCP connection not found")

    return app


# ── Endpoints ────────────────────────────────────────────────────────────


@router.get(
    "/mcp/connections",
    response=McpConnectionListOut,
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
@require_role(RoleChoices.ADMIN)
def list_mcp_connections(request):
    workspace = request.workspace

    apps = Application.objects.filter(
        authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
    ).order_by("-created")

    scope_by_app = {}
    scopes = (
        McpConnectionScope.objects.filter(
            workspace=workspace,
        )
        .select_related("team")
        .prefetch_related("departments__team")
    )
    for s in scopes:
        scope_by_app[s.application_id] = s

    results = []
    for app in apps:
        tokens = AccessToken.objects.filter(application=app).select_related("user")

        workspace_tokens = tokens.filter(
            user__memberships__workspace=workspace,
        )

        if not workspace_tokens.exists():
            continue

        latest = workspace_tokens.order_by("-created").first()
        last_used = workspace_tokens.aggregate(last=Max("created"))["last"]

        has_active_refresh = (
            RefreshToken.objects.filter(
                application=app,
                access_token__user=latest.user if latest else None,
            )
            .filter(
                Q(revoked__isnull=True),
            )
            .exists()
        )

        results.append(
            _connection_out(
                app,
                {
                    "user": latest.user if latest else None,
                    "scopes": latest.scope if latest else "",
                    "last_used_at": last_used,
                    "is_active": has_active_refresh,
                },
                scope_by_app.get(app.id),
            )
        )

    return {"items": results, "count": len(results)}


@router.delete(
    "/mcp/connections/{connection_id}",
    auth=api_or_session,
    throttle=[MutationThrottle()],
)
@require_role(RoleChoices.ADMIN)
def revoke_mcp_connection(request, connection_id: str):
    workspace = request.workspace
    app = _get_connection_app(connection_id, workspace)

    now = timezone.now()
    RefreshToken.objects.filter(application=app).update(revoked=now)
    AccessToken.objects.filter(application=app).delete()
    McpConnectionScope.objects.filter(application=app).delete()
    app.delete()

    return {"ok": True}


@router.get(
    "/mcp/connections/{connection_id}/scope",
    response=McpConnectionScopeOut,
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
@require_role(RoleChoices.ADMIN)
def get_connection_scope(request, connection_id: str):
    workspace = request.workspace
    app = _get_connection_app(connection_id, workspace)

    try:
        scope = (
            McpConnectionScope.objects.select_related("team")
            .prefetch_related("departments__team")
            .get(application=app, workspace=workspace)
        )
    except McpConnectionScope.DoesNotExist:
        return {
            "scope_type": ScopeType.WORKSPACE,
            "team_id": None,
            "team_name": None,
            "department_ids": [],
            "departments": [],
        }

    return _scope_out(scope)


@router.patch(
    "/mcp/connections/{connection_id}/scope",
    response=McpConnectionScopeOut,
    auth=api_or_session,
    throttle=[MutationThrottle()],
)
@require_role(RoleChoices.ADMIN)
def update_connection_scope(request, connection_id: str, payload: McpConnectionScopeIn):
    from apps.orgs.models import Department, Team

    workspace = request.workspace
    app = _get_connection_app(connection_id, workspace)

    if payload.scope_type not in ScopeType.values:
        raise HttpError(400, f"Invalid scope_type: {payload.scope_type}")

    latest_token = (
        AccessToken.objects.filter(
            application=app,
            user__memberships__workspace=workspace,
        )
        .select_related("user")
        .order_by("-created")
        .first()
    )
    user = latest_token.user if latest_token else None

    team = None
    departments = []

    if payload.scope_type == ScopeType.TEAM:
        if not payload.team_id:
            raise HttpError(400, "team_id is required when scope_type is 'team'")
        try:
            team = Team.objects.get(id=payload.team_id, workspace=workspace)
        except (Team.DoesNotExist, ValueError):
            raise HttpError(400, "Team not found in this workspace")

    elif payload.scope_type == ScopeType.DEPARTMENT:
        if not payload.department_ids:
            raise HttpError(400, "department_ids is required when scope_type is 'department'")
        departments = list(
            Department.objects.filter(
                id__in=payload.department_ids,
                team__workspace=workspace,
            ).select_related("team")
        )
        if len(departments) != len(payload.department_ids):
            raise HttpError(400, "One or more department IDs are invalid for this workspace")

    scope, _created = McpConnectionScope.objects.update_or_create(
        application=app,
        defaults={
            "user": user,
            "workspace": workspace,
            "scope_type": payload.scope_type,
            "team": team,
        },
    )

    if payload.scope_type == ScopeType.DEPARTMENT:
        scope.departments.set(departments)
    else:
        scope.departments.clear()

    scope = (
        McpConnectionScope.objects.select_related("team")
        .prefetch_related("departments__team")
        .get(pk=scope.pk)
    )
    return _scope_out(scope)
