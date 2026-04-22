"""Middleware that gives Django admin its own session cookie.

This prevents admin login/logout from destroying the frontend user's
session.  Admin pages (any path starting with /admin/) read and write
a separate cookie (`kf_admin_sessionid`) instead of the default
`sessionid`.
"""

from django.conf import settings
from django.contrib.sessions.backends.db import SessionStore

ADMIN_COOKIE = "kf_admin_sessionid"
ADMIN_PREFIX = "/admin/"


class AdminSessionMiddleware:
    """Swap sessions so /admin/ uses its own cookie."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith(ADMIN_PREFIX):
            return self.get_response(request)

        original_session = request.session

        admin_session_key = request.COOKIES.get(ADMIN_COOKIE)
        store = SessionStore(session_key=admin_session_key)

        if admin_session_key and not store.exists(admin_session_key):
            store = SessionStore()

        request.session = store

        response = self.get_response(request)

        if request.session.modified or not request.session.session_key:
            request.session.save()

        if request.session.session_key:
            response.set_cookie(
                ADMIN_COOKIE,
                request.session.session_key,
                httponly=True,
                samesite="Lax",
                secure=getattr(settings, "SESSION_COOKIE_SECURE", False),
                max_age=settings.SESSION_COOKIE_AGE,
                path=ADMIN_PREFIX,
            )

        request.session = original_session

        return response
