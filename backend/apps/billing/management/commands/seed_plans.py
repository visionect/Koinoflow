from django.core.management.base import BaseCommand
from django.db.models import Min

from apps.billing.enums import BillingPeriod
from apps.billing.models import Plan
from apps.orgs.enums import PlanChoices


class Command(BaseCommand):
    help = "Create or update default subscription plans."

    def _deduplicate_plans(self):
        """Migrate legacy Trial rows and remove duplicate (tier, billing_period) rows."""
        from django.db.models import Count

        migrated = Plan.objects.filter(name="Trial", tier=PlanChoices.STARTER).update(
            tier=PlanChoices.TRIAL
        )
        if migrated:
            self.stdout.write(
                self.style.WARNING(f"Migrated {migrated} Trial plan(s) to tier=trial.")
            )

        dupes = (
            Plan.objects.values("tier", "billing_period")
            .annotate(cnt=Count("id"), keep=Min("created_at"))
            .filter(cnt__gt=1)
        )
        deleted = 0
        for dup in dupes:
            qs = Plan.objects.filter(
                tier=dup["tier"],
                billing_period=dup["billing_period"],
            ).exclude(created_at=dup["keep"])
            deleted += qs.count()
            qs.delete()
        if deleted:
            self.stdout.write(self.style.WARNING(f"Removed {deleted} duplicate plan row(s)."))

    def handle(self, *args, **options):
        self._deduplicate_plans()

        plan_rows = (
            {
                "name": "Trial",
                "tier": PlanChoices.TRIAL,
                "price_cents": 0,
                "currency": "USD",
                "billing_period": BillingPeriod.MONTHLY,
                "is_active": True,
            },
            {
                "name": "Starter",
                "tier": PlanChoices.STARTER,
                "price_cents": 4900,
                "currency": "USD",
                "billing_period": BillingPeriod.MONTHLY,
                "is_active": True,
            },
            {
                "name": "Growth",
                "tier": PlanChoices.GROWTH,
                "price_cents": 19900,
                "currency": "USD",
                "billing_period": BillingPeriod.MONTHLY,
                "is_active": True,
            },
            {
                "name": "Enterprise",
                "tier": PlanChoices.ENTERPRISE,
                "price_cents": 0,
                "currency": "USD",
                "billing_period": BillingPeriod.MONTHLY,
                "is_active": True,
            },
        )

        created_count = 0
        updated_count = 0

        for row in plan_rows:
            _, created = Plan.objects.update_or_create(
                tier=row["tier"],
                billing_period=row["billing_period"],
                defaults={
                    "name": row["name"],
                    "price_cents": row["price_cents"],
                    "currency": row["currency"],
                    "is_active": row["is_active"],
                },
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(f"Seeded plans. created={created_count} updated={updated_count}")
        )
