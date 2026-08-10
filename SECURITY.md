# Security Policy

## Reporting a Vulnerability

Please report security vulnerabilities privately — **do not open a public
GitHub issue**.

Email **carl@carlhuxley.com** with:

- A description of the vulnerability and its potential impact
- Steps to reproduce (a minimal repro is ideal)
- Any relevant logs, stack traces, or PoC code

You should receive an acknowledgment within 5 business days. We'll follow
up with an assessment and, if confirmed, a plan and rough timeline for a
fix before any public disclosure.

## Scope

ACE Enterprise executes LLM-generated code as part of its TDD loop
(`PythonLanguagePod`, `TypeScriptLanguagePod`, `GoLanguagePod`), sandboxed
via Podman with `--network none`, `--cap-drop=all`,
`--security-opt no-new-privileges`, and read-only workspace mounts. Reports
in this area are especially welcome, including:

- Container sandbox escapes or privilege escalation
- Ways to bypass the static security gates (Bandit / eslint-plugin-security
  / gosec HIGH-severity gating) before code is committed to disk
- Tampering with the audit hash chain (`src/audit/`) that isn't caught by
  `src/audit/checkpoint.py`'s git-anchored verification
- Injection or path-traversal issues in code that handles LLM output

Issues in the clean-room synthesis pipeline (`bootstrap/`) — e.g. license
header stamping, provenance verification bypasses — are also in scope.

## Supported Versions

This project does not yet have a stable release line; security fixes are
applied to `main`.
