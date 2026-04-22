from decouple import config

from .base import *  # noqa: F401, F403
from .base import DATABASES, MIDDLEWARE

SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Static files for containerized deployments
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Keep DB connections warm between requests for production deployments.
DATABASES["default"]["CONN_MAX_AGE"] = 300
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

SOCIALACCOUNT_LOGIN_ON_GET = True

FRONTEND_URL = config("FRONTEND_URL")
LOGIN_REDIRECT_URL = FRONTEND_URL + "/"
ACCOUNT_LOGOUT_REDIRECT_URL = FRONTEND_URL + "/login"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "format": (
                '{"timestamp":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s",'
                '"message":"%(message)s"}'
            ),
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}
