from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from tasks.registry import register_task

_BODY_FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


def _staleness_email_html(
    process_title: str,
    department_name: str,
    workspace_name: str,
    days_stale: int | None,
    process_url: str,
) -> str:
    if days_stale is None:
        stale_line = "This process has <strong>never been called</strong> by any agent or integration and may no longer be needed."  # noqa: E501
    else:
        stale_line = (
            f"This process hasn&#39;t been used in "
            f"<strong>{days_stale} day{'s' if days_stale != 1 else ''}</strong>. "  # noqa: E501
            "It may no longer be needed and could be removed to keep your knowledge base clean."
        )

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="UTF-8" />\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n'
        f"  <title>Stale process: {process_title}</title>\n"
        "</head>\n"
        f'<body style="margin:0;padding:0;background-color:#f9fafb;font-family:{_BODY_FONT};">\n'
        '  <table width="100%" cellpadding="0" cellspacing="0" role="presentation"'
        '   style="background-color:#f9fafb;padding:40px 0;">\n'
        "    <tr>\n"
        '      <td align="center">\n'
        '        <table width="560" cellpadding="0" cellspacing="0" role="presentation"'
        '         style="background:#ffffff;border-radius:8px;border:1px solid #e5e7eb;overflow:hidden;">\n'  # noqa: E501
        # Header
        "          <tr>\n"
        '            <td style="background:#111827;padding:28px 40px;">\n'
        '              <span style="color:#ffffff;font-size:20px;font-weight:700;letter-spacing:-0.3px;">'  # noqa: E501
        "Koinoflow</span>\n"
        "            </td>\n"
        "          </tr>\n"
        # Alert badge
        "          <tr>\n"
        '            <td style="padding:32px 40px 0;">\n'
        '              <span style="display:inline-block;background:#fef3c7;color:#92400e;'
        "font-size:12px;font-weight:600;letter-spacing:0.5px;text-transform:uppercase;"
        'padding:4px 10px;border-radius:4px;">Staleness alert</span>\n'
        "            </td>\n"
        "          </tr>\n"
        # Title
        "          <tr>\n"
        '            <td style="padding:16px 40px 0;">\n'
        f'              <h1 style="margin:0;font-size:22px;font-weight:700;color:#111827;line-height:1.3;">'  # noqa: E501
        f"Process needs attention</h1>\n"
        "            </td>\n"
        "          </tr>\n"
        # Process card
        "          <tr>\n"
        '            <td style="padding:20px 40px 0;">\n'
        '              <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:6px;'
        'padding:16px 20px;">\n'
        f'                <p style="margin:0 0 4px;font-size:16px;font-weight:600;color:#111827;">'
        f"{process_title}</p>\n"
        f'                <p style="margin:0;font-size:13px;color:#6b7280;">'
        f"{department_name} &middot; {workspace_name}</p>\n"
        "              </div>\n"
        "            </td>\n"
        "          </tr>\n"
        # Body text
        "          <tr>\n"
        '            <td style="padding:20px 40px 0;">\n'
        f'              <p style="margin:0;font-size:15px;color:#374151;line-height:1.6;">'
        f"{stale_line}</p>\n"
        "            </td>\n"
        "          </tr>\n"
        # Actions heading
        "          <tr>\n"
        '            <td style="padding:24px 40px 0;">\n'
        '              <p style="margin:0 0 12px;font-size:13px;font-weight:600;color:#6b7280;'
        'text-transform:uppercase;letter-spacing:0.5px;">What would you like to do?</p>\n'
        '              <table cellpadding="0" cellspacing="0" role="presentation" width="100%">\n'
        "                <tr>\n"
        # Keep / Review button
        '                  <td style="padding-right:8px;" width="50%">\n'
        '                    <div style="border:1px solid #e5e7eb;border-radius:6px;padding:16px;">\n'  # noqa: E501
        '                      <p style="margin:0 0 6px;font-size:13px;font-weight:600;color:#111827;">'  # noqa: E501
        "Keep this process</p>\n"
        '                      <p style="margin:0 0 12px;font-size:12px;color:#6b7280;line-height:1.5;">'  # noqa: E501
        "Review and confirm it&#39;s still accurate.</p>\n"
        f'                      <a href="{process_url}" style="display:inline-block;'
        "background:#111827;color:#ffffff;font-size:13px;font-weight:600;"
        'text-decoration:none;padding:8px 16px;border-radius:5px;">Review process</a>\n'
        "                    </div>\n"
        "                  </td>\n"
        # Archive button
        '                  <td style="padding-left:8px;" width="50%">\n'
        '                    <div style="border:1px solid #e5e7eb;border-radius:6px;padding:16px;">\n'  # noqa: E501
        '                      <p style="margin:0 0 6px;font-size:13px;font-weight:600;color:#111827;">'  # noqa: E501
        "Remove this process</p>\n"
        '                      <p style="margin:0 0 12px;font-size:12px;color:#6b7280;line-height:1.5;">'  # noqa: E501
        "Delete it if it&#39;s no longer relevant.</p>\n"
        f'                      <a href="{process_url}" style="display:inline-block;'
        "background:#ffffff;color:#374151;font-size:13px;font-weight:600;"
        'text-decoration:none;padding:8px 16px;border-radius:5px;border:1px solid #d1d5db;">'
        "Open process</a>\n"
        "                    </div>\n"
        "                  </td>\n"
        "                </tr>\n"
        "              </table>\n"
        "            </td>\n"
        "          </tr>\n"
        # Footer
        "          <tr>\n"
        '            <td style="padding:28px 40px;border-top:1px solid #f3f4f6;margin-top:28px;">\n'
        '              <p style="margin:0;font-size:12px;color:#9ca3af;line-height:1.6;">\n'
        f"                You received this alert because staleness notifications are enabled for "
        f'<strong style="color:#6b7280;">{workspace_name}</strong>. '
        "Adjust alert settings in your workspace settings.\n"
        "              </p>\n"
        "            </td>\n"
        "          </tr>\n"
        "        </table>\n"
        "      </td>\n"
        "    </tr>\n"
        "  </table>\n"
        "</body>\n"
        "</html>"
    )


def _staleness_email_text(
    process_title: str,
    department_name: str,
    workspace_name: str,
    days_stale: int | None,
    process_url: str,
) -> str:
    if days_stale is None:
        stale_line = (
            f'The process "{process_title}" in {department_name} '
            "has never been called by any agent or integration."
        )
    else:
        stale_line = (
            f'The process "{process_title}" in {department_name} '
            f"hasn't been used in {days_stale} days."
        )
    return (
        f"{stale_line}\n\n"
        f"Review the process and decide whether to keep or remove it:\n{process_url}\n\n"
        f"You received this alert because staleness notifications are enabled for {workspace_name}."
    )


@register_task("staleness_check")
def staleness_check():
    from django.db.models import OuterRef, Q, Subquery

    from apps.orgs.models import FK_SETTINGS_FIELDS, CoreSettings
    from apps.processes.enums import StatusChoices
    from apps.processes.models import Process
    from apps.usage.models import UsageEvent

    last_used_sq = (
        UsageEvent.objects.filter(process=OuterRef("pk"))
        .order_by("-called_at")
        .values("called_at")[:1]
    )
    published = (
        Process.objects.filter(status=StatusChoices.PUBLISHED)
        .select_related("department__team")
        .annotate(last_used_at=Subquery(last_used_sq))
    )
    process_list = list(published)
    if not process_list:
        return

    scope_keys = set()
    for p in process_list:
        ws_id = p.department.team.workspace_id
        team_id = p.department.team_id
        dept_id = p.department_id
        scope_keys.add((ws_id, None, None))
        scope_keys.add((ws_id, team_id, None))
        scope_keys.add((ws_id, team_id, dept_id))

    settings_filter = Q()
    for ws_id, team_id, dept_id in scope_keys:
        if dept_id:
            settings_filter |= Q(workspace_id=ws_id, team_id=team_id, department_id=dept_id)
        elif team_id:
            settings_filter |= Q(workspace_id=ws_id, team_id=team_id, department__isnull=True)
        else:
            settings_filter |= Q(workspace_id=ws_id, team__isnull=True, department__isnull=True)

    all_settings = list(
        CoreSettings.objects.filter(settings_filter).select_related(*FK_SETTINGS_FIELDS)
    )

    settings_index = {}
    for s in all_settings:
        key = (s.workspace_id, s.team_id, s.department_id)
        settings_index[key] = s

    def _resolve_staleness_rule(ws_id, team_id, dept_id):
        for key in [
            (ws_id, team_id, dept_id),
            (ws_id, team_id, None),
            (ws_id, None, None),
        ]:
            row = settings_index.get(key)
            if row and row.staleness_alert_id is not None:
                return row.staleness_alert
        return None

    from tasks import task_backend

    now = timezone.now()
    for process in process_list:
        rule = _resolve_staleness_rule(
            process.department.team.workspace_id,
            process.department.team_id,
            process.department_id,
        )
        if rule is None:
            continue

        cutoff = now - timedelta(days=rule.period_days)
        is_stale = process.last_used_at is None or process.last_used_at < cutoff
        if is_stale:
            task_backend.enqueue("send_staleness_alert", process_id=str(process.id))


@register_task("send_staleness_alert")
def send_staleness_alert(process_id: str):
    from apps.orgs.enums import RoleChoices
    from apps.orgs.models import FK_SETTINGS_FIELDS, CoreSettings, Membership
    from apps.processes.models import Process

    try:
        process = Process.objects.select_related("owner", "department__team__workspace").get(
            id=process_id
        )
    except Process.DoesNotExist:
        return

    dept = process.department
    team = dept.team
    workspace = team.workspace

    # Resolve effective staleness alert rule for this process's scope
    from django.db.models import Q

    scope_filter = (
        Q(workspace=workspace, team__isnull=True, department__isnull=True)
        | Q(workspace=workspace, team=team, department__isnull=True)
        | Q(workspace=workspace, team=team, department=dept)
    )
    all_settings = list(
        CoreSettings.objects.filter(scope_filter).select_related(*FK_SETTINGS_FIELDS)
    )
    settings_index = {(s.workspace_id, s.team_id, s.department_id): s for s in all_settings}

    rule = None
    for key in [
        (workspace.id, team.id, dept.id),
        (workspace.id, team.id, None),
        (workspace.id, None, None),
    ]:
        row = settings_index.get(key)
        if row and row.staleness_alert_id is not None:
            rule = row.staleness_alert
            break

    if rule is None:
        return

    # Collect recipient emails
    recipient_emails: set[str] = set()

    if rule.notify_admins:
        for m in Membership.objects.filter(
            workspace=workspace, role=RoleChoices.ADMIN
        ).select_related("user"):
            if m.user.email:
                recipient_emails.add(m.user.email)

    if rule.notify_team_managers:
        for m in Membership.objects.filter(
            workspace=workspace, team=team, role=RoleChoices.TEAM_MANAGER
        ).select_related("user"):
            if m.user.email:
                recipient_emails.add(m.user.email)

    if rule.notify_process_owner and process.owner and process.owner.email:
        recipient_emails.add(process.owner.email)

    if not recipient_emails:
        return

    from apps.usage.models import UsageEvent

    last_usage = UsageEvent.objects.filter(process=process).order_by("-called_at").first()
    days_stale = None if last_usage is None else (timezone.now() - last_usage.called_at).days

    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173")
    from apps.orgs.models import CoreSlug, EntityType

    try:
        ws_slug = CoreSlug.objects.get(
            entity_type=EntityType.WORKSPACE, entity_id=workspace.id
        ).slug
    except CoreSlug.DoesNotExist:
        ws_slug = str(workspace.id)

    process_url = f"{frontend_url}/{ws_slug}/processes/{process.id}"

    from apps.common.email_service import get_email_backend

    backend = get_email_backend()
    for email in recipient_emails:
        backend.send(
            to=email,
            subject=f"[Koinoflow] Stale process: {process.title}",
            html=_staleness_email_html(
                process_title=process.title,
                department_name=dept.name,
                workspace_name=workspace.name,
                days_stale=days_stale,
                process_url=process_url,
            ),
            text=_staleness_email_text(
                process_title=process.title,
                department_name=dept.name,
                workspace_name=workspace.name,
                days_stale=days_stale,
                process_url=process_url,
            ),
            from_email=settings.ALERTS_FROM_EMAIL,
        )
