from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.billing.enums import BillingPeriod, SubscriptionStatus
from apps.billing.models import Customer, Plan, Subscription, WorkspaceSubscription
from apps.orgs.enums import PlanChoices, RoleChoices
from apps.orgs.models import Membership, Workspace


class Command(BaseCommand):
    help = "Onboard the internal workspace with an active Enterprise subscription."

    INTERNAL_ADMIN_EMAIL = "gasper.skornik@gmail.com"
    INTERNAL_COMPANY_NAME = "Koinoflow"

    def handle(self, *args, **options):
        workspace_qs = Workspace.objects.order_by("created_at")
        workspace_count = workspace_qs.count()
        if workspace_count == 0:
            raise CommandError("No workspace found. Expected exactly one existing workspace.")
        if workspace_count > 1:
            raise CommandError(
                f"Found {workspace_count} workspaces. Expected exactly one existing workspace."
            )
        workspace = workspace_qs.first()

        try:
            admin_user = User.objects.get(email=self.INTERNAL_ADMIN_EMAIL)
        except User.DoesNotExist as exc:
            raise CommandError(
                f"Internal admin user {self.INTERNAL_ADMIN_EMAIL} does not exist."
            ) from exc

        now = timezone.now()

        with transaction.atomic():
            membership, membership_created = Membership.objects.get_or_create(
                user=admin_user,
                workspace=workspace,
                defaults={"role": RoleChoices.ADMIN},
            )
            membership_role_updated = False
            if membership.role != RoleChoices.ADMIN:
                membership.role = RoleChoices.ADMIN
                membership.save(update_fields=["role", "updated_at"])
                membership_role_updated = True

            plan, plan_created = Plan.objects.update_or_create(
                tier=PlanChoices.ENTERPRISE,
                billing_period=BillingPeriod.MONTHLY,
                defaults={
                    "name": "Enterprise",
                    "price_cents": 0,
                    "currency": "USD",
                    "is_active": True,
                },
            )

            customer, customer_created = Customer.objects.update_or_create(
                workspace=workspace,
                defaults={
                    "email": self.INTERNAL_ADMIN_EMAIL,
                    "first_name": admin_user.first_name,
                    "last_name": admin_user.last_name,
                    "company": self.INTERNAL_COMPANY_NAME,
                },
            )

            workspace_link = (
                WorkspaceSubscription.objects.select_related("subscription")
                .filter(workspace=workspace)
                .first()
            )
            if workspace_link:
                subscription = workspace_link.subscription
                subscription_created = False
            else:
                subscription = (
                    Subscription.objects.filter(customer=customer, plan=plan)
                    .order_by("-created_at")
                    .first()
                )
                if subscription is None:
                    subscription = Subscription.objects.create(
                        customer=customer,
                        plan=plan,
                        status=SubscriptionStatus.ACTIVE,
                        current_term_start=now,
                        current_term_end=None,
                        trial_start=None,
                        trial_end=None,
                        cancelled_at=None,
                    )
                    subscription_created = True
                else:
                    subscription_created = False

            sub_update_fields = []
            if subscription.customer_id != customer.id:
                subscription.customer = customer
                sub_update_fields.append("customer")
            if subscription.plan_id != plan.id:
                subscription.plan = plan
                sub_update_fields.append("plan")
            if subscription.status != SubscriptionStatus.ACTIVE:
                subscription.status = SubscriptionStatus.ACTIVE
                sub_update_fields.append("status")
            if subscription.current_term_start is None:
                subscription.current_term_start = now
                sub_update_fields.append("current_term_start")
            if subscription.current_term_end is not None:
                subscription.current_term_end = None
                sub_update_fields.append("current_term_end")
            if subscription.trial_start is not None:
                subscription.trial_start = None
                sub_update_fields.append("trial_start")
            if subscription.trial_end is not None:
                subscription.trial_end = None
                sub_update_fields.append("trial_end")
            if subscription.cancelled_at is not None:
                subscription.cancelled_at = None
                sub_update_fields.append("cancelled_at")
            if sub_update_fields:
                subscription.save(update_fields=[*sub_update_fields, "updated_at"])

            _, workspace_link_created = WorkspaceSubscription.objects.update_or_create(
                workspace=workspace,
                defaults={"subscription": subscription},
            )

        self.stdout.write(self.style.SUCCESS("Internal workspace onboarding complete."))
        self.stdout.write(f"workspace_id={workspace.id}")
        self.stdout.write(f"admin_email={self.INTERNAL_ADMIN_EMAIL}")
        self.stdout.write(f"membership_created={membership_created}")
        self.stdout.write(f"membership_role_updated={membership_role_updated}")
        self.stdout.write(f"plan_created={plan_created}")
        self.stdout.write(f"customer_created={customer_created}")
        self.stdout.write(f"subscription_created={subscription_created}")
        self.stdout.write(f"workspace_subscription_created={workspace_link_created}")
        self.stdout.write(f"subscription_status={subscription.status}")
        self.stdout.write(f"subscription_plan_tier={plan.tier}")
