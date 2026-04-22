from django.conf import settings
from django.contrib.auth import logout
from ninja import Router, Schema

from apps.accounts.auth import api_or_session
from apps.common.throttles import AuthAnonThrottle, AuthUserThrottle

router = Router(tags=["auth"])


class UserSchema(Schema):
    id: str
    email: str
    first_name: str
    last_name: str


class MeResponse(Schema):
    user: UserSchema | None
    workspace_slug: str | None
    role: str | None
    subscription_status: str | None
    trial_end: str | None
    feature_flags: list[str]
    billing_enabled: bool


def _workspace_slug(workspace):
    if not workspace:
        return None
    from apps.orgs.models import CoreSlug

    try:
        return CoreSlug.objects.get(entity_type="workspace", entity_id=workspace.id).slug
    except CoreSlug.DoesNotExist:
        return None


@router.get(
    "/me",
    auth=api_or_session,
    response=MeResponse,
    throttle=[AuthAnonThrottle(), AuthUserThrottle()],
)
def me(request):
    """Return current authenticated user and their active workspace."""
    user = request.user if request.user.is_authenticated else None

    if user:
        from apps.orgs.middleware import resolve_membership_for_user

        requested_slug = request.META.get("HTTP_X_WORKSPACE_SLUG", "").strip() or None
        membership = resolve_membership_for_user(user, requested_slug)
        workspace = membership.workspace if membership else None
        return {
            "user": {
                "id": str(user.id),
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
            },
            "workspace_slug": _workspace_slug(workspace),
            "role": membership.role if membership else None,
            "subscription_status": _subscription_status(workspace),
            "trial_end": _trial_end(workspace),
            "feature_flags": _feature_flags(workspace),
            "billing_enabled": settings.ENABLE_BILLING,
        }

    workspace = getattr(request, "workspace", None)
    return {
        "user": None,
        "workspace_slug": _workspace_slug(workspace),
        "role": None,
        "subscription_status": _subscription_status(workspace),
        "trial_end": _trial_end(workspace),
        "feature_flags": _feature_flags(workspace),
        "billing_enabled": settings.ENABLE_BILLING,
    }


def _subscription_status(workspace):
    if not workspace:
        return None
    if not settings.ENABLE_BILLING:
        # Self-hosted mode: treat every workspace as permanently active so the
        # frontend never shows the trial banner or trial-expired redirect.
        return "active"
    from django.utils import timezone

    from apps.billing.enums import SubscriptionStatus
    from apps.billing.models import WorkspaceSubscription

    try:
        ws_sub = WorkspaceSubscription.objects.select_related("subscription").get(
            workspace=workspace
        )
        sub = ws_sub.subscription
        if (
            sub.status == SubscriptionStatus.IN_TRIAL
            and sub.trial_end
            and sub.trial_end < timezone.now()
        ):
            sub.status = SubscriptionStatus.CANCELLED
            sub.save(update_fields=["status", "updated_at"])
        return sub.status
    except WorkspaceSubscription.DoesNotExist:
        return None


def _trial_end(workspace):
    if not workspace or not settings.ENABLE_BILLING:
        return None
    from apps.billing.enums import SubscriptionStatus
    from apps.billing.models import WorkspaceSubscription

    try:
        ws_sub = WorkspaceSubscription.objects.select_related("subscription").get(
            workspace=workspace
        )
        sub = ws_sub.subscription
        if sub.status == SubscriptionStatus.IN_TRIAL and sub.trial_end:
            return sub.trial_end.isoformat()
        return None
    except WorkspaceSubscription.DoesNotExist:
        return None


def _feature_flags(workspace):
    if not workspace:
        return []
    from apps.orgs.models import WorkspaceFeatureFlag

    return list(
        WorkspaceFeatureFlag.objects.filter(workspace=workspace).values_list(
            "flag__name", flat=True
        )
    )


@router.post("/logout", auth=api_or_session, throttle=[AuthAnonThrottle(), AuthUserThrottle()])
def logout_view(request):
    """Clear session."""
    logout(request)
    return {"ok": True}
