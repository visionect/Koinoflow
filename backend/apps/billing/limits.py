"""
Plan-level resource limits.

Add entries here when new plan tiers are introduced or limits change.
None means unlimited.
"""

from apps.orgs.enums import PlanChoices

# Maximum workspace members (active members + pending invitations combined).
MEMBER_LIMITS: dict[str, int | None] = {
    PlanChoices.TRIAL: 3,
    PlanChoices.STARTER: None,
    PlanChoices.GROWTH: None,
    PlanChoices.ENTERPRISE: None,
}


def get_member_limit(workspace) -> int | None:
    """
    Return the member limit for the workspace's current plan tier.
    Returns None if there is no limit or if billing info is unavailable.
    """
    try:
        ws_sub = workspace.billing  # WorkspaceSubscription via related_name
        tier = ws_sub.subscription.plan.tier
        return MEMBER_LIMITS.get(tier)
    except Exception:
        return None
