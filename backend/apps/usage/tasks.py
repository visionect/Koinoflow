from apps.usage.enums import ClientType
from tasks.registry import register_task


@register_task("log_usage_event")
def log_usage_event(
    skill_id: str,
    version_number: int,
    client_id: str = "unknown",
    client_type: str = ClientType.UNKNOWN,
    agent_id: str | None = None,
):
    from apps.usage.models import UsageEvent

    UsageEvent.objects.create(
        skill_id=skill_id,
        agent_id=agent_id,
        version_number=version_number,
        client_id=client_id,
        client_type=client_type,
    )
