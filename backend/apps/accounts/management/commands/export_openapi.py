import json

from config.api import api
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Export the Django Ninja OpenAPI schema as JSON."

    def handle(self, *args, **options):
        schema = api.get_openapi_schema()
        self.stdout.write(json.dumps(schema, indent=2))
