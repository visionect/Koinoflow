from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.billing.enums import SubscriptionStatus
from apps.billing.tests.factories import (
    CustomerFactory,
    PlanFactory,
    SubscriptionFactory,
    WorkspaceSubscriptionFactory,
)
from apps.orgs.enums import RoleChoices
from apps.orgs.tests.factories import MembershipFactory


@pytest.mark.django_db
class TestMeSubscriptionStatus:
    @pytest.fixture(autouse=True)
    def enable_billing(self, settings):
        settings.ENABLE_BILLING = True

    def test_me_returns_null_when_no_subscription(self):
        membership = MembershipFactory(role=RoleChoices.ADMIN)
        client = Client()
        client.force_login(membership.user)
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        assert resp.json()["subscription_status"] is None

    def test_me_returns_active_status(self):
        membership = MembershipFactory(role=RoleChoices.ADMIN)
        plan = PlanFactory()
        customer = CustomerFactory(workspace=membership.workspace)
        sub = SubscriptionFactory(
            customer=customer,
            plan=plan,
            status=SubscriptionStatus.ACTIVE,
        )
        WorkspaceSubscriptionFactory(
            workspace=membership.workspace,
            subscription=sub,
        )

        client = Client()
        client.force_login(membership.user)
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        assert resp.json()["subscription_status"] == "active"

    def test_me_returns_in_trial_status(self):
        membership = MembershipFactory(role=RoleChoices.ADMIN)
        plan = PlanFactory()
        customer = CustomerFactory(workspace=membership.workspace)
        sub = SubscriptionFactory(
            customer=customer,
            plan=plan,
            status=SubscriptionStatus.IN_TRIAL,
        )
        WorkspaceSubscriptionFactory(
            workspace=membership.workspace,
            subscription=sub,
        )

        client = Client()
        client.force_login(membership.user)
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        assert resp.json()["subscription_status"] == "in_trial"

    def test_me_returns_cancelled_status(self):
        membership = MembershipFactory(role=RoleChoices.ADMIN)
        plan = PlanFactory()
        customer = CustomerFactory(workspace=membership.workspace)
        sub = SubscriptionFactory(
            customer=customer,
            plan=plan,
            status=SubscriptionStatus.CANCELLED,
        )
        WorkspaceSubscriptionFactory(
            workspace=membership.workspace,
            subscription=sub,
        )

        client = Client()
        client.force_login(membership.user)
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        assert resp.json()["subscription_status"] == "cancelled"

    def test_me_unauthenticated_has_null_subscription(self):
        client = Client()
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    def test_me_no_workspace_has_null_subscription(self):
        user = UserFactory()
        client = Client()
        client.force_login(user)
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        assert resp.json()["subscription_status"] is None

    def test_me_expires_trial_when_trial_end_is_past(self):
        membership = MembershipFactory(role=RoleChoices.ADMIN)
        plan = PlanFactory()
        customer = CustomerFactory(workspace=membership.workspace)
        sub = SubscriptionFactory(
            customer=customer,
            plan=plan,
            status=SubscriptionStatus.IN_TRIAL,
            trial_start=timezone.now() - timedelta(days=31),
            trial_end=timezone.now() - timedelta(days=1),
        )
        WorkspaceSubscriptionFactory(workspace=membership.workspace, subscription=sub)

        client = Client()
        client.force_login(membership.user)
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        assert resp.json()["subscription_status"] == "cancelled"
        sub.refresh_from_db()
        assert sub.status == SubscriptionStatus.CANCELLED

    def test_me_keeps_in_trial_when_trial_not_expired(self):
        membership = MembershipFactory(role=RoleChoices.ADMIN)
        plan = PlanFactory()
        customer = CustomerFactory(workspace=membership.workspace)
        sub = SubscriptionFactory(
            customer=customer,
            plan=plan,
            status=SubscriptionStatus.IN_TRIAL,
            trial_start=timezone.now(),
            trial_end=timezone.now() + timedelta(days=29),
        )
        WorkspaceSubscriptionFactory(workspace=membership.workspace, subscription=sub)

        client = Client()
        client.force_login(membership.user)
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        assert resp.json()["subscription_status"] == "in_trial"
        sub.refresh_from_db()
        assert sub.status == SubscriptionStatus.IN_TRIAL


@pytest.mark.django_db
class TestMeBillingDisabled:
    @pytest.fixture(autouse=True)
    def disable_billing(self, settings):
        settings.ENABLE_BILLING = False

    def test_me_reports_billing_disabled(self):
        membership = MembershipFactory(role=RoleChoices.ADMIN)
        client = Client()
        client.force_login(membership.user)
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        body = resp.json()
        assert body["billing_enabled"] is False

    def test_me_reports_active_when_billing_disabled_even_without_subscription(self):
        membership = MembershipFactory(role=RoleChoices.ADMIN)
        client = Client()
        client.force_login(membership.user)
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        assert resp.json()["subscription_status"] == "active"
        assert resp.json()["trial_end"] is None

    def test_me_ignores_cancelled_subscription_when_billing_disabled(self):
        membership = MembershipFactory(role=RoleChoices.ADMIN)
        plan = PlanFactory()
        customer = CustomerFactory(workspace=membership.workspace)
        sub = SubscriptionFactory(
            customer=customer,
            plan=plan,
            status=SubscriptionStatus.CANCELLED,
        )
        WorkspaceSubscriptionFactory(workspace=membership.workspace, subscription=sub)

        client = Client()
        client.force_login(membership.user)
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        assert resp.json()["subscription_status"] == "active"
