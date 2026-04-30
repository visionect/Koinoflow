<p align="center">
  <img src=".github/assets/og-image.png" alt="Koinoflow" width="720" />
</p>

<h1 align="center">Koinoflow</h1>

<p align="center">
  <em>Koino (κοινό) · shared knowledge in motion.</em>
</p>

<p align="center">
  <strong>Version-controlled operational skills for humans and AI agents.</strong>
</p>

<p align="center">
  <a href="https://koinoflow.com"><img alt="Website" src="https://img.shields.io/badge/website-koinoflow.com-0ea5e9" /></a>
  <a href="https://app.koinoflow.com"><img alt="Hosted app" src="https://img.shields.io/badge/try-app.koinoflow.com-7c3aed" /></a>
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-green.svg" /></a>
  <a href="https://github.com/visionect/Koinoflow/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/visionect/Koinoflow/actions/workflows/ci.yml/badge.svg" /></a>
  <a href="https://github.com/visionect/Koinoflow/pkgs/container/koinoflow%2Fbackend"><img alt="GHCR" src="https://img.shields.io/badge/ghcr.io-visionect%2Fkoinoflow-blue?logo=docker" /></a>
</p>

---

Koinoflow is a B2B platform where an organization writes, versions, and
governs its operational skills — then exposes that approved knowledge to
people through a web app and to AI agents through the [Model Context
Protocol (MCP)](https://modelcontextprotocol.io). When a developer asks
their editor "how do we ship a release?" or a support agent asks "what's
our refund policy?", the answer comes from the latest approved version of
your skill, not a stale wiki page.

> Status: early development. APIs, schemas, and data models may change.

Try Koinoflow on our hosted deployment at
[app.koinoflow.com](https://app.koinoflow.com). You can test the product and
onboard your account for free for 30 days.

## Features

- **Skill authoring with Tiptap.** A clean Markdown-first editor with
  diffs, revisions, comments, and approval workflows.
- **Version history as a first-class object.** Every change is an
  immutable version with an author, a commit message, and an optional
  approval gate before it becomes the "current" version.
- **Organizations → teams → departments → skills.** A workspace model
  that mirrors how real companies organize operational knowledge.
- **MCP server, remote and local.** Expose skills to any MCP-capable
  client (Claude Desktop, Cursor, Codex, etc.) over Streamable HTTP
  (hosted) or stdio (local npm package).
- **OAuth sign-in.** Google and GitHub via `django-allauth`.
- **Staleness alerts + skill audit rules.** Know when a skill hasn't
  been reviewed in N days.
- **Usage analytics.** See which skills are being read, who's reading
  them, and via which MCP client.
- **Billing-optional.** Ships with `ENABLE_BILLING=False` out of the box
  so self-hosters never see a trial banner or paywall.

## Architecture

| Layer            | Stack                                                   |
| ---------------- | ------------------------------------------------------- |
| Backend API      | Django 5 + Django Ninja, PostgreSQL, Redis              |
| Background jobs  | Celery (abstracted so Cloud Tasks can be swapped in)    |
| Auth             | django-allauth (Google + GitHub OAuth)                  |
| MCP server       | Python MCP SDK over Streamable HTTP                     |
| MCP (local pkg)  | TypeScript, `@modelcontextprotocol/sdk`, stdio          |
| Frontend         | React 19 + Vite + TypeScript (strict) + TanStack Query  |
| UI components    | shadcn/ui (Radix + Tailwind)                            |
| Editor           | Tiptap                                                  |
| API codegen      | `@hey-api/openapi-ts`                                   |
| Tests            | pytest (backend) · Vitest + Playwright (frontend)       |
| Local infra      | Docker Compose                                          |

Repo layout:

```
backend/        Django project (config/, apps/)
frontend/       React + Vite SPA
mcp-server/     Remote MCP server (Python, Streamable HTTP)
mcp-package/    Local MCP server (TypeScript, stdio, npm-publishable)
infra/          docker-compose.yml for local dev
```

## Quick start (local development)

Requires Docker, Docker Compose, and `make`.

```bash
git clone https://github.com/visionect/Koinoflow.git
cd Koinoflow
make setup      # copies .env, builds images, migrates, creates superuser
make up         # starts backend, frontend, postgres, redis, mcp-server
```

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000/api/v1
- API docs (Swagger-style): http://localhost:8000/api/v1/docs
- Django admin: http://localhost:8000/admin/ (sign in with the superuser `make setup` created for you)
- MCP server: http://localhost:8001/mcp

Other common targets — run `make help` for the full list:

```bash
make migrate           # apply Django migrations
make makemigrations    # generate new migrations
make test              # backend tests
make lint              # ruff check + format check
make fmt               # auto-format with ruff
make down              # stop services
make clean             # stop + remove volumes
```

## Configuration

All configuration is via environment variables. Copy `.env.example` to
`.env` and edit. Highlights:

| Variable                  | Default                | Purpose                                           |
| ------------------------- | ---------------------- | ------------------------------------------------- |
| `DJANGO_SECRET_KEY`       | *(required)*           | Django secret key                                 |
| `DEBUG`                   | `True`                 | Django debug mode                                 |
| `DATABASE_URL`            | *(required)*           | Postgres connection string                        |
| `REDIS_URL`               | *(required)*           | Redis connection string                           |
| `DEFAULT_FROM_EMAIL`      | `noreply@example.com`  | Default email sender                              |
| `INVITATION_FROM_EMAIL`   | = `DEFAULT_FROM_EMAIL` | Sender for team-invite emails                     |
| `ALERTS_FROM_EMAIL`       | = `DEFAULT_FROM_EMAIL` | Sender for staleness-alert emails                 |
| `RESEND_API_KEY`          | *(empty)*              | Resend API key (for transactional email)          |
| `ENABLE_BILLING`          | `False`                | Turn on trial/subscription gating (hosted only)   |
| `GOOGLE_OAUTH_CLIENT_ID`  | *(optional)*           | Google sign-in                                    |
| `GITHUB_OAUTH_CLIENT_ID`  | *(optional)*           | GitHub sign-in                                    |
| `CONNECTOR_ENCRYPTION_KEY`| *(required for connectors)* | Fernet key for connector credential encryption — generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `SKILL_SECRET_KMS_KEY`    | *(optional)*           | Full GCP KMS key resource name for skill-secret envelope encryption; if unset, falls back to `CONNECTOR_ENCRYPTION_KEY` |

## Skill secrets & trust model

Executable skills can declare secrets they need (e.g. `OPENAI_API_KEY`,
`SLACK_BOT_TOKEN`). Those values are stored in the database and injected
into the skill executor's environment at run time. Here is the full
picture of how they are protected and why you can trust the system.

### Encryption at rest

Secret values are **never stored in plaintext**. Koinoflow uses
*envelope encryption*:

1. A random 256-bit data-encryption key (DEK) is generated per secret
   value.
2. The DEK is used to Fernet-encrypt the plaintext value.
3. The DEK itself is wrapped by either:
   - **Google Cloud KMS** (hosted deployment and any self-hoster that
     sets `SKILL_SECRET_KMS_KEY`) — the DEK ciphertext is stored in the
     database; the raw key material never touches the database.
   - **Fernet key** (fallback for self-hosters without KMS) — the entire
     token is encrypted with the `CONNECTOR_ENCRYPTION_KEY` you
     configure.

Even if your database is compromised, no secret plaintext is recoverable
without the KMS key or the Fernet master key.

### Self-hosted deployments — you own the keys

When you run Koinoflow on your own infrastructure:

- **You control the database.** Encrypted values live only in your
  Postgres instance.
- **You control the encryption key.** Set `CONNECTOR_ENCRYPTION_KEY` to
  a Fernet key you generate; it never leaves your environment.
- **You control the KMS key.** Point `SKILL_SECRET_KMS_KEY` at a KMS key
  in your own GCP project if you want hardware-backed key storage.

There is no Visionect-controlled key material in self-hosted
deployments. If you do not trust a hosted service, run it yourself —
the Docker images and source code are public.

### Hosted deployment (app.koinoflow.com)

The hosted service uses Google Cloud KMS with customer-isolated key
versions. Visionect's infrastructure is the trust boundary. We do not
log or transmit plaintext secret values; they are decrypted only inside
the skill executor process at run time.

### Sandbox / test runs — ephemeral secret overrides

The sandbox debugger lets you run a skill interactively without storing
a secret permanently. When you execute a skill in sandbox mode you can
supply **ephemeral secret overrides** for the current run:

- Values are passed in the execute request body, injected into the
  executor environment, and **never written to the database**.
- The UI labels them clearly as "used for this run only, not saved".
- Use a short-lived or scoped credential (e.g. an API key with read-only
  access) so that even if the run output is captured it carries minimal
  blast radius.

### External vault references — we never see the secret

Organizations that already manage secrets in their own vault can store
a **vault reference** instead of the secret value. When you choose this
option, Koinoflow stores only the reference string (e.g.
`gcp-sm://my-project/my-secret`) — the actual secret never enters our
database, our logs, or any backup.

Concretely, this is what each party can see:

| Observer                                     | What they see          |
| -------------------------------------------- | ---------------------- |
| Koinoflow operators (hosted) or you (self-hosted) | the reference string only |
| An attacker who exfiltrates the database     | the reference string only |
| The skill executor at run time               | the resolved value, in memory, for one run |

The executor calls your vault directly using credentials you configure
on the executor host (e.g. a GCP service account with
`secretmanager.secretAccessor`). The plaintext is held in memory for the
duration of one run and never written to Koinoflow's database.

Supported reference schemes today:

| Scheme    | Example                               | Resolves via                                       |
| --------- | ------------------------------------- | -------------------------------------------------- |
| `env://`  | `env://OPENAI_API_KEY`                | An env var on the executor process                 |
| `gcp-sm://` | `gcp-sm://my-project/my-secret`     | Google Cloud Secret Manager (latest version)       |
| `gcp-sm://` | `gcp-sm://my-project/my-secret@7`   | Google Cloud Secret Manager (pinned version)       |

To store a vault reference instead of a value, send the reference in the
`vault_ref` field when upserting a skill secret:

```http
PUT /api/v1/skills/{slug}/secrets/OPENAI_API_KEY
Content-Type: application/json

{ "vault_ref": "gcp-sm://my-project/openai-key" }
```

The list endpoint shows each secret's `kind` (`encrypted` or
`vault_ref`) and, for vault references, the reference itself — so it's
visible at a glance which secrets Koinoflow holds and which live
entirely outside our system.

Additional providers (HashiCorp Vault, AWS Secrets Manager,
Azure Key Vault) are planned; track progress in
[GitHub Issues](https://github.com/visionect/Koinoflow/issues).

### Access logs

Every secret read during a skill execution is recorded in
`skill_secret_access_log`. Workspace admins can audit which secrets were
accessed, by whom, and during which run.

## Self-hosting with pre-built images

Every push to `main` publishes multi-arch Docker images to the GitHub
Container Registry:

```
ghcr.io/visionect/koinoflow/backend:latest
ghcr.io/visionect/koinoflow/mcp-server:latest
```

Tagged releases (`vX.Y.Z`) also publish `:X.Y.Z` and `:X.Y` tags. The
images are public — no login required to pull.

## Running the MCP server against your instance

The local MCP package (TypeScript, stdio) lets any MCP client talk to your
Koinoflow deployment. See [`mcp-package/README.md`](mcp-package/README.md)
for install + editor configuration (Claude Desktop, Cursor, Codex, etc.).

```jsonc
{
  "mcpServers": {
    "koinoflow": {
      "command": "npx",
      "args": ["-y", "@koinoflow/mcp"],
      "env": {
        "KOINOFLOW_API_URL": "https://your-koinoflow.example.com/api/v1",
        "KOINOFLOW_API_KEY": "kn_..."
      }
    }
  }
}
```

## Contributing

We welcome issues and pull requests. Please read
[CONTRIBUTING.md](CONTRIBUTING.md) for the development workflow and
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) before participating.

## Security

If you believe you've found a security issue, please read
[SECURITY.md](SECURITY.md) for coordinated disclosure instructions. Do not
file a public GitHub issue for vulnerabilities.

## License

Koinoflow is released under the [MIT License](LICENSE).

The **Koinoflow** name and logo are trademarks of Visionect d.o.o. — see
[TRADEMARK.md](TRADEMARK.md) for guidance on acceptable use.

## Hosted vs. self-hosted

You can run Koinoflow entirely on your own infrastructure using the
instructions above — that's the default mode and it's free forever under
MIT. If you'd rather not operate it yourself, start with our managed hosted
deployment at [app.koinoflow.com](https://app.koinoflow.com): test Koinoflow
and onboard your account free for 30 days. After the trial, we can help set up
Koinoflow in your infrastructure and migrate your data there, or you can keep
using our deployment for a custom fee.

## Sponsorship

Active development of Koinoflow is sponsored by
[Visionect](https://www.visionect.com), which also operates the hosted
service at [app.koinoflow.com](https://app.koinoflow.com). The project remains
open-source; sponsorship funds full-time engineering and community
support.
