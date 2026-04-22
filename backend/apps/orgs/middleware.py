"""Workspace context resolution.

For an authenticated request, ``request.workspace`` / ``request.membership``
must be deterministic and pinned to a single workspace for the lifetime of
the request. Previous implementation used ``Membership.objects.filter(...).first()``
which returned an arbitrary row for users with ≥ 2 memberships, causing
cross-workspace data leakage.

Resolution order (first winner):

1. If API-key auth set ``request.workspace`` already, keep it.
2. If OAuth bearer auth set ``request.workspace`` already, keep it.
3. Look at an explicit ``X-Workspace-Slug`` header and validate membership.
4. Fall back to the user's oldest (``created_at`` ASC, ``id`` ASC) membership.

Step 4 matches the historical "default workspace" behaviour but is
deterministic. When the user later switches workspace the frontend should
send ``X-Workspace-Slug``.
"""

from apps.orgs.models import CoreSlug, EntityType, Membership


def _base_membership_queryset(user):
    return (
        Membership.objects.filter(user=user)
        .select_related("workspace", "team")
        .prefetch_related("departments")
        .order_by("created_at", "id")
    )


def resolve_membership_for_user(user, requested_slug: str | None = None):
    """Return the membership that should own ``request.workspace`` for this user.

    Returns ``None`` if the user has no memberships or the requested slug
    does not resolve to one of their workspaces.
    """
    qs = _base_membership_queryset(user)

    if requested_slug:
        try:
            core = CoreSlug.objects.get(entity_type=EntityType.WORKSPACE, slug=requested_slug)
        except CoreSlug.DoesNotExist:
            return None
        return qs.filter(workspace_id=core.entity_id).first()

    return qs.first()


class WorkspaceMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not hasattr(request, "workspace"):
            request.workspace = None
        if not hasattr(request, "membership"):
            request.membership = None

        if request.workspace is not None:
            return self.get_response(request)

        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return self.get_response(request)

        requested_slug = request.META.get("HTTP_X_WORKSPACE_SLUG") or ""
        requested_slug = requested_slug.strip() or None

        membership = resolve_membership_for_user(user, requested_slug)
        if membership:
            request.workspace = membership.workspace
            request.membership = membership
        return self.get_response(request)
