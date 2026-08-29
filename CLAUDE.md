# Project Instructions for AI Agents

This file provides instructions and context for AI coding agents working on this project.

## Task Tracking

Use GitHub Issues for task tracking and to file follow-up work. This repo
does not ship a `.beads/` issue database — if you see references to `bd` in
old commit messages or docs, that was the maintainer's local tooling and
isn't part of this repository.

## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Open a GitHub issue for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   git push
   git status  # MUST show "up to date with origin"
   ```
4. **Clean up** - Clear stashes, prune remote branches
5. **Verify** - All changes committed AND pushed
6. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds


## Build & Test

```bash
# Install dependencies
pip install -r requirements.txt

# Install the git pre-commit hook (one-time, per clone)
cp .hooks/pre-commit .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
```

The pre-commit hook runs `generate_live_docs.py` before every commit and
auto-stages `docs/SYSTEM_ARCHITECTURE.md` so the architecture docs stay in
sync with the code. If the LLM call fails the commit still goes through.

## Architecture Overview

See [`docs/SYSTEM_ARCHITECTURE.md`](docs/SYSTEM_ARCHITECTURE.md) — generated
from the live source tree, do not edit by hand. Regenerate manually with:

```bash
.venv/bin/python generate_live_docs.py
```

[`CONTEXT.md`](CONTEXT.md) — domain glossary and architectural decisions,
kept in sync with the live source. Preserves existing definitions; adds new
concepts on each commit. Regenerate manually with:

```bash
.venv/bin/python generate_live_context.py
```

## Conventions & Patterns

### Licensing

- This repository (ACE Enterprise itself) is licensed Apache-2.0 — see `LICENSE` at repo root. Do not add or leave AGPL/copyleft headers anywhere in `src/`, `mcp_server/`, `bootstrap/`, or other project source files.
- `bootstrap/stamp.py` stamps the *synthesized clean-room output* (the separate public-repo synthesis pipeline in `bootstrap/`) with Apache-2.0 SPDX headers too, reading the LICENSE text directly from repo root as the single source of truth. When writing or refactoring code in `bootstrap/stamp.py` or anywhere that generates new TypeScript/Python files as pipeline output, default to Apache-2.0 and never emit AGPLv3 or other copyleft headers — this was previously inconsistent (stamped AGPL-3.0-only) and was corrected 2026-08-09.
