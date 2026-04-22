from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.orgs.enums import RoleChoices
from apps.orgs.tests.factories import (
    CoreSettingsFactory,
    DepartmentFactory,
    MembershipFactory,
    StalenessAlertRuleFactory,
    TeamFactory,
    WorkspaceFactory,
)
from apps.processes.tasks import send_staleness_alert, staleness_check
from apps.processes.tests.factories import ProcessFactory


def _create_usage_event(process, days_ago):
    from apps.usage.models import UsageEvent

    event = UsageEvent.objects.create(
        process=process,
        version_number=1,
        client_id="test-client",
        client_type="claude",
        tool_name="read_process",
    )
    event.called_at = timezone.now() - timedelta(days=days_ago)
    event.save(update_fields=["called_at"])
    return event


@pytest.mark.django_db
class TestStalenessCheck:
    def _make_stale_process(self, **kwargs):
        ws = WorkspaceFactory()
        team = TeamFactory(workspace=ws)
        dept = DepartmentFactory(team=team)
        owner = UserFactory()
        rule = StalenessAlertRuleFactory(workspace=ws, period_days=30)
        CoreSettingsFactory(workspace=ws, staleness_alert=rule, process_audit=None)
        defaults = {"department": dept, "status": "published", "owner": owner}
        defaults.update(kwargs)
        process = ProcessFactory(**defaults)
        # No UsageEvent created → never used → stale
        return process

    @patch("tasks.task_backend")
    def test_staleness_check_finds_never_used_process(self, mock_backend):
        process = self._make_stale_process()

        staleness_check()

        mock_backend.enqueue.assert_called_once_with(
            "send_staleness_alert", process_id=str(process.id)
        )

    @patch("tasks.task_backend")
    def test_staleness_check_finds_process_unused_beyond_period(self, mock_backend):
        process = self._make_stale_process()
        _create_usage_event(process, days_ago=35)  # used 35 days ago, period is 30

        staleness_check()

        mock_backend.enqueue.assert_called_once_with(
            "send_staleness_alert", process_id=str(process.id)
        )

    @patch("tasks.task_backend")
    def test_staleness_check_ignores_recently_used_process(self, mock_backend):
        process = self._make_stale_process()
        _create_usage_event(process, days_ago=5)  # used 5 days ago, period is 30

        staleness_check()

        mock_backend.enqueue.assert_not_called()

    @patch("tasks.task_backend")
    def test_staleness_check_ignores_draft_processes(self, mock_backend):
        self._make_stale_process(status="draft")

        staleness_check()

        mock_backend.enqueue.assert_not_called()

    @patch("tasks.task_backend")
    def test_staleness_check_requires_staleness_rule(self, mock_backend):
        ws = WorkspaceFactory()
        team = TeamFactory(workspace=ws)
        dept = DepartmentFactory(team=team)
        owner = UserFactory()
        CoreSettingsFactory(workspace=ws, staleness_alert=None, process_audit=None)
        ProcessFactory(department=dept, status="published", owner=owner)
        # No rule configured → no alert even if never used

        staleness_check()

        mock_backend.enqueue.assert_not_called()


@pytest.mark.django_db
class TestSendStalenessAlert:
    def _make_process_with_rule(self, notify_admins=True, notify_process_owner=True):
        ws = WorkspaceFactory()
        team = TeamFactory(workspace=ws)
        dept = DepartmentFactory(team=team)
        owner = UserFactory()
        admin_user = UserFactory()
        MembershipFactory(workspace=ws, user=admin_user, role=RoleChoices.ADMIN)
        rule = StalenessAlertRuleFactory(
            workspace=ws,
            period_days=30,
            notify_admins=notify_admins,
            notify_team_managers=False,
            notify_process_owner=notify_process_owner,
        )
        CoreSettingsFactory(workspace=ws, staleness_alert=rule, process_audit=None)
        process = ProcessFactory(department=dept, status="published", owner=owner)
        return process, admin_user, owner

    @patch("apps.common.email_service.get_email_backend")
    def test_send_staleness_alert_emails_admin(self, mock_get_backend):
        mock_backend = MagicMock()
        mock_get_backend.return_value = mock_backend
        process, admin_user, owner = self._make_process_with_rule(
            notify_admins=True, notify_process_owner=False
        )

        send_staleness_alert(str(process.id))

        assert mock_backend.send.called
        recipients = {call.kwargs["to"] for call in mock_backend.send.call_args_list}
        assert admin_user.email in recipients

    @patch("apps.common.email_service.get_email_backend")
    def test_send_staleness_alert_emails_owner(self, mock_get_backend):
        mock_backend = MagicMock()
        mock_get_backend.return_value = mock_backend
        process, admin_user, owner = self._make_process_with_rule(
            notify_admins=False, notify_process_owner=True
        )

        send_staleness_alert(str(process.id))

        assert mock_backend.send.called
        recipients = {call.kwargs["to"] for call in mock_backend.send.call_args_list}
        assert owner.email in recipients

    @patch("apps.common.email_service.get_email_backend")
    def test_send_staleness_alert_no_recipients_skips(self, mock_get_backend):
        mock_backend = MagicMock()
        mock_get_backend.return_value = mock_backend
        ws = WorkspaceFactory()
        team = TeamFactory(workspace=ws)
        dept = DepartmentFactory(team=team)
        rule = StalenessAlertRuleFactory(
            workspace=ws,
            notify_admins=False,
            notify_team_managers=False,
            notify_process_owner=False,
        )
        CoreSettingsFactory(workspace=ws, staleness_alert=rule, process_audit=None)
        process = ProcessFactory(department=dept, status="published", owner=None)

        send_staleness_alert(str(process.id))

        mock_backend.send.assert_not_called()

    @patch("apps.common.email_service.get_email_backend")
    def test_send_staleness_alert_subject_contains_process_title(self, mock_get_backend):
        mock_backend = MagicMock()
        mock_get_backend.return_value = mock_backend
        process, _, _ = self._make_process_with_rule()

        send_staleness_alert(str(process.id))

        subject = mock_backend.send.call_args.kwargs["subject"]
        assert process.title in subject

    @patch("apps.common.email_service.get_email_backend")
    def test_send_staleness_alert_days_stale_from_usage_event(self, mock_get_backend):
        mock_backend = MagicMock()
        mock_get_backend.return_value = mock_backend
        process, _, _ = self._make_process_with_rule(notify_admins=True, notify_process_owner=False)
        _create_usage_event(process, days_ago=45)

        send_staleness_alert(str(process.id))

        html = mock_backend.send.call_args.kwargs["html"]
        assert "45 day" in html

    @patch("apps.common.email_service.get_email_backend")
    def test_send_staleness_alert_never_used_message(self, mock_get_backend):
        mock_backend = MagicMock()
        mock_get_backend.return_value = mock_backend
        process, _, _ = self._make_process_with_rule(notify_admins=True, notify_process_owner=False)
        # No usage events → "never been called"

        send_staleness_alert(str(process.id))

        html = mock_backend.send.call_args.kwargs["html"]
        assert "never been called" in html

    @patch("apps.common.email_service.get_email_backend")
    def test_send_staleness_alert_nonexistent_process(self, mock_get_backend):
        mock_backend = MagicMock()
        mock_get_backend.return_value = mock_backend

        send_staleness_alert("00000000-0000-0000-0000-000000000000")

        mock_backend.send.assert_not_called()
