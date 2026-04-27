import json
import os
import time
from types import SimpleNamespace

import respx
from httpx import Response

os.environ["KOINOFLOW_API_URL"] = "http://testserver/api/v1"
os.environ.setdefault("KOINOFLOW_API_KEY", "test-key")
os.environ.setdefault("MCP_APPROVAL_TOKEN_SECRET", "test-approval-secret")

from auth import get_authorization_server_metadata  # noqa: E402
from server import (  # noqa: E402
    _mcp_client_type,
    _token_info_var,
    apply_skill_update,
    discover_skills,
    list_skills,
    propose_skill_update,
    read_skill,
)

PROCESS_DETAIL = {
    "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    "title": "Deploy to Production",
    "slug": "deploy-to-production",
    "description": "Step-by-step deployment guide",
    "status": "published",
    "department_slug": "engineering",
    "department_name": "Engineering",
    "team_slug": "platform",
    "team_name": "Platform",
    "owner": None,
    "current_version": {
        "id": "11111111-2222-3333-4444-555555555555",
        "version_number": 3,
        "content_md": "## Step 1\n\nRun the deploy script.",
        "frontmatter_yaml": "",
        "change_summary": "Updated step 1",
        "files": [],
        "authored_by": None,
        "created_at": "2026-04-01T10:00:00Z",
    },
    "last_reviewed_at": "2026-04-01T12:00:00Z",
    "created_at": "2026-03-01T10:00:00Z",
    "updated_at": "2026-04-01T10:00:00Z",
}

PROCESS_DETAIL_WITH_FRONTMATTER = {
    **PROCESS_DETAIL,
    "current_version": {
        **PROCESS_DETAIL["current_version"],
        "frontmatter_yaml": "owner: platform-team\ncriticality: high",
    },
}

PROCESS_DETAIL_WITH_FILES = {
    **PROCESS_DETAIL,
    "current_version": {
        **PROCESS_DETAIL["current_version"],
        "files": [
            {
                "id": "file-1",
                "path": "scripts/deploy.sh",
                "file_type": "shell",
                "size_bytes": 2560,
            },
            {
                "id": "file-2",
                "path": "references/checklist.md",
                "file_type": "markdown",
                "size_bytes": 1126,
            },
        ],
    },
}

PROCESS_LIST = {
    "items": [
        {
            "title": "Deploy to Production",
            "slug": "deploy-to-production",
            "description": "Step-by-step deployment guide",
            "current_version_number": 3,
            "department_name": "Engineering",
            "team_name": "Platform",
        },
        {
            "title": "Onboarding Checklist",
            "slug": "onboarding-checklist",
            "description": "",
            "current_version_number": 1,
            "department_name": "HR",
            "team_name": "People",
        },
    ],
    "count": 2,
}

PROCESS_DETAIL_WITH_METADATA = {
    **PROCESS_DETAIL,
    "current_version": {
        **PROCESS_DETAIL["current_version"],
        "koinoflow_metadata": {
            "retrieval_keywords": ["deploy", "ship"],
            "risk_level": "high",
            "requires_human_approval": True,
            "prerequisites": ["setup-access"],
            "audience": ["engineers"],
        },
    },
}

PROCESS_LIST_WITH_METADATA = {
    "items": [
        {
            "title": "Deploy to Production",
            "slug": "deploy-to-production",
            "description": "Ship code",
            "current_version_number": 3,
            "department_name": "Engineering",
            "team_name": "Platform",
            "risk_level": "high",
            "requires_human_approval": True,
            "retrieval_keywords": ["deploy", "release"],
        },
    ],
    "count": 1,
}


def test_authorization_server_metadata_matches_mcp_requested_scopes():
    data = get_authorization_server_metadata()

    assert data["issuer"] == "http://testserver"
    assert data["authorization_endpoint"] == "http://testserver/oauth/authorize/"
    assert data["registration_endpoint"] == "http://testserver/oauth/register"
    assert data["scopes_supported"] == ["skills:read", "skills:write", "usage:write"]

PROCESS_DISCOVERY = {
    "items": [
        {
            "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "title": "Deploy to Production",
            "slug": "deploy-to-production",
            "description": "Ship code",
            "current_version_number": 3,
            "department_name": "Engineering",
            "team_name": "Platform",
            "risk_level": "high",
            "requires_human_approval": True,
            "retrieval_keywords": ["deploy", "release"],
            "score": 0.9234,
            "vector_score": 0.95,
            "lexical_score": 0.86,
            "match_reasons": ["semantic similarity 0.95", "retrieval keywords matched query terms"],
            "snippet": "Release services safely.",
            "indexed": True,
        }
    ],
    "count": 1,
    "embedding_status": "ready",
}


def _set_token_scope(scope: str = "skills:read skills:write usage:write") -> None:
    _token_info_var.set(
        {
            "_raw_token": "oauth-token",
            "scope": scope,
            "sub": "user-123",
            "workspace_id": "workspace-1",
        }
    )


def _make_ctx(client_name: str | None = None, version: str | None = None):
    if client_name is None:
        return SimpleNamespace()

    return SimpleNamespace(
        request_context=SimpleNamespace(
            session=SimpleNamespace(
                client_params=SimpleNamespace(
                    clientInfo=SimpleNamespace(name=client_name, version=version)
                )
            )
        )
    )


@respx.mock
async def test_read_skill_returns_markdown():
    _set_token_scope()
    respx.get("http://testserver/api/v1/skills/deploy-to-production").mock(
        return_value=Response(200, json=PROCESS_DETAIL)
    )
    respx.post("http://testserver/api/v1/usage").mock(return_value=Response(200, json={"ok": True}))

    result = await read_skill(slug="deploy-to-production", ctx=_make_ctx())

    assert "## Step 1" in result
    assert "Run the deploy script." in result
    assert not result.startswith("---\n")
    assert "## Support Files (0 files)" in result


def test_mcp_client_type_uses_known_client_title():
    assert _mcp_client_type(_make_ctx("cursor-vscode", "1.0.0")) == "Cursor"


def test_mcp_client_type_falls_back_for_unknown_client():
    assert _mcp_client_type(_make_ctx("totally-unknown-client", "1.0.0")) == "MCP"


@respx.mock
async def test_read_skill_with_frontmatter():
    _set_token_scope()
    respx.get("http://testserver/api/v1/skills/deploy-to-production").mock(
        return_value=Response(200, json=PROCESS_DETAIL_WITH_FRONTMATTER)
    )
    respx.post("http://testserver/api/v1/usage").mock(return_value=Response(200, json={"ok": True}))

    result = await read_skill(slug="deploy-to-production", ctx=_make_ctx())

    assert result.startswith("---\n")
    assert "owner: platform-team" in result
    assert "criticality: high" in result
    assert "## Step 1" in result
    assert "## Support Files (0 files)" in result


@respx.mock
async def test_read_skill_lists_support_files_by_default():
    _set_token_scope()
    respx.get("http://testserver/api/v1/skills/deploy-to-production").mock(
        return_value=Response(200, json=PROCESS_DETAIL_WITH_FILES)
    )
    respx.post("http://testserver/api/v1/usage").mock(return_value=Response(200, json={"ok": True}))

    result = await read_skill(slug="deploy-to-production", ctx=_make_ctx())

    assert "## Support Files (2 files)" in result
    assert "- scripts/deploy.sh (shell, 2.5 KB)" in result
    assert "- references/checklist.md (markdown, 1.1 KB)" in result


@respx.mock
async def test_read_skill_can_skip_support_file_manifest():
    _set_token_scope()
    respx.get("http://testserver/api/v1/skills/deploy-to-production").mock(
        return_value=Response(200, json=PROCESS_DETAIL_WITH_FILES)
    )
    respx.post("http://testserver/api/v1/usage").mock(return_value=Response(200, json={"ok": True}))

    result = await read_skill(
        slug="deploy-to-production",
        ctx=_make_ctx(),
        include_files=False,
    )

    assert "## Step 1" in result
    assert "## Support Files" not in result


@respx.mock
async def test_list_skills_formats_output():
    _set_token_scope()
    respx.get("http://testserver/api/v1/skills").mock(return_value=Response(200, json=PROCESS_LIST))

    result = await list_skills()

    assert "Showing 1–2 of 2 processes" in result
    assert "**Deploy to Production**" in result
    assert "`deploy-to-production`" in result
    assert "Step-by-step deployment guide" in result
    assert "[v3]" in result
    assert "**Onboarding Checklist**" in result
    assert "`onboarding-checklist`" in result


@respx.mock
async def test_discover_skills_formats_ranked_output():
    _set_token_scope()
    route = respx.get("http://testserver/api/v1/skills/discover").mock(
        return_value=Response(200, json=PROCESS_DISCOVERY)
    )

    result = await discover_skills(query="ship production", limit=5)

    assert route.called
    assert route.calls[0].request.url.params["query"] == "ship production"
    assert route.calls[0].request.url.params["limit"] == "5"
    assert "Top 1 process matches" in result
    assert "**Deploy to Production**" in result
    assert "`deploy-to-production`" in result
    assert "[score: 0.92]" in result
    assert "[risk: high]" in result
    assert "[needs approval]" in result
    assert "semantic similarity 0.95" in result
    assert "Call read_skill" in result


@respx.mock
async def test_list_skills_empty():
    _set_token_scope()
    respx.get("http://testserver/api/v1/skills").mock(
        return_value=Response(200, json={"items": [], "count": 0})
    )

    result = await list_skills()

    assert result == "No processes found."


@respx.mock
async def test_read_skill_logs_usage():
    _set_token_scope()
    respx.get("http://testserver/api/v1/skills/deploy-to-production").mock(
        return_value=Response(200, json=PROCESS_DETAIL)
    )
    usage_route = respx.post("http://testserver/api/v1/usage").mock(
        return_value=Response(200, json={"ok": True})
    )

    await read_skill(slug="deploy-to-production", ctx=_make_ctx())

    import asyncio

    await asyncio.sleep(0.1)

    assert usage_route.called
    call = usage_route.calls[0]
    import json

    body = json.loads(call.request.content)
    assert body["skill_id"] == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert body["version_number"] == 3
    assert body["client_id"] == "mcp-remote"
    assert body["client_type"] == "MCP"


@respx.mock
async def test_propose_skill_update_returns_suggestions_and_token():
    _set_token_scope()
    respx.get("http://testserver/api/v1/settings").mock(
        return_value=Response(200, json={"allow_agent_process_updates": True})
    )
    respx.get("http://testserver/api/v1/skills/deploy-to-production").mock(
        return_value=Response(200, json=PROCESS_DETAIL_WITH_FRONTMATTER)
    )

    result = await propose_skill_update(
        slug="deploy-to-production",
        proposed_markdown="Run deploy script.",
        change_summary="Clarify deployment step.",
    )
    payload = json.loads(result)

    assert payload["skill_slug"] == "deploy-to-production"
    assert payload["requires_user_approval"] is True
    assert payload["approval_token"]
    assert payload["approval_expires_at_epoch"] > int(time.time())
    assert payload["refinement_suggestions"]
    assert payload["current_markdown"].startswith("---\nowner: platform-team")


@respx.mock
async def test_apply_skill_update_requires_write_scope():
    _set_token_scope("skills:read usage:write")
    respx.get("http://testserver/api/v1/settings").mock(
        return_value=Response(200, json={"allow_agent_process_updates": True})
    )
    respx.get("http://testserver/api/v1/skills/deploy-to-production").mock(
        return_value=Response(200, json=PROCESS_DETAIL)
    )

    proposal = json.loads(
        await propose_skill_update(
            slug="deploy-to-production",
            proposed_markdown="## Steps\n\n1. Run deploy script.",
            change_summary="Refine structure.",
        )
    )

    result = await apply_skill_update(
        slug="deploy-to-production",
        proposed_markdown="## Steps\n\n1. Run deploy script.",
        change_summary="Refine structure.",
        approval_token=proposal["approval_token"],
    )
    assert "missing required scope" in result


@respx.mock
async def test_apply_skill_update_creates_new_version():
    _set_token_scope()
    respx.get("http://testserver/api/v1/settings").mock(
        return_value=Response(200, json={"allow_agent_process_updates": True})
    )
    respx.get("http://testserver/api/v1/skills/deploy-to-production").mock(
        return_value=Response(200, json=PROCESS_DETAIL)
    )
    create_route = respx.post("http://testserver/api/v1/skills/deploy-to-production/versions").mock(
        return_value=Response(
            201,
            json={"id": "version-id-1", "version_number": 4},
        )
    )

    proposed_markdown = "---\nowner: platform-team\n---\n\n## Steps\n\n1. Run deploy script."
    proposal = json.loads(
        await propose_skill_update(
            slug="deploy-to-production",
            proposed_markdown=proposed_markdown,
            change_summary="Add owner metadata and explicit steps.",
        )
    )

    result = await apply_skill_update(
        slug="deploy-to-production",
        proposed_markdown=proposed_markdown,
        change_summary="Add owner metadata and explicit steps.",
        approval_token=proposal["approval_token"],
    )
    payload = json.loads(result)

    assert payload["status"] == "updated"
    assert payload["new_version_number"] == 4
    assert create_route.called
    call_body = json.loads(create_route.calls[0].request.content)
    assert call_body["frontmatter_yaml"] == "owner: platform-team"
    assert call_body["content_md"] == "## Steps\n\n1. Run deploy script."


@respx.mock
async def test_read_skill_includes_koinoflow_context_block():
    _set_token_scope()
    respx.get("http://testserver/api/v1/skills/deploy-to-production").mock(
        return_value=Response(200, json=PROCESS_DETAIL_WITH_METADATA)
    )
    respx.post("http://testserver/api/v1/usage").mock(return_value=Response(200, json={"ok": True}))

    result = await read_skill(slug="deploy-to-production", ctx=_make_ctx())

    assert "**Koinoflow Context**" in result
    assert "Risk level: **high**" in result
    assert "Requires human approval" in result
    assert "`setup-access`" in result
    assert "Audience: engineers" in result
    assert "Retrieval keywords: deploy, ship" in result
    assert "## Step 1" in result


@respx.mock
async def test_read_skill_omits_context_block_when_metadata_empty():
    _set_token_scope()
    respx.get("http://testserver/api/v1/skills/deploy-to-production").mock(
        return_value=Response(200, json=PROCESS_DETAIL)
    )
    respx.post("http://testserver/api/v1/usage").mock(return_value=Response(200, json={"ok": True}))

    result = await read_skill(slug="deploy-to-production", ctx=_make_ctx())

    assert "**Koinoflow Context**" not in result
    assert "Risk level" not in result


@respx.mock
async def test_list_skills_includes_risk_and_keywords():
    _set_token_scope()
    respx.get("http://testserver/api/v1/skills").mock(
        return_value=Response(200, json=PROCESS_LIST_WITH_METADATA)
    )

    result = await list_skills()

    assert "[risk: high]" in result
    assert "[needs approval]" in result
    assert "(keywords: deploy, release)" in result


@respx.mock
async def test_apply_skill_update_rejects_token_mismatch():
    _set_token_scope()
    respx.get("http://testserver/api/v1/settings").mock(
        return_value=Response(200, json={"allow_agent_process_updates": True})
    )
    respx.get("http://testserver/api/v1/skills/deploy-to-production").mock(
        return_value=Response(200, json=PROCESS_DETAIL)
    )

    proposal = json.loads(
        await propose_skill_update(
            slug="deploy-to-production",
            proposed_markdown="## Steps\n\n1. Run deploy script.",
            change_summary="Refine structure.",
        )
    )

    result = await apply_skill_update(
        slug="deploy-to-production",
        proposed_markdown="## Steps\n\n1. Run deploy script.\n2. Verify.",
        change_summary="Refine structure.",
        approval_token=proposal["approval_token"],
    )
    assert "does not match the proposed markdown" in result


@respx.mock
async def test_propose_skill_update_blocked_when_setting_disabled():
    _set_token_scope()
    respx.get("http://testserver/api/v1/settings").mock(
        return_value=Response(200, json={"allow_agent_process_updates": False})
    )

    result = await propose_skill_update(
        slug="deploy-to-production",
        proposed_markdown="## Steps\n\n1. Run deploy script.",
        change_summary="Refine structure.",
    )

    assert "not enabled" in result
    assert "Allow agent process updates" in result


@respx.mock
async def test_propose_skill_update_blocked_when_setting_null():
    _set_token_scope()
    respx.get("http://testserver/api/v1/settings").mock(
        return_value=Response(200, json={"allow_agent_process_updates": None})
    )

    result = await propose_skill_update(
        slug="deploy-to-production",
        proposed_markdown="## Steps\n\n1. Run deploy script.",
        change_summary="Refine structure.",
    )

    assert "not enabled" in result
