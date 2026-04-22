# Contributing to Koinoflow

Thanks for your interest in contributing. This document covers how to get
your changes into the project.

## Ground rules

- By contributing, you agree that your contributions will be licensed under
  the project's [MIT License](LICENSE).
- Be kind. We follow a [Code of Conduct](CODE_OF_CONDUCT.md).
- Discuss large changes in an issue *before* opening a PR. A 30-line PR
  with a clear intent is much more likely to land than a 2,000-line PR
  that nobody was expecting.

## Development setup

Requires Docker, Docker Compose, and `make`.

```bash
git clone https://github.com/visionect/Koinoflow.git
cd Koinoflow
make setup
make up
```

See the [README](README.md#quick-start-local-development) for details on
available `make` targets.

## Coding standards

### Python (backend, mcp-server)

- Formatter / linter: `ruff`. Run `make fmt` before committing; CI runs
  `make lint`.
- Type hints on public functions where it adds clarity.
- Prefer small, testable functions. Every API endpoint must have at least
  one test.
- Use UUID primary keys for all new models (no integer PKs).

### TypeScript (frontend, mcp-package)

- `strict: true` mode. Avoid `any`; prefer `unknown` and narrow.
- Formatter: Prettier. Linter: ESLint.
- Use shadcn/ui primitives for new UI; keep Tailwind classes close to the
  JSX they apply to.
- Server state goes through TanStack Query; don't reinvent caching.

### Comments

Comments explain *why* a non-obvious decision was made. Do not write
comments that narrate what the code does.

## Tests

```bash
make test          # backend pytest suite
```

Frontend tests:

```bash
cd frontend
npm test           # Vitest
npx playwright test
```

PRs must keep all tests green. If your change needs new tests, add them.

## Commit messages

We use [Conventional Commits](https://www.conventionalcommits.org/).
Examples:

```
feat(backend): add process approval workflow
fix(frontend): restore focus to editor after save
chore(infra): bump postgres image
docs(readme): document ENABLE_BILLING
```

## Pull requests

- Keep PRs focused — one logical change per PR.
- Link to the issue your PR resolves ("Fixes #123").
- Update `README.md`, `.env.example`, and tests alongside behavior changes.
- Don't include deployment-specific or environment-specific files
  (`.env`, credentials, cloud config) in commits.

## Security-sensitive changes

Changes that touch authentication, authorization, billing, or MCP access
control get extra scrutiny and require a maintainer review. See
[SECURITY.md](SECURITY.md) for how to report vulnerabilities privately.

## Reporting bugs / requesting features

Use the GitHub issue templates. Please include:

- What you tried, what you expected, what actually happened.
- Koinoflow version / commit SHA.
- Relevant logs or a minimal reproduction.

Thanks — we appreciate the help.
