from django.db import models


class SubscriptionStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    IN_TRIAL = "in_trial", "In Trial"
    CANCELLED = "cancelled", "Cancelled"
    NON_RENEWING = "non_renewing", "Non-Renewing"
    PAUSED = "paused", "Paused"
    FUTURE = "future", "Future"


class InvoiceStatus(models.TextChoices):
    PAID = "paid", "Paid"
    PAYMENT_DUE = "payment_due", "Payment Due"
    NOT_PAID = "not_paid", "Not Paid"
    VOIDED = "voided", "Voided"
    PENDING = "pending", "Pending"


class BillingPeriod(models.TextChoices):
    MONTHLY = "monthly", "Monthly"
    YEARLY = "yearly", "Yearly"
