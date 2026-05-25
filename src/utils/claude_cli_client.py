"""ClaudeCliClient — LLM client backed by the local 'claude -p' CLI.

Replaces HTTP API calls (OpenRouter / Anthropic) with a subprocess call to the
Claude Code CLI that is already authenticated on the host machine.

Architecture contract:
  Host  → claude -p "prompt"  → synthesised text written to /dev/shm workspace
  Container → podman exec vitest run → pass / fail returned to host

The container remains a pure execution sandbox with --network none.
No API keys, no external billing — uses the active Claude Code session.
"""
import subprocess
from typing import Any


class ClaudeCliClient:
    """Drop-in replacement for LLMClient using the local claude CLI.

    Returns dicts in the same shape as LLMClient.generate() so WorkerAgent,
    TypeScriptWorkerAgent, IncrementalPlanner, and extract.py need no changes.
    """

    def __init__(self, timeout: int = 120) -> None:
        self._timeout = timeout

    def generate(self, prompt: str, temperature: float = 0.0) -> dict[str, Any]:
        """Run claude -p with prompt, return {"content": <response>}."""
        result = subprocess.run(
            ["claude", "--print", "--output-format", "text", prompt],
            capture_output=True,
            text=True,
            timeout=self._timeout,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            raise RuntimeError(f"claude CLI error (exit {result.returncode}): {stderr}")

        return {
            "content": result.stdout.strip(),
            # Token counts are unavailable from the CLI — callers treat 0 as absent
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "tokens_used": 0,
        }
