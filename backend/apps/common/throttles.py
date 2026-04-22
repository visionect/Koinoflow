from ninja.throttling import AnonRateThrottle, AuthRateThrottle


class GlobalAnonThrottle(AnonRateThrottle):
    scope = "global_anon"


class GlobalAuthThrottle(AuthRateThrottle):
    scope = "global_auth"


# Tier 1: Auth & credential endpoints — strictest limits
class AuthAnonThrottle(AnonRateThrottle):
    scope = "auth_anon"


class AuthUserThrottle(AuthRateThrottle):
    scope = "auth_user"


# Tier 2: Creation endpoints (workspace, invite, API keys, processes)
class CreateAnonThrottle(AnonRateThrottle):
    scope = "create_anon"


class CreateAuthThrottle(AuthRateThrottle):
    scope = "create_auth"


# Tier 2b: Invite-specific (sends emails, expensive)
class InviteThrottle(AuthRateThrottle):
    scope = "invite"


# Tier 2c: API key creation (high-privilege, sensitive)
class ApiKeyCreateThrottle(AuthRateThrottle):
    scope = "api_key_create"


# Tier 3: Mutation endpoints (PATCH/DELETE on resources)
class MutationThrottle(AuthRateThrottle):
    scope = "mutation"


# Tier 4: Read-heavy endpoints (lists, summaries)
class ReadThrottle(AuthRateThrottle):
    scope = "read"


# Usage event logging — per API key
class UsageLogThrottle(AuthRateThrottle):
    scope = "usage_log"


# File upload/import — expensive
class ImportThrottle(AuthRateThrottle):
    scope = "import"


# Webhook receivers — anonymous with generous cap, protects against floods
class WebhookThrottle(AnonRateThrottle):
    scope = "webhook"


# AI / connector extraction — expensive (money + external quota)
class AiExtractionThrottle(AuthRateThrottle):
    scope = "ai_extraction"
