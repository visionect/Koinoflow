from django.db import models

from apps.billing.enums import BillingPeriod, InvoiceStatus, SubscriptionStatus
from apps.common.models import BaseModel
from apps.orgs.enums import PlanChoices

ACTIVE_STATUSES = {SubscriptionStatus.ACTIVE, SubscriptionStatus.IN_TRIAL}


class Customer(BaseModel):
    chargebee_customer_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    workspace = models.OneToOneField(
        "orgs.Workspace",
        on_delete=models.CASCADE,
        related_name="customer",
    )
    email = models.EmailField()
    first_name = models.CharField(max_length=255, blank=True, default="")
    last_name = models.CharField(max_length=255, blank=True, default="")
    company = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "billing_customer"

    def __str__(self):
        return f"{self.email} ({self.workspace.name})"


class Plan(BaseModel):
    chargebee_plan_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    name = models.CharField(max_length=255)
    tier = models.CharField(
        max_length=20,
        choices=PlanChoices.choices,
        default=PlanChoices.STARTER,
    )
    price_cents = models.PositiveIntegerField(default=0)
    currency = models.CharField(max_length=3, default="USD")
    billing_period = models.CharField(
        max_length=20,
        choices=BillingPeriod.choices,
        default=BillingPeriod.MONTHLY,
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "billing_plan"
        constraints = [
            models.UniqueConstraint(
                fields=["tier", "billing_period"],
                name="uq_plan_tier_period",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.tier}/{self.billing_period})"


class Addon(BaseModel):
    chargebee_addon_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    name = models.CharField(max_length=255)
    price_cents = models.PositiveIntegerField(default=0)
    currency = models.CharField(max_length=3, default="USD")
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "billing_addon"

    def __str__(self):
        return self.name


class Subscription(BaseModel):
    chargebee_subscription_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    plan = models.ForeignKey(
        Plan,
        on_delete=models.PROTECT,
        related_name="subscriptions",
    )
    status = models.CharField(
        max_length=20,
        choices=SubscriptionStatus.choices,
        default=SubscriptionStatus.ACTIVE,
    )
    addons = models.ManyToManyField(
        Addon,
        through="SubscriptionAddon",
        blank=True,
    )
    current_term_start = models.DateTimeField(null=True, blank=True)
    current_term_end = models.DateTimeField(null=True, blank=True)
    trial_start = models.DateTimeField(null=True, blank=True)
    trial_end = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "billing_subscription"
        indexes = [
            models.Index(fields=["customer", "status"], name="idx_sub_customer_status"),
        ]

    def __str__(self):
        return f"{self.customer.email} — {self.plan.name} ({self.status})"

    @property
    def is_access_allowed(self):
        return self.status in ACTIVE_STATUSES


class SubscriptionAddon(BaseModel):
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.CASCADE,
        related_name="subscription_addons",
    )
    addon = models.ForeignKey(
        Addon,
        on_delete=models.CASCADE,
        related_name="subscription_addons",
    )
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = "billing_subscription_addon"
        constraints = [
            models.UniqueConstraint(
                fields=["subscription", "addon"],
                name="uq_subscription_addon",
            ),
        ]

    def __str__(self):
        return f"{self.addon.name} x{self.quantity}"


class Invoice(BaseModel):
    chargebee_invoice_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="invoices",
    )
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices",
    )
    status = models.CharField(
        max_length=20,
        choices=InvoiceStatus.choices,
        default=InvoiceStatus.PENDING,
    )
    total_cents = models.PositiveIntegerField(default=0)
    currency = models.CharField(max_length=3, default="USD")
    issued_at = models.DateTimeField(null=True, blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "billing_invoice"
        indexes = [
            models.Index(fields=["customer", "status"], name="idx_invoice_customer_status"),
        ]

    def __str__(self):
        return f"Invoice {self.id} — {self.customer.email} ({self.status})"


class WorkspaceSubscription(BaseModel):
    workspace = models.OneToOneField(
        "orgs.Workspace",
        on_delete=models.CASCADE,
        related_name="billing",
    )
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.CASCADE,
        related_name="workspace_links",
    )

    class Meta:
        db_table = "billing_workspace_subscription"

    def __str__(self):
        return f"{self.workspace.name} — {self.subscription.status}"

    @property
    def is_access_allowed(self):
        return self.subscription.is_access_allowed
