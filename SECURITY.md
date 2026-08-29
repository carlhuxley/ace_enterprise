# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| `main`  | :white_check_mark: |

*Note: This project does not yet have a stable tagged release line; all security patches are applied directly to `main`.*

## Reporting a Vulnerability

Please report security vulnerabilities privately via GitHub — **do not open a public issue**.

### How to Submit
1. Navigate to the **Security** tab of this repository.
2. Under "Security advisories", click **Report a vulnerability**.
3. Fill in the advisory form with:
   - A description of the vulnerability and its potential impact
   - Step-by-step reproduction instructions (a minimal PoC is ideal)
   - Relevant logs, stack traces, or payload samples

### Response Timeline
- **Acknowledgment:** Within 5 business days.
- **Assessment & Fix:** If confirmed, we will coordinate an estimated timeline for a patch directly within the private advisory.
- **Coordinated Disclosure:** We adhere to responsible disclosure principles and ask reporters to maintain confidentiality until a fix has been published.

## Known Dependency Advisories

GitHub's Dependabot reports vulnerabilities across the full `uv.lock` resolution, which includes optional extras — most flagged CVEs are not part of a bare `uv sync` install. Traced via `uv tree --invert` against the lockfile:

- **Bare install** (`uv sync`, no extras): only `starlette` (via `fastapi`), `idna`, `torch` (via `sentence-transformers`), `pydantic-settings`, and `setuptools` carry open advisories — all medium/low severity except two Starlette "high" findings, one of which (SSRF/NTLM via UNC paths) is Windows-specific and doesn't apply to this project's Linux/Podman deployment target.
- **`ml` extra** (`uv sync --extra ml`, pulls in `mlflow`): accounts for the large majority of flagged CVEs — `GitPython`, `aiohttp`, `Pillow`, `sqlparse`, `pyasn1`, and `cryptography` are all transitive dependencies of `mlflow`, not of this project directly. Most are DoS-class (regex/resource-exhaustion) rather than RCE against how this codebase actually uses them; the GitPython command-injection findings require calling it against attacker-controlled repo URLs, which nothing here does.
- **`server` extra** (`packages/ace-mcp`'s `optional-dependencies.server`, pulls in `mcp`): accounts for the rest — `mcp`, `python-multipart`, `pyjwt`.
- **`docker/harness/ts-harness/package.json`** (`vitest`, npm): the one non-Python advisory (critical) requires vitest's UI server, which this codebase never starts (`vitest run`, headless) — and even then, it only runs inside a `--network none` Podman container.

Only install `ml`/`server` extras if you need MLflow experiment tracking or the MCP server integration, and keep them updated independently.

## In-Scope Areas

ACE Enterprise executes LLM-generated code as part of its TDD loop (`PythonLanguagePod`, `TypeScriptLanguagePod`, `GoLanguagePod`), sandboxed via Podman with `--network none`, `--cap-drop=all`, `--security-opt no-new-privileges`, and read-only workspace mounts.

Reports in these specific areas are especially welcome:
- Container sandbox escapes or privilege escalation
- Static security gate bypasses (Bandit / eslint-plugin-security / gosec HIGH-severity gating) prior to disk commit
- Tampering with the audit hash chain (`src/audit/`) that bypasses `src/audit/checkpoint.py` git-anchored verification
- Injection or path-traversal vulnerabilities in LLM output handling
- Bypasses in the clean-room synthesis pipeline (`bootstrap/`), such as license header stamping or provenance verification
