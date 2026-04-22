import pytest

from apps.orgs.tests.factories import DepartmentFactory, TeamFactory, WorkspaceFactory
from apps.processes.tests.factories import ProcessFactory
from apps.usage.models import UsageEvent
from apps.usage.tasks import log_usage_event


@pytest.mark.django_db
class TestLogUsageEvent:
    def _make_process(self):
        ws = WorkspaceFactory()
        team = TeamFactory(workspace=ws)
        dept = DepartmentFactory(team=team)
        return ProcessFactory(department=dept)

    def test_log_usage_event_creates_record(self):
        process = self._make_process()

        log_usage_event(
            process_id=str(process.id),
            version_number=1,
            client_id="cursor-abc",
            client_type="Cursor",
        )

        assert UsageEvent.objects.count() == 1
        event = UsageEvent.objects.first()
        assert event.process_id == process.id
        assert event.version_number == 1
        assert event.client_id == "cursor-abc"
        assert event.client_type == "Cursor"

    def test_log_usage_event_with_defaults(self):
        process = self._make_process()

        log_usage_event(
            process_id=str(process.id),
            version_number=2,
        )

        assert UsageEvent.objects.count() == 1
        event = UsageEvent.objects.first()
        assert event.client_id == "unknown"
        assert event.client_type == "Unknown"
