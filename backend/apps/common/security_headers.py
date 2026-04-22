"""Content-Security-Policy and Permissions-Policy for Django-rendered pages.

The SPA is served from GCS with its own CSP configured at the HTTPS LB
(see ``infra/terraform/load_balancer.tf``). This middleware covers the
Django-rendered surface: /admin, /accounts, /oauth/authorize. The SPA
frontend never hits this middleware because static SPA traffic never
reaches Cloud Run.
"""

from django.conf import settings

_DEFAULT_PERMISSIONS_POLICY = (
    "accelerometer=(), ambient-light-sensor=(), autoplay=(), battery=(), "
    "camera=(), clipboard-read=(), clipboard-write=(self), display-capture=(), "
    "document-domain=(), encrypted-media=(), fullscreen=(self), gamepad=(), "
    "geolocation=(), gyroscope=(), hid=(), idle-detection=(), local-fonts=(), "
    "magnetometer=(), microphone=(), midi=(), payment=(), picture-in-picture=(), "
    "publickey-credentials-get=(), screen-wake-lock=(), serial=(), "
    "speaker-selection=(), usb=(), web-share=(), xr-spatial-tracking=()"
)

# Django admin requires 'unsafe-inline' for its jQuery + inline attributes;
# it does not use remote CDNs in our setup. OAuth consent pages are rendered
# from DOT templates which may also use inline. We keep the scope narrow:
# only self and inline for scripts/styles, no data: URLs for scripts, no
# arbitrary third-party origins.
_DEFAULT_CSP = (
    "default-src 'self'; "
    "base-uri 'self'; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
    "object-src 'none'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "upgrade-insecure-requests"
)


class SecurityHeadersMiddleware:
    """Attach CSP, Permissions-Policy and X-Robots-Tag to backend responses."""

    def __init__(self, get_response):
        self.get_response = get_response
        self._csp = getattr(settings, "CONTENT_SECURITY_POLICY", _DEFAULT_CSP)
        self._permissions = getattr(settings, "PERMISSIONS_POLICY", _DEFAULT_PERMISSIONS_POLICY)

    def __call__(self, request):
        response = self.get_response(request)
        if self._csp and "Content-Security-Policy" not in response:
            response["Content-Security-Policy"] = self._csp
        if self._permissions and "Permissions-Policy" not in response:
            response["Permissions-Policy"] = self._permissions
        if "Referrer-Policy" not in response:
            response["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if "Cross-Origin-Opener-Policy" not in response:
            response["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
        if "X-Content-Type-Options" not in response:
            response["X-Content-Type-Options"] = "nosniff"
        path = request.path or ""
        if path.startswith("/admin/"):
            response["X-Robots-Tag"] = "noindex, nofollow"
        return response
