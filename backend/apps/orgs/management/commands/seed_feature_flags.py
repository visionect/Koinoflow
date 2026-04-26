from django.core.management.base import BaseCommand

from apps.orgs.models import FeatureFlag

FEATURE_FLAGS = [
    "capture",
    "agents",
]


class Command(BaseCommand):
    help = "Seed built-in feature flags."

    def handle(self, *args, **options):
        created = 0
        for name in FEATURE_FLAGS:
            _, was_created = FeatureFlag.objects.get_or_create(name=name)
            if was_created:
                created += 1
                self.stdout.write(self.style.SUCCESS(f"  Created flag: {name}"))
            else:
                self.stdout.write(f"  Already exists: {name}")

        self.stdout.write(self.style.SUCCESS(f"Done. {created} flag(s) created."))
