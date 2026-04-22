from django.conf import settings

from tasks.registry import register_task


def _invitation_html(
    inviter_name: str,
    workspace_name: str,
    role_display: str,
    accept_url: str,
) -> str:
    body_font = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
    header_span_style = "color:#ffffff;font-size:20px;font-weight:700;letter-spacing:-0.3px;"
    inner_table_style = (
        "background:#ffffff;border-radius:8px;border:1px solid #e5e7eb;overflow:hidden;"
    )
    heading_style = "margin:0 0 8px;font-size:24px;font-weight:700;color:#111827;line-height:1.3;"
    outer_table_style = "background-color:#f9fafb;padding:40px 0;"
    link_style = (
        "display:inline-block;padding:12px 28px;"
        "font-size:15px;font-weight:600;"
        "color:#ffffff;text-decoration:none;"
        "border-radius:6px;line-height:1;"
    )
    expire_msg = (
        "This invitation expires in 7 days. "
        "If you didn&#39;t expect this email, "
        "you can safely ignore it."
    )
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="UTF-8" />\n'
        '  <meta name="viewport"'
        ' content="width=device-width, initial-scale=1.0" />\n'
        f"  <title>You've been invited to"
        f" {workspace_name}</title>\n"
        "</head>\n"
        f'<body style="margin:0;padding:0;'
        f"background-color:#f9fafb;"
        f'font-family:{body_font};">\n'
        f'  <table width="100%" cellpadding="0"'
        f' cellspacing="0" role="presentation"'
        f' style="{outer_table_style}">\n'
        "    <tr>\n"
        '      <td align="center">\n'
        '        <table width="560" cellpadding="0"'
        ' cellspacing="0" role="presentation"'
        f' style="{inner_table_style}">\n'
        "          <tr>\n"
        '            <td style="background:#111827;'
        'padding:28px 40px;">\n'
        f'              <span style="{header_span_style}">'
        "Koinoflow</span>\n"
        "            </td>\n"
        "          </tr>\n"
        "          <tr>\n"
        '            <td style="padding:40px 40px 32px;">\n'
        f'              <p style="{heading_style}">\n'
        "                You've been invited\n"
        "              </p>\n"
        '              <p style="margin:0 0 24px;'
        'font-size:15px;color:#6b7280;line-height:1.6;">\n'
        f'                <strong style="color:#374151;">'
        f"{inviter_name}</strong>"
        " has invited you to join\n"
        f'                <strong style="color:#374151;">'
        f"{workspace_name}</strong>"
        " on Koinoflow\n"
        f'                as a <strong style="color:#374151;">'
        f"{role_display}</strong>.\n"
        "              </p>\n"
        '              <table cellpadding="0"'
        ' cellspacing="0" role="presentation">\n'
        "                <tr>\n"
        '                  <td style="border-radius:6px;'
        'background:#111827;">\n'
        f'                    <a href="{accept_url}"'
        f' style="{link_style}">\n'
        "                      Accept invitation\n"
        "                    </a>\n"
        "                  </td>\n"
        "                </tr>\n"
        "              </table>\n"
        '              <p style="margin:24px 0 0;'
        'font-size:13px;color:#9ca3af;line-height:1.6;">\n'
        "                Or copy and paste this URL"
        " into your browser:<br/>\n"
        f'                <a href="{accept_url}"'
        ' style="color:#6366f1;word-break:break-all;">'
        f"{accept_url}</a>\n"
        "              </p>\n"
        "            </td>\n"
        "          </tr>\n"
        "          <tr>\n"
        '            <td style="padding:20px 40px 28px;'
        'border-top:1px solid #f3f4f6;">\n'
        '              <p style="margin:0;font-size:12px;'
        'color:#9ca3af;line-height:1.6;">\n'
        f"                {expire_msg}\n"
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


def _invitation_text(
    inviter_name: str,
    workspace_name: str,
    role_display: str,
    accept_url: str,
) -> str:
    return (
        f'{inviter_name} has invited you to join "{workspace_name}" on Koinoflow '
        f"as a {role_display}.\n\n"
        f"Accept the invitation:\n{accept_url}\n\n"
        f"This invitation expires in 7 days."
    )


@register_task("send_invitation_email")
def send_invitation_email(invitation_id: str):
    from apps.common.email_service import get_email_backend
    from apps.orgs.enums import InvitationStatus
    from apps.orgs.models import PendingInvitation

    try:
        invitation = PendingInvitation.objects.select_related("workspace", "invited_by").get(
            id=invitation_id, status=InvitationStatus.PENDING
        )
    except PendingInvitation.DoesNotExist:
        return

    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173")
    accept_url = f"{frontend_url}/invitations/{invitation.token}/accept"

    inviter_name = ""
    if invitation.invited_by:
        inviter_name = invitation.invited_by.get_full_name() or invitation.invited_by.email

    workspace_name = invitation.workspace.name
    role_display = invitation.get_role_display()

    backend = get_email_backend()
    backend.send(
        to=invitation.email,
        subject=f"You've been invited to {workspace_name} on Koinoflow",
        html=_invitation_html(inviter_name, workspace_name, role_display, accept_url),
        text=_invitation_text(inviter_name, workspace_name, role_display, accept_url),
        from_email=settings.INVITATION_FROM_EMAIL,
    )
