from django.contrib import admin

from apps.agents.models import Agent, AgentSkillDeployment


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ("name", "workspace", "token_prefix", "is_active", "last_used_at", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "workspace__name", "token_prefix")
    readonly_fields = ("token_hash", "token_prefix", "last_used_at")


@admin.register(AgentSkillDeployment)
class AgentSkillDeploymentAdmin(admin.ModelAdmin):
    list_display = ("skill", "agent", "deploy_to_all", "created_at")
    list_filter = ("deploy_to_all",)
    search_fields = ("skill__title", "skill__slug", "agent__name")
