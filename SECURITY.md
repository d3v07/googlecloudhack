# Security Policy

## Reporting a vulnerability

Please **do not** open a public issue for a security report. Instead, open a private
[GitHub Security Advisory](https://docs.github.com/en/code-security/security-advisories) on this
repository, or contact the maintainers (@d3v07, @Frex22) directly. We'll acknowledge within a few
days and keep you posted on the fix.

## Supported versions

This is a hackathon project; the `main` branch is the supported version.

## Security model

- **Agents and tools are read-only.** Only the deterministic controller performs a database
  mutation (an index create), and only after a one-time, **hash-bound human approval** that binds
  the approval to the exact evidence the operator reviewed.
- **The approver identity is derived from the verified session**, never from client input.
- **Workload queries are allowlist-validated**, read-only, and capped (`limit` + `maxTimeMS`) —
  no raw filters, no `$where`/eval.
- **Secrets** live in `.env` (local) and Secret Manager (production); the read API and dashboard
  read shared secrets via Secret Manager references. Nothing sensitive is committed.
- `.gitignore` excludes `.env`, key files, and local tooling state; CI runs format, lint, and tests.
