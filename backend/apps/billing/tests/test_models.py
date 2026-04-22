import pytest

from apps.billing.enums import SubscriptionStatus
from apps.billing.tests.factories import (
    SubscriptionFactory,
    WorkspaceSubscriptionFactory,
)


@pytest.mark.django_db
class TestSubscriptionModel:
    def test_active_allows_access(self):
        sub = SubscriptionFactory(status=SubscriptionStatus.ACTIVE)
        assert sub.is_access_allowed is True

    def test_in_trial_allows_access(self):
        sub = SubscriptionFactory(status=SubscriptionStatus.IN_TRIAL)
        assert sub.is_access_allowed is True

    def test_cancelled_denies_access(self):
        sub = SubscriptionFactory(status=SubscriptionStatus.CANCELLED)
        assert sub.is_access_allowed is False

    def test_paused_denies_access(self):
        sub = SubscriptionFactory(status=SubscriptionStatus.PAUSED)
        assert sub.is_access_allowed is False

    def test_non_renewing_denies_access(self):
        sub = SubscriptionFactory(status=SubscriptionStatus.NON_RENEWING)
        assert sub.is_access_allowed is False

    def test_future_denies_access(self):
        sub = SubscriptionFactory(status=SubscriptionStatus.FUTURE)
        assert sub.is_access_allowed is False


@pytest.mark.django_db
class TestWorkspaceSubscription:
    def test_is_access_allowed_delegates(self):
        ws_sub = WorkspaceSubscriptionFactory(
            subscription__status=SubscriptionStatus.ACTIVE,
        )
        assert ws_sub.is_access_allowed is True

    def test_is_access_denied_when_cancelled(self):
        ws_sub = WorkspaceSubscriptionFactory(
            subscription__status=SubscriptionStatus.CANCELLED,
        )
        assert ws_sub.is_access_allowed is False
