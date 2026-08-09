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
