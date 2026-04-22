import logging
import os

API_BASE_URL = os.environ.get("KOINOFLOW_API_URL")
if not API_BASE_URL:
    raise ValueError("KOINOFLOW_API_URL is required")

SERVER_HOST = os.environ.get("MCP_SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(
    os.environ.get(
        "PORT",
        os.environ.get("MCP_SERVER_PORT", "8001"),
    )
)

ALLOWED_HOSTS_ENV = os.environ.get("MCP_ALLOWED_HOSTS", "")
ALLOWED_HOSTS = [h.strip() for h in ALLOWED_HOSTS_ENV.split(",") if h.strip()]

ALLOWED_ORIGINS_ENV = os.environ.get("MCP_ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS = [o.strip() for o in ALLOWED_ORIGINS_ENV.split(",") if o.strip()]

# OAuth 2.1 configuration
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://localhost:8001")
OAUTH_INTROSPECT_URL = os.environ.get(
    "MCP_INTROSPECT_URL",
    API_BASE_URL.rsplit("/api/", 1)[0] + "/oauth/introspect/",
)
OAUTH_INTROSPECT_CLIENT_ID = os.environ.get("MCP_INTROSPECT_CLIENT_ID", "")
OAUTH_INTROSPECT_CLIENT_SECRET = os.environ.get("MCP_INTROSPECT_CLIENT_SECRET", "")

# The Django authorization server's base URL (for AS metadata discovery)
AUTHORIZATION_SERVER_URL = os.environ.get(
    "AUTHORIZATION_SERVER_URL",
    API_BASE_URL.rsplit("/api/", 1)[0],
)

APPROVAL_TOKEN_SECRET = os.environ.get("MCP_APPROVAL_TOKEN_SECRET", "")
if not APPROVAL_TOKEN_SECRET:
    raise ValueError("MCP_APPROVAL_TOKEN_SECRET is required")
APPROVAL_TOKEN_TTL_SECONDS = int(os.environ.get("MCP_APPROVAL_TOKEN_TTL_SECONDS", "900"))

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("koinoflow-mcp")
