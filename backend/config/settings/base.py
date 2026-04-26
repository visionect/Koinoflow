import ssl
from pathlib import Path

import dj_database_url
from celery.schedules import crontab
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config("SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS = [h for h in config("ALLOWED_HOSTS", default="").split(",") if h]

ADMIN_IP_ALLOWLIST = config("ADMIN_IP_ALLOWLIST", default="")
ADMIN_IP_GATE_ENABLED = config("ADMIN_IP_GATE_ENABLED", default=True, cast=bool)
ADMIN_BYPASS_IP_GATE = config("ADMIN_BYPASS_IP_GATE", default=False, cast=bool)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    # Third party
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "allauth.socialaccount.providers.github",
    "django_celery_beat",
    "corsheaders",
    "oauth2_provider",
    # Local
    "apps.common",
    "apps.accounts",
    "apps.orgs",
    "apps.agents",
    "apps.skills",
    "apps.usage",
    "apps.connectors",
    "apps.billing",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.common.middleware.BearerTokenCSRFExemptMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "apps.common.admin.AdminSessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "apps.common.admin_ip_gate.AdminIpAllowlistMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.common.security_headers.SecurityHeadersMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "apps.orgs.middleware.WorkspaceMiddleware",
]

ROOT_URLCONF = "config.urls"
AUTH_USER_MODEL = "accounts.User"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SITE_ID = 1

DATABASES = {
    "default": dj_database_url.config(default=config("DATABASE_URL")),
}

_redis_url = config("REDIS_URL", default="redis://localhost:6379/0")
_redis_ca_cert_path = config("REDIS_CA_CERT_PATH", default="")
_redis_verify_mode = config("REDIS_SSL_VERIFY_MODE", default="required").strip().lower()
_redis_options: dict = {}
_celery_ssl_options: dict = {}


def _resolve_redis_cert_reqs():
    """Return the ssl.VerifyMode for Redis connections.

    Production default is ``required``. ``REDIS_SSL_VERIFY_MODE=none`` is
    accepted as an explicit escape hatch (with a warning) for environments
    where the CA bundle cannot be provisioned yet — set this env var
    deliberately, never by accident. With ``required`` the caller must
    supply ``REDIS_CA_CERT_PATH`` pointing at the Memorystore CA bundle.
    """
    mode = _redis_verify_mode
    if mode == "none":
        import logging as _log

        _log.getLogger(__name__).warning(
            "REDIS_SSL_VERIFY_MODE=none: Redis TLS cert verification is disabled"
        )
        return ssl.CERT_NONE
    if mode == "optional":
        return ssl.CERT_OPTIONAL
    return ssl.CERT_REQUIRED


if _redis_url.startswith("rediss://"):
    _cert_reqs = _resolve_redis_cert_reqs()
    _redis_options["ssl_cert_reqs"] = _cert_reqs
    _celery_ssl_options["ssl_cert_reqs"] = _cert_reqs
    if _redis_ca_cert_path and _cert_reqs != ssl.CERT_NONE:
        _redis_options["ssl_ca_certs"] = _redis_ca_cert_path
        _celery_ssl_options["ssl_ca_certs"] = _redis_ca_cert_path

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": _redis_url,
        "OPTIONS": _redis_options,
    }
}

# Celery
CELERY_BROKER_URL = _redis_url
CELERY_RESULT_BACKEND = _redis_url
if _redis_url.startswith("rediss://"):
    CELERY_BROKER_USE_SSL = dict(_celery_ssl_options)
    CELERY_REDIS_BACKEND_USE_SSL = dict(_celery_ssl_options)

CELERY_BEAT_SCHEDULE = {
    "staleness-check-daily": {
        "task": "staleness_check",
        "schedule": crontab(hour=9, minute=0),
    },
    "confluence-token-refresh-check": {
        "task": "confluence_token_refresh_check",
        "schedule": crontab(minute=0),
    },
}

# Task backend selection
TASK_BACKEND = config("TASK_BACKEND", default="celery")

# Cloud Tasks (used when TASK_BACKEND=cloudtasks)
CLOUD_TASKS_PROJECT = config("CLOUD_TASKS_PROJECT", default="")
CLOUD_TASKS_LOCATION = config("CLOUD_TASKS_LOCATION", default="")
CLOUD_TASKS_QUEUE = config("CLOUD_TASKS_QUEUE", default="default")
CLOUD_TASKS_SERVICE_URL = config("CLOUD_TASKS_SERVICE_URL", default="")
CLOUD_TASKS_SERVICE_ACCOUNT = config("CLOUD_TASKS_SERVICE_ACCOUNT", default="")

# Auth
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = "mandatory"

SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True

SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
        "APP": {
            "client_id": config("GOOGLE_CLIENT_ID", default=""),
            "secret": config("GOOGLE_CLIENT_SECRET", default=""),
        },
    },
    "github": {
        "SCOPE": ["user:email"],
        "APP": {
            "client_id": config("GITHUB_CLIENT_ID", default=""),
            "secret": config("GITHUB_CLIENT_SECRET", default=""),
        },
    },
}

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
ACCOUNT_LOGOUT_REDIRECT_URL = "/login"

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False

# CORS (for frontend on different port)
CORS_ALLOWED_ORIGINS = [
    o for o in config("CORS_ALLOWED_ORIGINS", default="http://localhost:5173").split(",") if o
]
CORS_ALLOW_CREDENTIALS = True

CSRF_TRUSTED_ORIGINS = [
    o for o in config("CSRF_TRUSTED_ORIGINS", default="http://localhost:5173").split(",") if o
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Email
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="noreply@example.com")
INVITATION_FROM_EMAIL = config("INVITATION_FROM_EMAIL", default=DEFAULT_FROM_EMAIL)
ALERTS_FROM_EMAIL = config("ALERTS_FROM_EMAIL", default=DEFAULT_FROM_EMAIL)

# Billing
# When False (default), self-hosted deployments skip all trial/subscription
# gating: /auth/me reports billing as inactive-but-allowed, new workspaces
# are not wrapped in a trial Subscription, and the frontend hides the trial
# banner + trial-expired redirect. Set to True for hosted/commercial
# deployments that run the billing flow.
ENABLE_BILLING = config("ENABLE_BILLING", default=False, cast=bool)

# Resend (transactional email provider)
# Set EMAIL_BACKEND_CLASS to swap providers without touching send-site code:
#   apps.common.email_service.ResendEmailBackend   — production (default when DEBUG=False)
#   apps.common.email_service.ConsoleEmailBackend  — local dev   (default when DEBUG=True)
#   apps.common.email_service.SilentEmailBackend   — test suites
RESEND_API_KEY = config("RESEND_API_KEY", default="")
# Override in local.py (ConsoleEmailBackend) or via env var to switch providers.
EMAIL_BACKEND_CLASS = config(
    "EMAIL_BACKEND_CLASS",
    default="apps.common.email_service.ResendEmailBackend",
)

# Django Ninja throttle rates (scope -> "requests/period")
# Atlassian OAuth 2.0 (Confluence connector)
ATLASSIAN_CLIENT_ID = config("ATLASSIAN_CLIENT_ID", default="")
ATLASSIAN_CLIENT_SECRET = config("ATLASSIAN_CLIENT_SECRET", default="")
ATLASSIAN_WEBHOOK_SECRET = config("ATLASSIAN_WEBHOOK_SECRET", default="")
ATLASSIAN_OAUTH_SCOPES = [
    "read:page:confluence",
    "read:space:confluence",
    "read:content-details:confluence",
    "offline_access",
]

# Connector token encryption (Fernet key). Generate with:
# python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
CONNECTOR_ENCRYPTION_KEY = config("CONNECTOR_ENCRYPTION_KEY", default="")

# ── Capture AI extraction pipeline ──────────────────────────────────────
# Smithery MCP registry API key (optional — degrades gracefully when absent)
SMITHERY_API_KEY = config("SMITHERY_API_KEY", default="")
# How long to cache Smithery registry results in Redis (seconds). Default: 24 h.
SMITHERY_CACHE_TTL_SECONDS = config("SMITHERY_CACHE_TTL_SECONDS", default=86_400, cast=int)
# Lightweight model used for page scoring (Phase 1)
CAPTURE_SCORING_MODEL = config("CAPTURE_SCORING_MODEL", default="gemini-3-flash-preview")
# Flagship model used for process extraction (Phase 2)
CAPTURE_EXTRACTION_MODEL = config("CAPTURE_EXTRACTION_MODEL", default="gemini-3-flash-preview")
# Model used for AI-powered process generation from unstructured documentation
PROCESS_GENERATION_MODEL = config("PROCESS_GENERATION_MODEL", default="gemini-3-flash-preview")
# Model used for semantic process discovery embeddings
PROCESS_DISCOVERY_EMBEDDING_MODEL = config(
    "PROCESS_DISCOVERY_EMBEDDING_MODEL", default="gemini-embedding-2"
)
PROCESS_DISCOVERY_EMBEDDING_DIMENSIONS = config(
    "PROCESS_DISCOVERY_EMBEDDING_DIMENSIONS", default=768, cast=int
)
# Vertex AI project and location (shared with other Vertex AI integrations)
VERTEX_PROJECT_ID = config("VERTEX_PROJECT_ID", default=config("GCP_PROJECT_ID", default=""))
VERTEX_LOCATION = config("VERTEX_LOCATION", default="global")
LOCAL_ENV = config("LOCAL_ENV", default=False, cast=bool)
VERTEX_CLIENT_PROJECT_ID = config("VERTEX_CLIENT_PROJECT_ID", default="")
VERTEX_CLIENT_PRIVATE_KEY_ID = config("VERTEX_CLIENT_PRIVATE_KEY_ID", default="")
VERTEX_CLIENT_PRIVATE_KEY = config("VERTEX_CLIENT_PRIVATE_KEY", default="")
VERTEX_CLIENT_EMAIL = config("VERTEX_CLIENT_EMAIL", default="")
VERTEX_CLIENT_ID = config("VERTEX_CLIENT_ID", default="")
VERTEX_CLIENT_CERT_URL = config("VERTEX_CLIENT_CERT_URL", default="")

# Base URL this app is reachable at (used for OAuth callbacks and webhook registration)
APP_BASE_URL = config("APP_BASE_URL", default="http://localhost:8002")
FRONTEND_URL = config("FRONTEND_URL", default="http://localhost:5173")
INTERNAL_TASK_TOKEN = config("INTERNAL_TASK_TOKEN", default="")

# ── OAuth 2.1 (django-oauth-toolkit) ────────────────────────────────────
OAUTH2_PROVIDER_APPLICATION_MODEL = "oauth2_provider.Application"
OAUTH2_PROVIDER_ACCESS_TOKEN_MODEL = "oauth2_provider.AccessToken"
OAUTH2_PROVIDER_REFRESH_TOKEN_MODEL = "oauth2_provider.RefreshToken"

OAUTH2_PROVIDER = {
    "SCOPES": {
        "processes:read": "Read processes in your workspace",
        "processes:write": "Create and update processes in your workspace",
        "usage:write": "Log usage events",
    },
    "DEFAULT_SCOPES": ["processes:read", "processes:write", "usage:write"],
    "PKCE_REQUIRED": True,
    "ACCESS_TOKEN_EXPIRE_SECONDS": 3600,
    "REFRESH_TOKEN_EXPIRE_SECONDS": 60 * 60 * 24 * 30,
    "ROTATE_REFRESH_TOKEN": True,
    "ALLOWED_REDIRECT_URI_SCHEMES": ["https", "http", "cursor", "vscode"],
    "OAUTH2_VALIDATOR_CLASS": "apps.accounts.oauth_validator.KoinoflowOAuthValidator",
    "OIDC_ENABLED": False,
    "RESOURCE_SERVER_TOKEN_CACHING_SECONDS": 60,
}

# MCP resource server credentials for token introspection
MCP_INTROSPECT_CLIENT_ID = config("MCP_INTROSPECT_CLIENT_ID", default="")
MCP_INTROSPECT_CLIENT_SECRET = config("MCP_INTROSPECT_CLIENT_SECRET", default="")

NINJA_DEFAULT_THROTTLE_RATES = {
    "global_anon": "60/min",
    "global_auth": "300/min",
    "auth_anon": "10/min",
    "auth_user": "30/min",
    "create_anon": "5/min",
    "create_auth": "30/min",
    "invite": "20/hour",
    "webhook": "600/min",
    "ai_extraction": "20/hour",
    "api_key_create": "10/hour",
    "mutation": "60/min",
    "read": "120/min",
    "usage_log": "300/min",
    "import": "10/min",
    "connector_sync": "5/hour",
}
