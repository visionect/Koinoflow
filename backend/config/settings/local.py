from decouple import config

from .base import *  # noqa: F401, F403

DEBUG = True

# Test/local encryption key — do NOT use in production
CONNECTOR_ENCRYPTION_KEY = config(
    "CONNECTOR_ENCRYPTION_KEY",
    default="G1ZiCgSiNASQ9Uz8tu3xtHBJNeQKkMt-NuoPFdgNEsY=",
)

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
EMAIL_BACKEND_CLASS = "apps.common.email_service.ConsoleEmailBackend"
ACCOUNT_EMAIL_VERIFICATION = "none"

TASK_BACKEND = "sync"

FRONTEND_URL = config("FRONTEND_URL", default="http://localhost:5173")
LOGIN_REDIRECT_URL = FRONTEND_URL + "/"
ACCOUNT_LOGOUT_REDIRECT_URL = FRONTEND_URL + "/login"

SOCIALACCOUNT_LOGIN_ON_GET = True
