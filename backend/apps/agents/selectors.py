from apps.orgs.models import SYSTEM_KIND_AGENTS
from apps.skills.enums import StatusChoices
from apps.skills.models import Skill


def skills_for_agent(agent):
    base = Skill.objects.filter(
        department__team__workspace=agent.workspace,
        department__system_kind=SYSTEM_KIND_AGENTS,
        status=StatusChoices.PUBLISHED,
    )
    return (
        base.filter(agent_deployments__deploy_to_all=True)
        | base.filter(agent_deployments__agent=agent)
    ).distinct()
