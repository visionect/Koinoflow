# @koinoflow/mcp

MCP server for [Koinoflow](https://github.com/visionect/Koinoflow) — access your organization's operational processes from AI clients like Claude Desktop, Cursor, and VS Code.

## Prerequisites

- Node.js 18+
- A Koinoflow workspace API key from the deployment you want to connect to
  (self-hosted or hosted)

## Setup

`KOINOFLOW_API_URL` must point at the `/api/v1` endpoint of the Koinoflow
instance you want to use. For a local dev instance that is
`http://localhost:8000/api/v1`. For a self-hosted deployment it's typically
`https://koinoflow.<your-domain>/api/v1`.

### Claude Desktop / Claude Code

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "koinoflow": {
      "command": "npx",
      "args": ["-y", "@koinoflow/mcp"],
      "env": {
        "KOINOFLOW_API_KEY": "kf_your_key_here",
        "KOINOFLOW_API_URL": "https://koinoflow.example.com/api/v1"
      }
    }
  }
}
```

### Cursor

Add to your Cursor MCP config:

```json
{
  "mcpServers": {
    "koinoflow": {
      "command": "npx",
      "args": ["-y", "@koinoflow/mcp"],
      "env": {
        "KOINOFLOW_API_KEY": "kf_your_key_here",
        "KOINOFLOW_API_URL": "https://koinoflow.example.com/api/v1"
      }
    }
  }
}
```

### VS Code (Copilot)

Add to `.vscode/mcp.json`:

```json
{
  "servers": {
    "koinoflow": {
      "command": "npx",
      "args": ["-y", "@koinoflow/mcp"],
      "env": {
        "KOINOFLOW_API_KEY": "kf_your_key_here",
        "KOINOFLOW_API_URL": "https://koinoflow.example.com/api/v1"
      }
    }
  }
}
```

## Environment Variables

| Variable            | Required | Example                                | Description                                |
| ------------------- | -------- | -------------------------------------- | ------------------------------------------ |
| `KOINOFLOW_API_KEY` | Yes      | `kf_...`                               | Your workspace API key (starts with `kf_`) |
| `KOINOFLOW_API_URL` | Yes      | `https://koinoflow.example.com/api/v1` | API base URL of your Koinoflow deployment  |

## Available Tools

### `read_process`

Read a specific process by its slug. Returns the full Markdown content with YAML frontmatter and, by default, a support-file manifest.

**Parameters:**

- `slug` (string, required) — The process slug, e.g. `"deploy-to-production"`
- `version` (number, optional) — Specific version number; defaults to latest published
- `include_files` (boolean, optional, default `true`) — Append a support-file listing; set to `false` to return only the main markdown

### `list_processes`

List available processes in the workspace. Returns titles, slugs, and descriptions.

**Parameters:**

- `department` (string, optional) — Filter by department slug
- `team` (string, optional) — Filter by team slug

## License

MIT
