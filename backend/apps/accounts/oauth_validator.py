from oauth2_provider.oauth2_validators import OAuth2Validator

from apps.orgs.middleware import resolve_membership_for_user
from apps.orgs.models import CoreSlug, EntityType


class KoinoflowOAuthValidator(OAuth2Validator):
    """Extend the default DOT validator to include workspace context in token introspection.

    Workspace selection is deterministic (oldest membership first) so tokens
    issued for the same user consistently resolve to the same workspace.
    """

    def _workspace_claims(self, user):
        if not user or not user.is_authenticated:
            return {}

        membership = resolve_membership_for_user(user)
        if not membership:
            return {}

        ws = membership.workspace
        try:
            slug = CoreSlug.objects.get(entity_type=EntityType.WORKSPACE, entity_id=ws.id).slug
        except CoreSlug.DoesNotExist:
            slug = ""

        return {
            "workspace_id": str(ws.id),
            "workspace_slug": slug,
            "role": membership.role,
        }

    def get_additional_claims(self, request):
        return self._workspace_claims(request.user)

    def get_userinfo_claims(self, request):
        claims = super().get_userinfo_claims(request)
        claims.update(self._workspace_claims(request.user))
        return claims
