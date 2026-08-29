"""ClaudeCliClient — LLM client backed by the local 'claude -p' CLI.

Replaces HTTP API calls (OpenRouter / Anthropic) with a subprocess call to the
Claude Code CLI that is already authenticated on the host machine.

Architecture contract:
  Host  → claude -p "prompt"  → synthesised text written to /dev/shm workspace
  Container → podman exec vitest run → pass / fail returned to host

The container remains a pure execution sandbox with --network none.
No API keys, no external billing — uses the active Claude Code session.

--tools "" is load-bearing, not cosmetic: `claude --print` without it runs a
full agentic session with tool access (Write/Bash/...), not a text
completion. Confirmed live -- omitting it, the CLI tried to invoke its own
Write tool against the host filesystem for a prompt asking it to "output"
test code, hit the non-interactive permission prompt, and returned the
refusal text as the "generated code". Every LLM call in this codebase must
stay a pure text completion; --tools "" is what actually enforces that.

--strict-mcp-config is the same fix for a second attack surface: --tools ""
only disables the CLI's *built-in* tool set (Write/Bash/...) -- it says
nothing about MCP servers. On a host where this repo's own MCP server
(mcp_server/) is registered in the ambient claude config, a nested
`claude --print` call still discovers and can attempt to call its
`build_feature` tool, hit the same non-interactive permission wall, and
leak the refusal text as "generated code" (reproduced live: a TypeScript
polyglot e2e run got "I need permission to run `build_feature`..." embedded
verbatim inside add.test.ts). --strict-mcp-config with no --mcp-config
value means zero MCP servers are loaded, regardless of what's configured
on the host running the tests.

--setting-sources "" closes the third leak in the same family: project/
local settings.json can define hooks (e.g. this very repo's SessionStart
hook) that inject text into every nested session's context regardless of
--tools/--strict-mcp-config, since hooks aren't tools. Confirmed live --
without this flag, a nested call echoed back a paragraph about this
repo's SessionStart hook instead of a clean completion. --bare would also
suppress hooks but was rejected: its help text states it restricts auth to
ANTHROPIC_API_KEY/apiKeyHelper and never reads OAuth/keychain, which
breaks this class's whole premise of reusing the host's already-
authenticated Claude Code session with no API key. --setting-sources ""
skips project/local hooks (and CLAUDE.md/permissions) while leaving auth
untouched.

_NO_TOOLS_SYSTEM_PROMPT is a fourth, different-shaped leak in the same
family, found live running the bootstrap TS synthesis pipeline: even with
tools/MCP/hooks all disabled above, Claude's own training still has it
reach for exploration ("let me check the existing test/impl files
first") before answering. With nowhere to actually run that tool call, it
narrates the attempt as text instead -- literal JSON like
{"command":"ls ../ace-enterprise-oss/...","description":"..."} or
markdown like "**Bash** `find ...`" -- which then gets parsed as if it
were the requested scenario/code and fails (0/20 modules synthesised
successfully in the run that surfaced this; every failure traced back to
this pattern, confirmed by ~7.5 "parse error"/"could not parse scenario"
log lines per failed module). --tools "" stops it from actually running a
tool; this stops it from trying to in the first place, by telling it
up front there's nothing to reach for. Always prepended to whatever
system_prompt the caller supplies (or sent alone if none is given) --
this constraint is true for every ClaudeCliClient call, not specific to
one caller, so it belongs here rather than in each prompt-building site.

generate()'s retry loop is hardening against a fifth failure class, this
one at the subprocess/process level rather than in the response content:
the local `claude` binary is nvm-managed and self-updates in place, which
opens a few-second window where `subprocess.run(["claude", ...])` raises
FileNotFoundError (confirmed live, killed one bootstrap run). Separately,
`claude --print` calls have also failed with a bare "exit 1" and empty
stderr under sustained load (confirmed live, twice, each time taking out
most of the remaining modules in a long bootstrap batch run -- 85+ modules
in one case). Both are transient and self-clear; retrying a few calls
costs seconds, but not retrying costs the rest of a run. Scoped to the
client for the same reason as everything above: this is a property of the
CLI mechanism itself, not of what any particular caller asked for, so
every caller (IncrementalPlanner/IterativeTDDRunner included, without
touching either) gets the resilience automatically. Timeouts are
deliberately NOT retried -- a slow/hung call needs a different response
than "try again immediately", and retrying would just compound the delay.
"""
import logging
import os
import subprocess
import time
from typing import Any

logger = logging.getLogger(__name__)

_NO_TOOLS_SYSTEM_PROMPT = (
    "CRITICAL: You have NO file system access, terminal access, or tools "
    "available in this session. Do NOT output tool calls, JSON commands, "
    "bash snippets, or narration about what you would inspect or run. "
    "Emit ONLY the raw content requested (code, Gherkin, JSON, etc.) and "
    "nothing else."
)

_MAX_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 3.0


class ClaudeCliClient:
    """Drop-in replacement for LLMClient using the local claude CLI.

    Returns dicts in the same shape as LLMClient.generate() so WorkerAgent,
    TypeScriptWorkerAgent, IncrementalPlanner, Reflector, Curator, and
    extract.py need no changes. max_tokens is accepted for interface
    compatibility but not enforceable via the CLI, so it's ignored.
    """

    def __init__(self, timeout: int = 300) -> None:
        self._timeout = timeout
        # No API model string is selectable via the CLI (it uses whatever the
        # authenticated Claude Code session is configured for) -- this is a
        # stable identity label, not a real model version.
        self.model = "claude-cli"

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """Run claude -p with prompt, return {"content": <response>}."""
        # Strip CLAUDE* vars so the subprocess doesn't detect a nested session
        # and refuse to run (CLAUDECODE=1 causes exit 1 when nested).
        env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
        cmd = [
            "claude", "--print", "--output-format", "text",
            "--tools", "", "--strict-mcp-config", "--setting-sources", "",
        ]
        combined_system_prompt = (
            f"{_NO_TOOLS_SYSTEM_PROMPT}\n\n{system_prompt}" if system_prompt else _NO_TOOLS_SYSTEM_PROMPT
        )
        cmd += ["--system-prompt", combined_system_prompt]
        cmd += ["--", prompt]

        result = None
        last_error: Exception | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self._timeout,
                    env=env,
                )
            except OSError as exc:
                # e.g. FileNotFoundError during a claude-CLI self-update race.
                last_error = exc
                result = None
            else:
                if result.returncode == 0:
                    break
                last_error = RuntimeError(
                    f"claude CLI error (exit {result.returncode}): {result.stderr.strip()}"
                )
                result = None

            if attempt < _MAX_ATTEMPTS:
                logger.warning(
                    f"claude CLI call failed (attempt {attempt}/{_MAX_ATTEMPTS}): "
                    f"{last_error} -- retrying"
                )
                time.sleep(_RETRY_DELAY_SECONDS)

        if result is None:
            raise RuntimeError(
                f"claude CLI failed after {_MAX_ATTEMPTS} attempts: {last_error}"
            ) from last_error

        return {
            "content": result.stdout.strip(),
            # Token counts are unavailable from the CLI — callers treat 0 as absent
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "tokens_used": 0,
            # Matches LLMClient's OpenRouter response shape (actual_model/
            # requested_model/provider) so callers that thread model
            # attribution through experiment logging don't need a
            # client-type branch. "claude-cli" is a stable identity label,
            # not a real model version -- see self.model above.
            "actual_model": self.model,
            "requested_model": self.model,
            "provider": "claude-cli",
        }
