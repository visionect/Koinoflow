import factory

from apps.billing.enums import BillingPeriod, InvoiceStatus, SubscriptionStatus
from apps.billing.models import (
    Addon,
    Customer,
    Invoice,
    Plan,
    Subscription,
    SubscriptionAddon,
    WorkspaceSubscription,
)
from apps.orgs.enums import PlanChoices
from apps.orgs.tests.factories import WorkspaceFactory


class CustomerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Customer

    workspace = factory.SubFactory(WorkspaceFactory)
    email = factory.Faker("email")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    company = factory.Faker("company")


class PlanFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Plan

    name = factory.Sequence(lambda n: f"Plan {n}")
    tier = PlanChoices.STARTER
    price_cents = 2900
    billing_period = BillingPeriod.MONTHLY


class AddonFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Addon

    name = factory.Sequence(lambda n: f"Addon {n}")
    price_cents = 500


class SubscriptionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Subscription

    customer = factory.SubFactory(CustomerFactory)
    plan = factory.SubFactory(PlanFactory)
    status = SubscriptionStatus.ACTIVE


class SubscriptionAddonFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SubscriptionAddon

    subscription = factory.SubFactory(SubscriptionFactory)
    addon = factory.SubFactory(AddonFactory)
    quantity = 1


class InvoiceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Invoice

    customer = factory.SubFactory(CustomerFactory)
    subscription = factory.SubFactory(SubscriptionFactory)
    status = InvoiceStatus.PAID
    total_cents = 2900


class WorkspaceSubscriptionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = WorkspaceSubscription

    workspace = factory.LazyAttribute(lambda o: o.subscription.customer.workspace)
    subscription = factory.SubFactory(SubscriptionFactory)
