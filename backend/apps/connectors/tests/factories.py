import factory
from django.utils import timezone

from apps.connectors.enums import (
    AutomationTier,
    CandidateStatus,
    CredentialStatus,
    ProviderChoices,
    SyncJobStatus,
    SyncJobType,
)
from apps.connectors.models import (
    CaptureCandidate,
    ConnectorCredential,
    ExtractionJob,
    SyncedPage,
    SyncJob,
    encrypt_token,
)


class ConnectorCredentialFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ConnectorCredential

    workspace = factory.SubFactory("apps.orgs.tests.factories.WorkspaceFactory")
    provider = ProviderChoices.CONFLUENCE
    cloud_id = factory.Sequence(lambda n: f"cloud-{n}")
    site_url = factory.Sequence(lambda n: f"https://tenant-{n}.atlassian.net")
    access_token = factory.LazyFunction(lambda: encrypt_token("test-access-token"))
    refresh_token = factory.LazyFunction(lambda: encrypt_token("test-refresh-token"))
    token_expires_at = factory.LazyFunction(
        lambda: timezone.now() + __import__("datetime").timedelta(hours=1)
    )
    scopes = "read:confluence-content.all read:confluence-space.summary offline_access"
    status = CredentialStatus.ACTIVE
    connected_by = factory.SubFactory("apps.accounts.tests.factories.UserFactory")


class SyncJobFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SyncJob

    credential = factory.SubFactory(ConnectorCredentialFactory)
    job_type = SyncJobType.FULL
    status = SyncJobStatus.COMPLETED
    pages_scanned = 10
    pages_updated = 3
    started_at = factory.LazyFunction(timezone.now)
    finished_at = factory.LazyFunction(timezone.now)


class SyncedPageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SyncedPage

    credential = factory.SubFactory(ConnectorCredentialFactory)
    external_id = factory.Sequence(lambda n: f"page-{n}")
    external_url = factory.Sequence(
        lambda n: f"https://tenant-0.atlassian.net/wiki/spaces/ENG/pages/{n}"
    )
    space_key = "ENG"
    title = factory.Sequence(lambda n: f"Page {n}")
    content_md = "# Hello\n\nThis is a page."
    checksum = factory.LazyFunction(lambda: SyncedPage.compute_checksum("raw content"))
    last_synced_at = factory.LazyFunction(timezone.now)


class ExtractionJobFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ExtractionJob

    credential = factory.SubFactory(ConnectorCredentialFactory)
    status = SyncJobStatus.COMPLETED
    pages_scored = 5
    pages_extracted = 3
    candidates_created = 2
    started_at = factory.LazyFunction(timezone.now)
    finished_at = factory.LazyFunction(timezone.now)


class CaptureCandidateFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CaptureCandidate

    credential = factory.SubFactory(ConnectorCredentialFactory)
    title = factory.Sequence(lambda n: f"Deploy Service {n}")
    slug = factory.Sequence(lambda n: f"deploy-service-{n}")
    description = "A process for deploying the service."
    content_md = "## Steps\n\n1. Build\n2. Test\n3. Deploy"
    frontmatter_yaml = "name: Deploy Service\ntags:\n  - deployment"
    probability_score = 0.85
    automation_tier = AutomationTier.READY
    automation_reasoning = "All steps use standard CLI tools."
    integration_needs = []
    grounding_sources = []
    status = CandidateStatus.PENDING
