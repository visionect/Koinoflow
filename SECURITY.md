# Security Policy

## Supported versions

Koinoflow is in early development. Security fixes are applied to the `main`
branch and released as soon as possible. We do not yet maintain long-lived
stable branches.

| Version   | Supported |
| --------- | --------- |
| `main`    | Yes       |
| Older tags| No        |

## Reporting a vulnerability

**Please do not file a public GitHub issue for security vulnerabilities.**

Report privately using GitHub's "Report a vulnerability" button on the
repository's Security tab, or email
[security@visionect.com](mailto:security@visionect.com) with:

- A clear description of the issue and the impact.
- The minimal steps (or proof-of-concept) required to reproduce it.
- The affected commit SHA / release, and your environment if relevant.
- Whether you intend to publicly disclose, and on what timeline.

We aim to:

1. Acknowledge receipt within **2 business days**.
2. Confirm the issue and share a preliminary severity assessment within
   **7 days**.
3. Ship a fix or a mitigation as fast as the severity warrants, and
   coordinate disclosure with you.

We will credit reporters in the release notes unless you prefer to remain
anonymous.

## Scope

In scope:

- The Koinoflow backend, frontend, MCP server, and MCP client package in
  this repository.
- The default configuration shipped in this repository.

Out of scope:

- Bugs that require an attacker to already be an authenticated admin of the
  target workspace.
- DoS via unbounded input length (report as a regular issue).
- Vulnerabilities in third-party dependencies — report those upstream. If
  exploitable *through* Koinoflow, report here too.
- Configuration mistakes in deployments you don't operate.
