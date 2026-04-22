class BearerTokenCSRFExemptMiddleware:
    """Mark Bearer-authenticated API requests as CSRF-exempt.

    When an ``Authorization: Bearer`` or ``Authorization: Api-Key`` header is
    present, we want to skip Django's CsrfViewMiddleware — the request is not
    cookie-authenticated and there is no session to ride.

    Security invariant enforced here: when a bearer header is present we also
    strip the session cookie before SessionMiddleware / AuthenticationMiddleware
    can load it. That prevents a CSRF where an attacker attaches a bogus
    ``Authorization: Bearer x`` header to ride the victim's session cookie:
    with the session cookie gone, session-based auth fails, the downstream
    Ninja auth classes fall back to the bearer (which we haven't validated
    yet — but any write they do will be as whoever the bearer resolves to,
    not as the cookie-identified user).

    This middleware MUST be installed **before** SessionMiddleware in the
    MIDDLEWARE list so that the cookie strip happens before the session is
    loaded, but **before** CsrfViewMiddleware so the flag is honoured.
    """

    _BEARER_PREFIXES = ("Bearer ", "Api-Key ")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        auth = request.META.get("HTTP_AUTHORIZATION", "")
        if auth.startswith(self._BEARER_PREFIXES):
            for cookie in ("sessionid", "csrftoken", "kf_admin_sessionid"):
                request.COOKIES.pop(cookie, None)
            request._dont_enforce_csrf_checks = True
        return self.get_response(request)
