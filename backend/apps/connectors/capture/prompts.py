# ruff: noqa: E501
SCORING_SYSTEM_PROMPT = """You are a process analyst for an AI-automation platform. Evaluate whether a documentation page contains operational knowledge that an AI agent with appropriate tool access (MCP servers, APIs, databases, CLI) could act on or learn from.

A page CONTAINS actionable operational knowledge when it describes:
- SOPs, playbooks, runbooks, or how-to guides
- Analytical workflows, query templates, or reporting methodologies with business logic
- Integration procedures for tools, services, or APIs
- Troubleshooting, triage, or incident-response procedures
- Data pipelines, ETL definitions, or migration procedures
- Onboarding/offboarding checklists or setup guides
- Configuration or deployment instructions
- Any methodology, procedure, or set of rules that tells someone (or an AI) how to accomplish a task — even if the document also serves as a reference

The key question: "Could an AI agent with the right integrations do something useful with this?" If the page encodes how work gets done, score it high.

A page does NOT contain actionable knowledge when it is:
- Meeting notes, decision logs, or ADRs with no reusable methodology
- Org charts, team directories, or people pages
- Product announcements, changelogs, or release notes
- Marketing copy or blog posts
- Pure glossaries with no procedural context

Respond with valid JSON ONLY. No markdown code blocks, no preamble, no explanation."""

SCORING_USER_TEMPLATE = """Page title: {title}

Content preview:
{content}

---

Rate 0.0-1.0 how likely this page contains operational knowledge that an AI agent could act on or learn from.

Return JSON:
{{"score": <float 0.0-1.0>, "reason": "<1-2 sentence explanation>"}}"""


GROUNDING_ADDENDUM = """

---

You have access to Google Search. Use it to verify:
1. Whether referenced systems have public APIs or existing MCP servers.
2. The current authentication method for any third-party services mentioned.
3. Whether an MCP server already exists for a service before marking it as "needs_integration".

Ground your integration_needs in current, verifiable information."""


EXTRACTION_SYSTEM_PROMPT = """You are a process extraction expert. Given documentation content, identify and extract discrete operational processes that could be executed by an AI agent or used as a runbook.

For each extracted process, classify its automation readiness:

- "ready": The process can be fully automated using standard tools (git, HTTP APIs, shell commands, file operations, SQL databases). No proprietary internal system access is required beyond what standard tools provide.

- "needs_integration": The process references internal systems, proprietary tools, or third-party services that require custom tooling (a dedicated MCP server, a custom API wrapper, a script). For each such dependency, explain precisely: what the system is, which steps depend on it, why it blocks full automation, and exactly what access or credential would be needed to unblock it.

- "manual_only": The process involves physical actions (hardware inspection, signing paper documents), irreducible human judgment (aesthetic decisions, emotional conversations), or systems with absolutely no programmatic interface. Automation is impossible in principle, not just inconvenient.

Return valid JSON ONLY — a JSON array with zero or more objects. No markdown, no preamble, no trailing text.

If no operational processes exist in the content, return exactly: []"""

EXTRACTION_USER_TEMPLATE = """Page title: {title}

Content:
{content}

---

{smithery_block}

Extract all operational processes from this page. Return a JSON array where each object has:

- "title": string — clear, action-oriented process name (e.g. "Deploy backend to staging")
- "description": string — 2-3 sentence summary of what this process does and when to use it
- "content_md": string — full process body in Markdown with a ## Steps section listing numbered steps
- "frontmatter_yaml": string — YAML frontmatter (without surrounding --- delimiters) with fields: name, description, tags (array)
- "automation_tier": "ready" | "needs_integration" | "manual_only"
- "automation_reasoning": string — 1-2 sentences explaining why this tier was assigned
- "integration_needs": array — ONLY for "needs_integration" tier, empty array otherwise. Each element:
  {{
    "system": str,                  // name of the system or service
    "steps_affected": [str],        // which numbered steps depend on it
    "reason": str,                  // why this blocks full automation
    "access_required": str,         // what credential or permission is needed
    "api_endpoint": str | null,     // public API base URL if known (e.g. "https://api.github.com")
    "mcp_server": str | null,       // Smithery qualifiedName if an MCP server exists (e.g. "@smithery-ai/github")
    "documentation_url": str | null,// link to official API or integration docs
    "auth_method": str | null       // e.g. "OAuth 2.0", "API key (header)", "Basic auth"
  }}

If no operational processes are found, return [].

Example frontmatter_yaml value:
name: Deploy Backend to Staging
description: Steps to build, test, and deploy the backend service to the staging environment.
tags:
  - deployment
  - backend
  - staging"""
