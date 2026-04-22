from allauth.account.signals import user_signed_up
from django.dispatch import receiver


@receiver(user_signed_up)
def handle_new_user(request, user, **kwargs):
    """Frontend checks /auth/me — if workspace_slug is None, redirect to onboarding."""
    pass
