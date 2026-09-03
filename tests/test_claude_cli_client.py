"""Tests for ClaudeCliClient's generate() signature.

Reflector/Curator call llm_client.generate(prompt=, system_prompt=,
temperature=) -- ClaudeCliClient used to only accept prompt/temperature,
so using it (the no-API-key default) for those components raised TypeError.
"""
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from src.utils.claude_cli_client import _NO_TOOLS_SYSTEM_PROMPT, ClaudeCliClient


def _fake_completed_process(stdout="ok", returncode=0, stderr=""):
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


class TestGenerateSignature:
    def test_accepts_system_prompt_kwarg(self):
        client = ClaudeCliClient()
        with patch("subprocess.run", return_value=_fake_completed_process()) as run:
            client.generate(prompt="hi", system_prompt="be terse", temperature=0.3)
        assert run.called

    def test_accepts_max_tokens_kwarg(self):
        client = ClaudeCliClient()
        with patch("subprocess.run", return_value=_fake_completed_process()) as run:
            client.generate(prompt="hi", max_tokens=500)
        assert run.called

    def test_system_prompt_passed_to_cli_flag(self):
        client = ClaudeCliClient()
        with patch("subprocess.run", return_value=_fake_completed_process()) as run:
            client.generate(prompt="hi", system_prompt="be terse")
        cmd = run.call_args.args[0]
        assert "--system-prompt" in cmd
        sent = cmd[cmd.index("--system-prompt") + 1]
        assert sent.endswith("be terse")

    def test_no_system_prompt_still_sends_flag(self):
        """--system-prompt is now always sent -- see TestNoToolsConstraint
        for why (it always carries at least the no-tools guard)."""
        client = ClaudeCliClient()
        with patch("subprocess.run", return_value=_fake_completed_process()) as run:
            client.generate(prompt="hi")
        cmd = run.call_args.args[0]
        assert "--system-prompt" in cmd

    def test_prompt_is_last_positional_arg(self):
        client = ClaudeCliClient()
        with patch("subprocess.run", return_value=_fake_completed_process()) as run:
            client.generate(prompt="hi there", system_prompt="be terse")
        cmd = run.call_args.args[0]
        assert cmd[-1] == "hi there"

    def test_reflector_style_call_does_not_raise(self):
        # Exact call shape Reflector.reflect()/Curator.curate() use.
        client = ClaudeCliClient()
        with patch("subprocess.run", return_value=_fake_completed_process()):
            result = client.generate(
                prompt="analyse this", system_prompt="you are a reflector", temperature=0.3,
            )
        assert result["content"] == "ok"


class TestToolsDisabled:
    """--tools "" is load-bearing: without it, `claude --print` runs a full
    agentic session with tool access instead of a text completion -- see
    module docstring for the live repro (it tried to Write to the host)."""

    def test_tools_flag_present_and_empty(self):
        client = ClaudeCliClient()
        with patch("subprocess.run", return_value=_fake_completed_process()) as run:
            client.generate(prompt="hi")
        cmd = run.call_args.args[0]
        assert "--tools" in cmd
        assert cmd[cmd.index("--tools") + 1] == ""

    def test_double_dash_separates_flags_from_prompt(self):
        # Prevents a prompt that happens to start with "-" from being
        # parsed as a CLI flag.
        client = ClaudeCliClient()
        with patch("subprocess.run", return_value=_fake_completed_process()) as run:
            client.generate(prompt="-rf everything")
        cmd = run.call_args.args[0]
        assert "--" in cmd
        assert cmd[cmd.index("--") + 1] == "-rf everything"
        assert cmd[-1] == "-rf everything"


class TestModelAttribution:
    """generate() must report actual_model/requested_model/provider like
    LLMClient's OpenRouter response does, so callers threading model
    attribution into experiment logging (TDDCycleRunner._log()) don't need
    a client-type branch."""

    def test_reports_model_and_provider(self):
        client = ClaudeCliClient()
        with patch("subprocess.run", return_value=_fake_completed_process()):
            result = client.generate(prompt="hi")
        assert result["actual_model"] == "claude-cli"
        assert result["requested_model"] == "claude-cli"
        assert result["provider"] == "claude-cli"


class TestNoToolsConstraint:
    """Even with --tools ""/--strict-mcp-config/--setting-sources "" all
    disabled, Claude's own training still reaches for exploration ("let me
    check the existing files first") before answering -- with nothing to
    actually run, it narrates the attempted tool call as text instead of
    emitting the requested content, which then fails to parse downstream.
    Reproduced live running the bootstrap TS synthesis pipeline: 0/20
    modules synthesised successfully, every failure traced back to this.
    _NO_TOOLS_SYSTEM_PROMPT heads off the instinct by stating up front
    there's nothing to explore with."""

    def test_no_tools_constraint_present_with_no_caller_system_prompt(self):
        client = ClaudeCliClient()
        with patch("subprocess.run", return_value=_fake_completed_process()) as run:
            client.generate(prompt="hi")
        cmd = run.call_args.args[0]
        sent = cmd[cmd.index("--system-prompt") + 1]
        assert sent == _NO_TOOLS_SYSTEM_PROMPT

    def test_no_tools_constraint_prepended_to_caller_system_prompt(self):
        client = ClaudeCliClient()
        with patch("subprocess.run", return_value=_fake_completed_process()) as run:
            client.generate(prompt="hi", system_prompt="you are a reflector")
        cmd = run.call_args.args[0]
        sent = cmd[cmd.index("--system-prompt") + 1]
        assert sent.startswith(_NO_TOOLS_SYSTEM_PROMPT)
        assert sent.endswith("you are a reflector")


class TestMcpAndSettingsIsolation:
    """--tools "" only disables the CLI's built-in tools -- it says nothing
    about MCP servers or project/local hooks. Without --strict-mcp-config,
    a nested call on a host with this repo's own MCP server registered can
    discover and attempt to call its `build_feature` tool; without
    --setting-sources "", a nested call picks up this repo's SessionStart
    hook output. Both were reproduced live as text leaking into what must
    stay a pure completion -- see module docstring."""

    def test_strict_mcp_config_flag_present(self):
        client = ClaudeCliClient()
        with patch("subprocess.run", return_value=_fake_completed_process()) as run:
            client.generate(prompt="hi")
        cmd = run.call_args.args[0]
        assert "--strict-mcp-config" in cmd

    def test_setting_sources_flag_present_and_empty(self):
        client = ClaudeCliClient()
        with patch("subprocess.run", return_value=_fake_completed_process()) as run:
            client.generate(prompt="hi")
        cmd = run.call_args.args[0]
        assert "--setting-sources" in cmd
        assert cmd[cmd.index("--setting-sources") + 1] == ""


class TestRetryHardening:
    """Two failure classes confirmed live, both transient and self-clearing:
    the local `claude` binary self-updates in place (subprocess.run raises
    FileNotFoundError for a few seconds), and `claude --print` has failed
    with a bare exit 1 and empty stderr under sustained load. Both killed a
    real bootstrap run before this existed -- one FileNotFoundError crash,
    and one "exit 1" epidemic that took out 85+ of the remaining modules in
    a long batch run. Retrying costs seconds; not retrying costs the rest
    of a run."""

    def test_transient_oserror_retries_then_succeeds(self):
        client = ClaudeCliClient()
        with patch("subprocess.run") as run, patch("src.utils.claude_cli_client.time.sleep") as sleep:
            run.side_effect = [
                FileNotFoundError(2, "No such file or directory", "claude"),
                _fake_completed_process(stdout="ok"),
            ]
            result = client.generate(prompt="hi")
        assert result["content"] == "ok"
        assert run.call_count == 2
        sleep.assert_called_once()

    def test_transient_nonzero_exit_retries_then_succeeds(self):
        client = ClaudeCliClient()
        with patch("subprocess.run") as run, patch("src.utils.claude_cli_client.time.sleep"):
            run.side_effect = [
                _fake_completed_process(returncode=1, stderr=""),
                _fake_completed_process(stdout="ok"),
            ]
            result = client.generate(prompt="hi")
        assert result["content"] == "ok"
        assert run.call_count == 2

    def test_persistent_failure_raises_after_max_attempts(self):
        client = ClaudeCliClient()
        with patch("subprocess.run") as run, patch("src.utils.claude_cli_client.time.sleep"):
            run.side_effect = FileNotFoundError(2, "No such file or directory", "claude")
            with pytest.raises(RuntimeError, match="claude CLI failed after"):
                client.generate(prompt="hi")
        assert run.call_count == 3  # _MAX_ATTEMPTS, no more

    def test_timeout_is_not_retried(self):
        """A slow/hung call needs a different response than "try again
        immediately" -- retrying would just compound the delay."""
        client = ClaudeCliClient()
        with patch("subprocess.run") as run, patch("src.utils.claude_cli_client.time.sleep") as sleep:
            run.side_effect = subprocess.TimeoutExpired(cmd=["claude"], timeout=300)
            with pytest.raises(subprocess.TimeoutExpired):
                client.generate(prompt="hi")
        assert run.call_count == 1
        sleep.assert_not_called()

    def test_success_on_first_attempt_does_not_sleep(self):
        client = ClaudeCliClient()
        with patch("subprocess.run", return_value=_fake_completed_process()) as run, \
                patch("src.utils.claude_cli_client.time.sleep") as sleep:
            client.generate(prompt="hi")
        assert run.call_count == 1
        sleep.assert_not_called()


class TestModelSelection:
    def test_no_model_omits_the_model_flag(self):
        client = ClaudeCliClient()
        assert client.model == "claude-cli"
        assert client.provider == "claude-cli"
        with patch("subprocess.run", return_value=_fake_completed_process()) as run:
            client.generate(prompt="hi")
        assert "--model" not in run.call_args.args[0]

    def test_model_is_passed_to_the_cli(self):
        client = ClaudeCliClient(model="haiku")
        assert client.model == "claude-cli:haiku"
        with patch("subprocess.run", return_value=_fake_completed_process()) as run:
            client.generate(prompt="hi")
        cmd = run.call_args.args[0]
        assert cmd[cmd.index("--model") + 1] == "haiku"

    def test_response_carries_the_model_label(self):
        client = ClaudeCliClient(model="sonnet")
        with patch("subprocess.run", return_value=_fake_completed_process()):
            result = client.generate(prompt="hi")
        assert result["actual_model"] == "claude-cli:sonnet"
        assert result["provider"] == "claude-cli"
