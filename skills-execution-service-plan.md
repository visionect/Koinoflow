# Skills Execution Service on GCP — Architecture & Build Plan

A governed skill distribution service that lets AI agents execute skills as
remote, sandboxed code via a single MCP `execute_skill` tool. Designed to run
on GCP free tier for development and very low-volume production use.

---

## Goals

1. **Single MCP tool surface.** Agents see one tool: `execute_skill(skill_id, version, inputs)`. Discovery via `list_skills` and `describe_skill`.
2. **Governance.** Every skill is versioned, signed, ACL-gated, and audited.
3. **Sandboxed execution.** Skills run in isolated containers, never on the agent's host.
4. **Free-tier friendly.** Stay within GCP always-free quotas during dev and light prod.
5. **Secrets handled centrally.** Skills declare what they need; the service injects scoped secrets at runtime.

---

## High-level architecture

```
┌──────────────┐     MCP/HTTPS      ┌──────────────────────────┐
│   AI Agent   │ ──────────────────▶│  Skills MCP Server       │
│  (Claude,    │  execute_skill()   │  (Cloud Run Service)     │
│  Cursor,     │                    │  - auth (OAuth/API key)  │
│  custom)     │                    │  - skill registry API    │
└──────────────┘                    │  - ACL + governance      │
                                    │  - audit log writer      │
                                    │  - dispatcher            │
                                    └────────────┬─────────────┘
                                                 │
                  ┌──────────────────────────────┼─────────────────────────┐
                  │                              │                         │
                  ▼                              ▼                         ▼
          ┌───────────────┐            ┌─────────────────┐        ┌──────────────┐
          │  Firestore    │            │ Secret Manager  │        │ Cloud Run    │
          │  - skills     │            │ - per-skill     │        │ Jobs         │
          │  - versions   │            │   secrets       │        │ (executor)   │
          │  - ACLs       │            │ - scoped via    │        │ gVisor/      │
          │  - audit log  │            │   IAM           │        │ second-gen   │
          └───────────────┘            └─────────────────┘        └──────┬───────┘
                                                                         │
                                              ┌──────────────────────────┼───┐
                                              ▼                          ▼   │
                                      ┌───────────────┐       ┌────────────┐ │
                                      │ Artifact      │       │ Cloud      │ │
                                      │ Registry      │       │ Storage    │ │
                                      │ (skill        │       │ (skill     │ │
                                      │  images)      │       │  payloads, │ │
                                      └───────────────┘       │  outputs)  │ │
                                                              └────────────┘ │
                                                                             │
                                                              Cloud Logging ◀┘
```

---

## Component breakdown

### 1. Skills MCP Server (Cloud Run Service)

**What it does:** Public-facing MCP endpoint. Authenticates agents, exposes `list_skills` / `describe_skill` / `execute_skill`, validates inputs against the skill manifest, dispatches execution to a Cloud Run Job, streams back results, writes the audit record.

**Tech:**
- **Language:** Python (FastAPI + the official `mcp` SDK) or TypeScript (`@modelcontextprotocol/sdk`). Pick whichever your team writes faster.
- **Runtime:** Cloud Run Service, second-gen execution environment.
- **Min instances:** 0 (scale to zero). Cold start ~1–3s for a slim Python image — acceptable for an agent tool.
- **Concurrency:** 80 (default) is fine.
- **CPU/memory:** start at 0.5 vCPU / 512 MiB, raise if needed.

**Endpoints (MCP tools):**
- `list_skills(filter?)` → `[{ skill_id, name, summary, latest_version, tags }]`
- `describe_skill(skill_id, version?)` → full manifest including input schema
- `execute_skill(skill_id, version?, inputs)` → `{ run_id, status, output, logs_url }`
- `get_run(run_id)` → for polling long-running executions

**Auth model:**
- Agent → server: OAuth 2.1 (MCP standard) or scoped API keys for first version. API keys are simpler; do them first.
- Server → GCP services: a single service account with narrow IAM roles (read Firestore, write Cloud Run Jobs, read Secret Manager via short-lived tokens).

**Cost:** Within free tier for dev. Free tier covers 2M requests, 360k vCPU-seconds, 180k GiB-seconds per month. You won't touch this in development.

---

### 2. Skill Registry (Firestore in Native mode)

**What it stores:**

```
skills/{skill_id}
  ├─ name: string
  ├─ description: string
  ├─ owner: string (email/team)
  ├─ created_at, updated_at
  ├─ tags: [string]
  ├─ visibility: "public" | "private" | "org:<id>"
  └─ versions/{version}            (subcollection)
       ├─ manifest: <skill manifest, see below>
       ├─ image_uri: "europe-west1-docker.pkg.dev/PROJECT/skills/SKILL_ID:VERSION"
       ├─ image_digest: "sha256:..."
       ├─ signature: "..."        (cosign signature, optional)
       ├─ resource_limits: { cpu, memory_mb, timeout_s, max_concurrent }
       ├─ secret_refs: [          (declared secrets — names only, no values)
       │    { name: "OPENAI_API_KEY", scope: "per-tenant" | "global" }
       │  ]
       ├─ network_policy: "none" | "egress_allowlist"
       ├─ allowed_egress: ["api.example.com"]
       └─ published_at: timestamp

acls/{skill_id}/{principal}
  ├─ principal: "agent:<id>" | "user:<email>" | "tenant:<id>"
  ├─ permissions: ["execute", "describe"]
  └─ granted_by, granted_at

runs/{run_id}                     (audit log, also queried for status)
  ├─ skill_id, version
  ├─ principal: who called
  ├─ inputs_hash: sha256 of inputs (don't store raw inputs if sensitive)
  ├─ status: "queued" | "running" | "succeeded" | "failed" | "timeout"
  ├─ started_at, finished_at
  ├─ exit_code, error_message
  ├─ output_uri: "gs://..."        (truncated outputs go inline; large to GCS)
  ├─ logs_uri: Cloud Logging query link
  └─ resource_usage: { cpu_seconds, memory_peak_mb }
```

**Why Firestore:** Free tier gives 1 GiB storage, 50k reads / 20k writes / 20k deletes per day. Plenty for an MVP. Native indexes, easy SDK access from Cloud Run.

**Alternative:** Cloud SQL Postgres if you want SQL joins and a normal schema. Postgres has no free tier on GCP though — the smallest db-f1-micro is ~$10/month. Stick with Firestore.

---

### 3. Skill Manifest (the contract)

Every skill has a `skill.yaml` (or `manifest.json`) at publish time. This is what `describe_skill` returns to the agent.

```yaml
skill_id: pdf-summarizer
version: "1.4.2"
name: PDF Summarizer
description: |
  Extracts text from a PDF and returns a concise summary.
owner: data-platform@example.com
tags: [documents, pdf, summarization]

# What the agent sees as the input schema for execute_skill()
input_schema:
  type: object
  required: [pdf_url]
  properties:
    pdf_url:
      type: string
      description: HTTPS URL to a PDF file
    max_length:
      type: integer
      default: 500

# What the skill returns
output_schema:
  type: object
  properties:
    summary: { type: string }
    word_count: { type: integer }

# How to run it
runtime:
  type: container             # "container" | "python_script" | "node_script"
  image: europe-west1-docker.pkg.dev/PROJECT/skills/pdf-summarizer:1.4.2
  entrypoint: ["python", "/app/run.py"]
  # I/O contract: stdin = JSON inputs, stdout = JSON output, stderr = logs

resource_limits:
  cpu: "1"
  memory_mb: 512
  timeout_s: 60
  max_concurrent: 10          # global cap across all callers

secrets:
  - name: OPENAI_API_KEY
    scope: global             # "global" or "per-tenant"
  - name: INTERNAL_API_KEY
    scope: per-tenant

network:
  policy: egress_allowlist
  allowed: ["api.openai.com", "internal-api.example.com"]
```

**The I/O contract:** keep it boring. The container reads a single JSON object from stdin, writes a single JSON object to stdout, anything on stderr becomes logs. This is the simplest thing that works and matches what most existing sandbox tools do.

---

### 4. Skill Executor (Cloud Run Jobs)

**What it does:** Runs the actual skill code in an isolated container, one job execution per `execute_skill` call.

**Why Cloud Run Jobs:**
- Built on the second-gen execution environment with full Linux compatibility plus the gVisor/VMM isolation boundary.
- Pay per second of execution. Free tier covers a lot of dev usage.
- Native timeout, retry, max-concurrent settings.
- Each execution is a fresh container — no state leak between invocations.

**Two execution patterns:**

**Pattern A — one image per skill (recommended).**
The skill author publishes a container image to Artifact Registry. The MCP server creates a Cloud Run Job execution from that image at call time, passing inputs as args or environment.

Pros: clean isolation, skills can have any deps, easy to version.
Cons: cold start = image pull time (1–10s for slim images).

**Pattern B — one base image, skill code injected.**
A generic Python or Node base image; the skill's code is fetched from Cloud Storage at start. Faster updates, slower per-call (download).

Start with Pattern A. Add Pattern B later if needed for lightweight skills.

**Job creation flow:**

```python
# Pseudocode in the MCP server
def execute_skill(skill_id, version, inputs, principal):
    skill = registry.get(skill_id, version)
    check_acl(principal, skill, "execute")
    validate_inputs(inputs, skill.input_schema)
    
    run_id = uuid7()
    inputs_uri = upload_to_gcs(inputs, f"runs/{run_id}/inputs.json")
    
    # Mint short-lived secret access for this run only
    secrets = mint_secrets(skill.secret_refs, principal, ttl=skill.timeout_s + 30)
    
    # Create a Cloud Run Job execution
    execution = run_jobs.create_execution(
        job_name=f"skill-{skill_id}-{version}",
        env=secrets | {
            "RUN_ID": run_id,
            "INPUTS_URI": inputs_uri,
            "OUTPUT_URI": f"gs://.../runs/{run_id}/output.json",
        },
        timeout=skill.timeout_s,
        cpu=skill.cpu,
        memory=f"{skill.memory_mb}Mi",
    )
    
    audit.write_run(run_id, "queued", skill_id, version, principal)
    
    if skill.timeout_s <= 30:
        # Wait inline, return result
        wait_for_completion(execution, run_id)
        return load_output(run_id)
    else:
        # Return run_id, agent polls get_run()
        return {"run_id": run_id, "status": "running"}
```

**Pre-deployed jobs vs ad-hoc:** Cloud Run Jobs are deployed once per skill version, then executed on demand. The deploy happens in CI when a skill is published; the MCP server only triggers executions.

---

### 5. Secret Manager (Google Secret Manager)

**What it does:** Stores all skill secrets. The MCP server brokers access at execution time.

**Free tier:** 6 active secret versions free per month, 10k access operations free per month. Tight but workable for dev.

**Pattern:**
- Each declared secret in the skill manifest maps to a Secret Manager secret.
- Naming convention: `skill-{skill_id}-{secret_name}` for global, `skill-{skill_id}-{tenant_id}-{secret_name}` for per-tenant.
- The skill's executor service account has IAM `roles/secretmanager.secretAccessor` only on the secrets declared in its manifest. Enforced at deploy time by your CI.
- The MCP server fetches the actual values at execution time and passes them as env vars to the Cloud Run Job. Secrets are never written to disk.

**Better but more complex:** use Cloud Run's native secret integration where Secret Manager values mount as env vars without your app touching them. This is the right move once you're past MVP — the executor service account reads directly, the MCP server never sees the secret value.

---

### 6. Artifact Registry (skill container images)

**What it does:** Hosts the container images that Cloud Run Jobs run.

**Free tier:** First 0.5 GB free, then $0.10/GB/month. Slim Python images are ~150 MB; you can fit a few dozen skill versions in the free tier.

**Layout:**
```
europe-west1-docker.pkg.dev/PROJECT_ID/skills/SKILL_ID:VERSION
```

**Build pipeline (CI, triggered by skill repo push):**
1. Lint the skill manifest.
2. Build the container with `docker build` or Cloud Build.
3. Run skill's own test suite inside the container.
4. Tag with semver and `git sha`.
5. Push to Artifact Registry.
6. Optionally sign with cosign.
7. Call your MCP server's admin API (or write directly to Firestore) to register the new version.
8. Deploy a Cloud Run Job for this skill+version (idempotent).

Use Cloud Build for this — it has a free tier of 120 build-minutes/day.

---

### 7. Cloud Storage (inputs, outputs, large payloads)

**What it does:** Holds anything bigger than ~10 KB that an inline JSON response can't carry. Inputs over a threshold are uploaded; large outputs are written to GCS and referenced by URI in the run record.

**Free tier:** 5 GB standard storage in us-central1/east1/west1 always free, plus 5k Class A and 50k Class B operations/month free.

**Bucket layout:**
```
gs://PROJECT-skills-runs/
  runs/
    {run_id}/
      inputs.json
      output.json
      logs.txt
```

**Lifecycle policy:** auto-delete after 30 days. Free tier breaks fast if you hoard.

---

### 8. Audit log + observability (Cloud Logging + Firestore)

**Two layers:**

**Structured run records (Firestore `runs/` collection)** — one document per execution. Queryable: "all runs by tenant X last week," "all failed runs of skill Y."

**Detailed execution logs (Cloud Logging)** — automatic. Cloud Run pipes stdout/stderr to Cloud Logging by default. Tag log entries with `run_id` so you can pull all logs for a run via:
```
resource.type="cloud_run_job" AND labels.run_id="abc-123"
```

**Free tier:** 50 GB/month of log ingestion is free, 30 days retention free. You will not hit this.

---

## Free-tier cost summary (always-free quotas)

| Service | Always-free quota | Use in this stack |
|---|---|---|
| Cloud Run | 2M req, 360k vCPU-s, 180k GiB-s/mo | MCP server + Jobs |
| Firestore | 1 GiB, 50k reads / 20k writes per day | Registry + audit |
| Cloud Storage | 5 GB + 5k/50k ops/mo (US regions) | Inputs/outputs |
| Cloud Logging | 50 GB ingest/mo, 30d retention | Logs |
| Secret Manager | 6 active versions, 10k access ops/mo | Secrets |
| Artifact Registry | 0.5 GB storage | Images |
| Cloud Build | 120 build-min/day | Skill CI |

**Realistic dev cost:** $0/month if you stay disciplined about regions (us-central1/east1/west1) and don't accumulate images.

**First real cost driver:** Artifact Registry storage once you have ~3+ skill versions averaging 200 MB. Mitigate by deleting old versions or using slim base images (Distroless, Alpine, or Chainguard).

---

## Build phases

### Phase 0: One skill, end-to-end (1–2 days)

Goal: prove the loop. Hardcode everything.

1. Pick one trivial skill (e.g., "reverse a string").
2. Write a Dockerfile, push to Artifact Registry manually.
3. Create a Cloud Run Job manually.
4. Write a Cloud Run Service that exposes one MCP tool `execute_skill` that triggers that one Job and returns stdout.
5. Connect Claude Desktop or another MCP client. Call it.

When this works end-to-end, you understand the whole stack.

### Phase 1: Real registry + manifest (3–5 days)

1. Move skill metadata into Firestore.
2. Implement `list_skills` and `describe_skill`.
3. Add input schema validation against the manifest before execution.
4. Add the run record write on every call.
5. Build a CLI or simple admin UI to publish a new skill version (`skills publish ./my-skill/`).

### Phase 2: Auth, ACL, audit (3–5 days)

1. Add API key auth on the MCP server.
2. Add ACL checks (which principal can execute which skill).
3. Wire up Cloud Logging structured logs with `run_id`.
4. Build a `get_run(run_id)` endpoint for status polling.

### Phase 3: Secrets (2–3 days)

1. Declare secrets in manifest.
2. Provision them in Secret Manager via CI.
3. Inject at job creation as env vars (using Cloud Run's secret-mounting if possible).
4. Test: skill A cannot read skill B's secrets.

### Phase 4: Production hardening (ongoing)

- OAuth instead of API keys.
- Image signing with cosign and verification at execute time.
- Network egress allowlist enforcement (use VPC connector + Cloud NAT or per-job egress rules — this gets non-trivial).
- Per-tenant rate limits.
- Budget alerts on the GCP project.
- Skill author UI / dashboard.

---

## Things to watch out for

1. **Cloud Run Job cold starts.** A skill that runs in 200ms but cold-starts in 5s feels broken to the agent. Options: pre-warmed Cloud Run Service per high-traffic skill, or accept the latency and document it.
2. **Egress control is harder than it sounds.** Cloud Run doesn't natively give you per-job network policies. You either route through a VPC + Cloud NAT with egress filtering, or you trust skill authors not to do bad things, or you use a forward proxy your skills are forced to use. The proxy is the cleanest pattern.
3. **Secret leakage via logs.** Skills can `print(os.environ)` and leak everything. Either scrub logs in the executor wrapper, or make secrets accessible via a sidecar/short-lived token endpoint instead of env vars.
4. **Concurrency limits.** Cloud Run Jobs have a default max parallel executions; check it before launching a popular skill.
5. **Streaming.** MCP supports streaming tool results, but Cloud Run Jobs don't naturally stream. For long-running skills, return `run_id` immediately and let the agent poll `get_run`. Or run the skill in a Cloud Run Service with a streaming HTTP response.
6. **Image bloat.** A 2 GB image per skill version eats your free tier in days. Push for slim base images and `--no-cache` pip installs.
7. **Multi-tenancy.** If different agents represent different customers, you need tenant isolation in secrets, ACLs, audit logs, and rate limits. Bake this in from Phase 1, retrofitting is painful.

---

## Minimum viable file layout

```
skills-service/
├── server/                          # MCP server (Cloud Run Service)
│   ├── Dockerfile
│   ├── main.py                      # FastAPI + MCP SDK
│   ├── registry.py                  # Firestore client
│   ├── executor.py                  # Cloud Run Jobs client
│   ├── secrets.py                   # Secret Manager broker
│   ├── auth.py                      # API key / OAuth
│   ├── acl.py
│   ├── audit.py
│   └── schemas.py                   # manifest + run schemas
│
├── skills/                          # Each skill is a subdirectory
│   └── pdf-summarizer/
│       ├── skill.yaml               # the manifest
│       ├── Dockerfile
│       ├── run.py                   # entrypoint
│       ├── requirements.txt
│       └── tests/
│
├── cli/
│   └── skills_cli.py                # `skills publish ./skills/pdf-summarizer`
│
├── infra/                           # Terraform or gcloud scripts
│   ├── project.tf                   # Firestore, Secret Manager, AR, GCS
│   ├── cloud_run_service.tf
│   ├── iam.tf                       # service accounts + roles
│   └── README.md
│
└── .github/workflows/
    ├── publish-skill.yml            # build + push image + register version
    └── deploy-server.yml            # deploy the MCP server
```

---

## Reading list

- MCP spec: https://modelcontextprotocol.io
- Cloud Run Jobs docs: https://cloud.google.com/run/docs/create-jobs
- Cloud Run container runtime contract (sandboxing details)
- Anthropic's "Building agents that reach production systems with MCP" — the section on thin tool surfaces and Code Mode is the reference for this whole pattern.
- Cloudflare's "Code Mode" blog post — different infra, same philosophy.

---

## TL;DR

Stack: **Cloud Run Service (MCP server) + Cloud Run Jobs (executor) + Firestore (registry/audit) + Secret Manager (secrets) + Artifact Registry (images) + Cloud Storage (large payloads) + Cloud Logging (logs).**

Free for development. Single `execute_skill` tool surface. gVisor sandboxing comes free with Cloud Run. Phase 0 to working demo in a couple of days.
