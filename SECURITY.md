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

## In-Scope Areas

ACE Enterprise executes LLM-generated code as part of its TDD loop (`PythonLanguagePod`, `TypeScriptLanguagePod`, `GoLanguagePod`), sandboxed via Podman with `--network none`, `--cap-drop=all`, `--security-opt no-new-privileges`, and read-only workspace mounts.

Reports in these specific areas are especially welcome:
- Container sandbox escapes or privilege escalation
- Static security gate bypasses (Bandit / eslint-plugin-security / gosec HIGH-severity gating) prior to disk commit
- Tampering with the audit hash chain (`src/audit/`) that bypasses `src/audit/checkpoint.py` git-anchored verification
- Injection or path-traversal vulnerabilities in LLM output handling
- Bypasses in the clean-room synthesis pipeline (`bootstrap/`), such as license header stamping or provenance verification
