from ninja import NinjaAPI

from apps.accounts.api import router as auth_router
from apps.accounts.mcp_api import router as mcp_router
from apps.agents.api import router as agents_router
from apps.common.throttles import GlobalAnonThrottle, GlobalAuthThrottle
from apps.connectors.api import router as connectors_router
from apps.orgs.api import router as orgs_router
from apps.orgs.api_keys import router as api_keys_router
from apps.skills.api import router as skills_router
from apps.usage.api import router as usage_router

api = NinjaAPI(
    title="Koinoflow API",
    version="1.0.0",
    description="Skill management for AI agents",
    throttle=[
        GlobalAnonThrottle(),
        GlobalAuthThrottle(),
    ],
)


@api.get("/health", auth=None, tags=["health"])
def health(request):
    return {"status": "ok"}


api.add_router("/v1/auth/", auth_router)
api.add_router("/v1/", orgs_router)
api.add_router("/v1/", api_keys_router)
api.add_router("/v1/", agents_router)
api.add_router("/v1/", skills_router)
api.add_router("/v1/", usage_router)
api.add_router("/v1/", mcp_router)
api.add_router("/v1/connectors/", connectors_router)
