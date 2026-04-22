from django.contrib import admin
from django.urls import include, path
from oauth2_provider.views import TokenView

from apps.accounts.introspect import introspect_token
from apps.accounts.oauth_views import (
    KoinoflowAuthorizationView,
    authorization_server_metadata,
    dynamic_client_registration,
)
from apps.common.internal_tasks import run_scheduled_task, run_task

from .api import api

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
    path("api/internal/tasks/run", run_task, name="run_task"),
    path("api/internal/tasks/<slug:task_name>", run_scheduled_task),
    path("accounts/", include("allauth.urls")),
    # Custom introspect with workspace claims (must be before the DOT include)
    path("oauth/introspect/", introspect_token, name="oauth2-introspect"),
    # Branded consent page (shadows DOT's authorize view)
    path("oauth/authorize/", KoinoflowAuthorizationView.as_view()),
    path("oauth/", include("oauth2_provider.urls", namespace="oauth2_provider")),
    path("oauth/register", dynamic_client_registration, name="oauth2-dcr"),
    path(
        ".well-known/oauth-authorization-server",
        authorization_server_metadata,
        name="oauth2-as-metadata",
    ),
    # Claude.ai ignores authorization_endpoint / token_endpoint from OAuth
    # metadata and constructs /<path> from the issuer URL directly.
    # These root-level aliases work around that bug.
    path("authorize", KoinoflowAuthorizationView.as_view()),
    path("token", TokenView.as_view()),
    path("register", dynamic_client_registration),
]
