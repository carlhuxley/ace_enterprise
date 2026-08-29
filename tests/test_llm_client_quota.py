"""Tests for OpenRouter quota-exhaustion detection (ace_enterprise-wki)."""
import httpx
import pytest

from src.utils.llm_client import LLMClient, LLMQuotaExhaustedError, _is_quota_exhausted


# ---------------------------------------------------------------------------
# Unit: _is_quota_exhausted helper
# ---------------------------------------------------------------------------

def test_402_is_quota_exhausted():
    assert _is_quota_exhausted(402, "") is True


def test_401_is_quota_exhausted():
    assert _is_quota_exhausted(401, "") is True


def test_403_is_quota_exhausted():
    assert _is_quota_exhausted(403, "") is True


def test_plain_429_without_keywords_is_not_quota_exhausted():
    assert _is_quota_exhausted(429, "Too many requests, slow down") is False


def test_429_with_quota_keywords_is_quota_exhausted():
    # status 429 alone isn't in the fatal-status list; keyword match should catch it
    assert _is_quota_exhausted(429, "You have exceeded your monthly quota") is True
    assert _is_quota_exhausted(429, "insufficient credits remaining") is True


def test_500_without_keywords_is_not_quota_exhausted():
    assert _is_quota_exhausted(500, "internal server error") is False


def test_keyword_match_is_case_insensitive():
    assert _is_quota_exhausted(429, "INSUFFICIENT CREDIT") is True


# ---------------------------------------------------------------------------
# Integration: _generate_openrouter wiring (real httpx.Client via MockTransport)
# ---------------------------------------------------------------------------

_REAL_HTTPX_CLIENT = httpx.Client  # captured before any monkeypatching


def _client_with_mock_transport(monkeypatch, handler):
    """Patch httpx.Client so _generate_openrouter's `with httpx.Client(...)` uses
    a MockTransport instead of hitting the network."""
    def factory(*args, **kwargs):
        return _REAL_HTTPX_CLIENT(transport=httpx.MockTransport(handler), timeout=kwargs.get("timeout", 5))

    monkeypatch.setattr("src.utils.llm_client.httpx.Client", factory)


@pytest.fixture
def llm(monkeypatch):
    monkeypatch.setattr("src.utils.llm_client.settings.openrouter_api_key", "test-key")
    return LLMClient(provider="openrouter", model="anthropic/claude-haiku-4-5")


def test_402_response_raises_quota_exhausted_immediately(monkeypatch, llm):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(402, json={"error": {"message": "Insufficient credits"}})

    _client_with_mock_transport(monkeypatch, handler)

    with pytest.raises(LLMQuotaExhaustedError):
        llm.generate("hello")

    # No retries for a quota error — one call, not three.
    assert len(calls) == 1


def test_429_with_quota_keywords_raises_without_retry(monkeypatch, llm):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            429, json={"error": {"message": "You have exceeded your quota, add credits to continue"}}
        )

    _client_with_mock_transport(monkeypatch, handler)

    with pytest.raises(LLMQuotaExhaustedError):
        llm.generate("hello")

    assert len(calls) == 1


def test_plain_429_still_retries_and_raises_generic_runtime_error(monkeypatch, llm):
    monkeypatch.setattr("src.utils.llm_client.time.sleep", lambda *_: None)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, json={"error": {"message": "rate limited"}})

    _client_with_mock_transport(monkeypatch, handler)

    with pytest.raises(RuntimeError) as excinfo:
        llm.generate("hello")

    assert not isinstance(excinfo.value, LLMQuotaExhaustedError)
    assert len(calls) == 3  # exhausted all retries, not fast-failed


# ---------------------------------------------------------------------------
# Regression: reasoning-capable models (DeepSeek etc.) can burn max_tokens on
# internal reasoning and return content=None -- confirmed live against
# deepseek/deepseek-v4-flash via OpenRouter, even for a trivial prompt.
# ---------------------------------------------------------------------------

def test_payload_disables_reasoning(monkeypatch, llm):
    """reasoning: {exclude: true} must be sent so max_tokens isn't spent on
    <reasoning> content nothing in this codebase ever consumes."""
    captured = {}

    def handler(request):
        import json
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={
            "model": "anthropic/claude-haiku-4-5",
            "choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        })

    _client_with_mock_transport(monkeypatch, handler)
    llm.generate("hello")

    assert captured["payload"]["reasoning"] == {"exclude": True}


def test_none_content_from_reasoning_exhaustion_reports_finish_reason(monkeypatch, llm):
    """Previously: content=None set no diagnostic at all, so the final
    RuntimeError read 'Last error: None' -- useless for debugging. Now the
    finish_reason (e.g. "length" for reasoning-token exhaustion) surfaces."""
    def handler(request):
        return httpx.Response(200, json={
            "model": "anthropic/claude-haiku-4-5",
            "choices": [{"message": {"content": None, "reasoning": "thinking..."}, "finish_reason": "length"}],
            "usage": {},
        })

    _client_with_mock_transport(monkeypatch, handler)

    with pytest.raises(RuntimeError) as excinfo:
        llm.generate("hello")

    assert "Last error: None" not in str(excinfo.value)
    assert "finish_reason=length" in str(excinfo.value)


def test_none_content_retries_same_model_before_giving_up(monkeypatch, llm):
    """Found live against qwen/qwen3-coder-30b-a3b-instruct: ~18% of Arm 1
    calls in a 5-run, 30-task benchmark returned content=None despite
    reasoning:{exclude:true}, and the old code gave up after a single
    occurrence -- burning none of the retry budget every other transient
    failure mode (429, 5xx) here gets, even though the very next call to
    the same model routinely succeeds."""
    monkeypatch.setattr("src.utils.llm_client.time.sleep", lambda *_: None)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={
            "model": "anthropic/claude-haiku-4-5",
            "choices": [{"message": {"content": None}, "finish_reason": "stop"}],
            "usage": {},
        })

    _client_with_mock_transport(monkeypatch, handler)

    with pytest.raises(RuntimeError):
        llm.generate("hello")

    assert len(calls) == 3, "must exhaust all retries on the same model, not give up after one"


def test_none_content_then_success_recovers_on_retry(monkeypatch, llm):
    """The actual point of the fix: a transient empty completion followed
    by a real response on the next attempt must succeed, not surface as a
    failed call."""
    monkeypatch.setattr("src.utils.llm_client.time.sleep", lambda *_: None)
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, json={
                "model": "anthropic/claude-haiku-4-5",
                "choices": [{"message": {"content": None}, "finish_reason": "stop"}],
                "usage": {},
            })
        return httpx.Response(200, json={
            "model": "anthropic/claude-haiku-4-5",
            "choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        })

    _client_with_mock_transport(monkeypatch, handler)

    result = llm.generate("hello")

    assert result["content"] == "hi"
    assert len(calls) == 2
