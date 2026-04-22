"""
Email service abstraction.

To swap providers, change EMAIL_BACKEND_CLASS in settings to a different
EmailBackend subclass. The rest of the codebase stays unchanged.

Supported backends:
  - apps.common.email_service.ResendEmailBackend   (default, production)
  - apps.common.email_service.ConsoleEmailBackend  (local dev)
  - apps.common.email_service.SilentEmailBackend   (tests)
"""

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from django.conf import settings

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class EmailBackend(ABC):
    @abstractmethod
    def send(
        self,
        *,
        to: str,
        subject: str,
        html: str,
        text: str | None = None,
        from_email: str | None = None,
        reply_to: str | None = None,
    ) -> None:
        """Send a single transactional email. Raises on hard failure."""


class ResendEmailBackend(EmailBackend):
    """Production email backend using Resend (https://resend.com)."""

    def send(
        self,
        *,
        to: str,
        subject: str,
        html: str,
        text: str | None = None,
        from_email: str | None = None,
        reply_to: str | None = None,
    ) -> None:
        import resend

        api_key = getattr(settings, "RESEND_API_KEY", "")
        if not api_key:
            logger.error("RESEND_API_KEY is not configured — email not sent to %s", to)
            return

        resend.api_key = api_key

        sender = from_email or getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com")

        params: dict = {
            "from": sender,
            "to": [to],
            "subject": subject,
            "html": html,
        }
        if text:
            params["text"] = text
        if reply_to:
            params["reply_to"] = [reply_to]

        local, _, domain = to.partition("@")
        masked_to = f"{to[0]}***@{domain}" if domain else "***"
        try:
            resend.Emails.send(params)
            logger.info("Email sent via Resend to %s (subject: %s)", masked_to, subject)
        except Exception:
            logger.exception(
                "Resend failed to deliver email to %s (subject: %s)", masked_to, subject
            )
            raise


class ConsoleEmailBackend(EmailBackend):
    """Prints email to stdout. Use in local development."""

    def send(
        self,
        *,
        to: str,
        subject: str,
        html: str,
        text: str | None = None,
        from_email: str | None = None,
        reply_to: str | None = None,
    ) -> None:
        sender = from_email or getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com")
        print(
            f"\n{'=' * 60}\n"
            f"[EMAIL]\n"
            f"From:    {sender}\n"
            f"To:      {to}\n"
            f"Subject: {subject}\n"
            f"{'=' * 60}\n"
            f"{text or html}\n"
            f"{'=' * 60}\n"
        )


class SilentEmailBackend(EmailBackend):
    """Discards all emails silently. Use in tests."""

    def send(self, **kwargs) -> None:  # type: ignore[override]
        pass


def get_email_backend() -> EmailBackend:
    """
    Returns the configured email backend instance.

    Override EMAIL_BACKEND_CLASS in settings to switch providers.
    Defaults to ResendEmailBackend in production, ConsoleEmailBackend in DEBUG.
    """
    backend_path: str = getattr(
        settings,
        "EMAIL_BACKEND_CLASS",
        "apps.common.email_service.ConsoleEmailBackend"
        if getattr(settings, "DEBUG", False)
        else "apps.common.email_service.ResendEmailBackend",
    )

    module_path, class_name = backend_path.rsplit(".", 1)
    import importlib

    module = importlib.import_module(module_path)
    backend_cls = getattr(module, class_name)
    return backend_cls()
