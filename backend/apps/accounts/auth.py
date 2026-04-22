from django.utils import timezone
from ninja.security import HttpBearer, django_auth
from oauth2_provider.models import AccessToken

from apps.orgs.middleware import resolve_membership_for_user
from apps.orgs.models import ApiKey, CoreSettings


class OAuthTokenAuthentication(HttpBearer):
    """Validate OAuth 2.1 Bearer tokens issued by django-oauth-toolkit."""

    def authenticate(self, request, token: str):
        if token.startswith("kf_"):
            return None

        try:
            access_token = AccessToken.objects.select_related("user", "application").get(
                token=token
            )
        except AccessToken.DoesNotExist:
            return None

        if access_token.is_expired():
            return None

        user = access_token.user
        if not user or not user.is_authenticated:
            return None

        requested_slug = request.META.get("HTTP_X_WORKSPACE_SLUG", "").strip() or None
        membership = resolve_membership_for_user(user, requested_slug)
        if requested_slug and membership is None:
            return None

        if membership:
            request.workspace = membership.workspace
            request.membership = membership

        request.user = user
        request.oauth_token = access_token
        return user


class ApiKeyAuthentication(HttpBearer):
    def authenticate(self, request, token: str):
        key_hash = ApiKey.hash_key(token)
        try:
            api_key = (
                ApiKey.objects.select_related("workspace", "team")
                .prefetch_related("departments")
                .get(key_hash=key_hash, is_active=True)
            )
        except ApiKey.DoesNotExist:
            return None

        if api_key.expires_at and api_key.expires_at < timezone.now():
            return None

        ws_settings = CoreSettings.objects.filter(
            workspace=api_key.workspace, team=None, department=None
        ).first()
        if ws_settings is not None and ws_settings.enable_api_access is False:
            return None

        request.workspace = api_key.workspace
        request.api_key = api_key
        return api_key


api_key_only = ApiKeyAuthentication()
api_or_session = [OAuthTokenAuthentication(), api_key_only, django_auth]
