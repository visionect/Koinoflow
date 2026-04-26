from functools import wraps

from ninja.errors import HttpError

from apps.orgs.enums import RoleChoices


def check_role(request, *roles):
    """Imperative role check for use inside endpoint bodies."""
    membership = getattr(request, "membership", None)
    if not membership:
        raise HttpError(403, "No workspace context")
    if membership.role not in roles:
        raise HttpError(403, "Insufficient permissions")


def require_role(*roles):
    """Decorator for Django Ninja endpoints. Checks membership role."""

    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            check_role(request, *roles)
            return func(request, *args, **kwargs)

        return wrapper

    return decorator


def _role_source(request):
    """Return the object (membership or api_key) that carries role/scope info."""
    membership = getattr(request, "membership", None)
    if membership:
        return membership
    return getattr(request, "api_key", None)


def get_writable_dept_ids(request):
    """
    Returns None if the requester has unrestricted write access (admin).
    Returns a set of Department UUID strings otherwise.
    An empty set means no write access to any department.
    """
    source = _role_source(request)
    if source is None:
        return set()

    role = source.role

    if role == RoleChoices.ADMIN:
        return None

    if role == RoleChoices.TEAM_MANAGER:
        team = source.team
        if not team:
            return set()
        from apps.orgs.models import Department

        return set(
            str(pk) for pk in Department.objects.filter(team=team).values_list("id", flat=True)
        )

    return set(str(pk) for pk in source.departments.values_list("id", flat=True))


def check_skill_write(request, skill):
    """Raises HttpError(403) if the requester cannot write to the given skill.

    Workspace-wide skills are admin-only regardless of department membership.
    OAuth tokens are allowed if they carry skills:write scope (already verified before this call).
    """
    from apps.skills.enums import VisibilityChoices

    # OAuth connections handle their own scope/connection checks separately
    if getattr(request, "oauth_token", None) is not None:
        return

    if skill.visibility == VisibilityChoices.WORKSPACE:
        source = _role_source(request)
        if source is None or source.role != RoleChoices.ADMIN:
            raise HttpError(403, "Only admins can modify workspace-wide skills")
        return
    writable = get_writable_dept_ids(request)
    if writable is None:
        return
    if str(skill.department_id) not in writable:
        raise HttpError(403, "Insufficient permissions for this skill")


def check_dept_write(request, department):
    """Raises HttpError(403) if team_manager is trying to act on a dept outside their team."""
    source = _role_source(request)
    if source is None or source.role == RoleChoices.ADMIN:
        return
    if source.role == RoleChoices.TEAM_MANAGER:
        if source.team is None or source.team_id != department.team_id:
            raise HttpError(403, "Department is outside your assigned team")
        return
    raise HttpError(403, "Insufficient permissions")


def apply_api_key_scope(api_key, qs):
    """
    Narrows a published-only Skill queryset to the API key's role scope,
    respecting the skill visibility field.
    Call this only for API key requests (after filtering to published).
    """
    from django.db.models import Q

    role = api_key.role

    if role == RoleChoices.ADMIN:
        return qs

    if role == RoleChoices.TEAM_MANAGER:
        team = api_key.team
        if not team:
            return qs.none()
        team_dept_ids = list(api_key.team.departments.values_list("id", flat=True))
        return qs.filter(
            Q(department__team=team)
            | Q(visibility="workspace")
            | Q(shared_with__id__in=team_dept_ids)
        ).distinct()

    dept_ids = list(api_key.departments.values_list("id", flat=True))
    team_ids = list(api_key.departments.values_list("team_id", flat=True).distinct())
    return qs.filter(
        Q(department_id__in=dept_ids)
        | Q(visibility="team", department__team_id__in=team_ids)
        | Q(visibility="workspace")
        | Q(shared_with__id__in=dept_ids)
    ).distinct()


def apply_oauth_connection_scope(request, qs):
    """
    Narrow a Skill queryset based on the MCP connection's voluntary scope.

    Only applies to OAuth-authenticated requests. The scope can only restrict
    visibility below the user's role, never widen it. Membership role-based
    filtering is applied first, then the connection scope narrows further.
    """
    from django.db.models import Q

    from apps.accounts.models import McpConnectionScope, ScopeType

    oauth_token = getattr(request, "oauth_token", None)
    if not oauth_token or not oauth_token.application_id:
        return _apply_membership_scope(request, qs)

    try:
        scope = (
            McpConnectionScope.objects.select_related("team")
            .prefetch_related("departments")
            .get(application_id=oauth_token.application_id)
        )
    except McpConnectionScope.DoesNotExist:
        return _apply_membership_scope(request, qs)

    qs = _apply_membership_scope(request, qs)

    if scope.scope_type == ScopeType.WORKSPACE:
        return qs

    if scope.scope_type == ScopeType.TEAM:
        team = scope.team
        if not team:
            return qs
        team_dept_ids = list(team.departments.values_list("id", flat=True))
        return qs.filter(
            Q(department__team=team)
            | Q(visibility="workspace")
            | Q(shared_with__id__in=team_dept_ids)
        ).distinct()

    dept_ids = list(scope.departments.values_list("id", flat=True))
    if not dept_ids:
        return qs
    team_ids = list(scope.departments.values_list("team_id", flat=True).distinct())
    return qs.filter(
        Q(department_id__in=dept_ids)
        | Q(visibility="team", department__team_id__in=team_ids)
        | Q(visibility="workspace")
        | Q(shared_with__id__in=dept_ids)
    ).distinct()


def _apply_membership_scope(request, qs):
    """Apply role-based filtering for OAuth users based on their membership."""
    from django.db.models import Q

    membership = getattr(request, "membership", None)
    if not membership:
        return qs

    role = membership.role

    if role == RoleChoices.ADMIN:
        return qs

    if role == RoleChoices.TEAM_MANAGER:
        team = membership.team
        if not team:
            return qs.none()
        team_dept_ids = list(team.departments.values_list("id", flat=True))
        return qs.filter(
            Q(department__team=team)
            | Q(visibility="workspace")
            | Q(shared_with__id__in=team_dept_ids)
        ).distinct()

    dept_ids = list(membership.departments.values_list("id", flat=True))
    team_ids = list(membership.departments.values_list("team_id", flat=True).distinct())
    return qs.filter(
        Q(department_id__in=dept_ids)
        | Q(visibility="team", department__team_id__in=team_ids)
        | Q(visibility="workspace")
        | Q(shared_with__id__in=dept_ids)
    ).distinct()
