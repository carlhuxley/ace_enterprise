"""
LLM Client - Unified interface for open-source LLM providers.
Supports Ollama, vLLM, DeepSeek, and Together AI.
"""
import logging
import time
from typing import Any

import httpx

from src.config.settings import settings

logger = logging.getLogger(__name__)

# Cache for OpenRouter free models (populated on first use)
_openrouter_free_models_cache: list[str] | None = None
_openrouter_cache_time: float = 0
_OPENROUTER_CACHE_TTL = 3600  # 1 hour cache TTL


def _fetch_openrouter_free_models() -> list[str]:
    """Fetch list of free models from OpenRouter API."""
    global _openrouter_free_models_cache, _openrouter_cache_time

    # Return cached result if still valid
    if _openrouter_free_models_cache is not None:
        if time.time() - _openrouter_cache_time < _OPENROUTER_CACHE_TTL:
            return _openrouter_free_models_cache

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get("https://openrouter.ai/api/v1/models")
            response.raise_for_status()
            data = response.json()

        free_models = []
        for model in data.get("data", []):
            pricing = model.get("pricing", {})
            # Free models have prompt price of "0"
            if pricing.get("prompt") == "0":
                free_models.append(model["id"])

        # Sort by context length (prefer larger context) if available
        _openrouter_free_models_cache = free_models
        _openrouter_cache_time = time.time()

        logger.info(f"OpenRouter: cached {len(free_models)} free models")
        return free_models

    except Exception as e:
        logger.warning(f"Failed to fetch OpenRouter models: {e}")
        # Return cached result even if expired, or empty list
        return _openrouter_free_models_cache or []


class LLMClient:
    """
    Unified LLM client supporting multiple providers.

    Providers:
    - Ollama (local)
    - OpenAI
    - Anthropic
    - DeepSeek
    """

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        """
        Initialize LLM client.

        Args:
            provider: LLM provider (default from settings)
            model: Model name (default from settings)
            base_url: Custom base URL for vLLM endpoints (optional)
        """
        self.provider = provider or settings.default_llm_provider
        self.model = self._get_default_model(model)
        self.base_url = base_url  # For vLLM custom endpoints
        self.timeout = 600.0  # seconds (10 minutes for large local models)

        logger.info(f"Initialized LLM client: {self.provider}/{self.model}")

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> dict[str, Any]:
        """
        Generate completion from LLM.

        Args:
            prompt: User prompt
            system_prompt: System prompt (optional)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0-1)

        Returns:
            Dictionary with:
            - content: Generated text
            - tokens_used: Total tokens consumed
            - latency_ms: Generation time in milliseconds
            - model: Model used
        """
        start_time = time.time()

        if self.provider == "ollama":
            result = self._generate_ollama(prompt, system_prompt, temperature)
        elif self.provider == "vllm":
            result = self._generate_vllm(prompt, system_prompt, max_tokens, temperature)
        elif self.provider == "openai":
            result = self._generate_openai(prompt, system_prompt, max_tokens, temperature)
        elif self.provider == "anthropic":
            result = self._generate_anthropic(prompt, system_prompt, max_tokens, temperature)
        elif self.provider == "deepseek":
            result = self._generate_deepseek(prompt, system_prompt, max_tokens, temperature)
        elif self.provider == "togetherai":
            result = self._generate_togetherai(prompt, system_prompt, max_tokens, temperature)
        elif self.provider == "openrouter":
            result = self._generate_openrouter(prompt, system_prompt, max_tokens, temperature)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

        latency_ms = int((time.time() - start_time) * 1000)
        result["latency_ms"] = latency_ms
        result["model"] = self.model

        logger.debug(
            f"Generated {result['tokens_used']} tokens in {latency_ms}ms "
            f"using {self.provider}/{self.model}"
        )

        return result

    def _generate_vllm(
        self,
        prompt: str,
        system_prompt: str | None,
        max_tokens: int | None,
        temperature: float,
    ) -> dict[str, Any]:
        """Generate using vLLM API (OpenAI-compatible)."""
        if not self.base_url:
            raise ValueError("vLLM provider requires base_url to be specified")

        url = f"{self.base_url}/v1/completions"

        # Combine system prompt with user prompt if provided
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "max_tokens": max_tokens or 1024,
            "temperature": temperature,
        }

        try:
            timeout = httpx.Timeout(timeout=self.timeout, connect=60.0)
            with httpx.Client(timeout=timeout) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()

            return {
                "content": data["choices"][0]["text"],
                "tokens_used": data["usage"]["total_tokens"],
            }

        except httpx.TimeoutException as e:
            logger.error(f"vLLM API timeout after {self.timeout}s: {e}")
            raise RuntimeError(f"vLLM timeout: {e}")
        except httpx.HTTPError as e:
            logger.error(f"vLLM API error: {e}")
            raise RuntimeError(f"Failed to generate with vLLM: {e}")

    def _generate_ollama(
        self,
        prompt: str,
        system_prompt: str | None,
        temperature: float,
    ) -> dict[str, Any]:
        """Generate using Ollama API."""
        url = f"{settings.ollama_base_url}/api/generate"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }

        if system_prompt:
            payload["system"] = system_prompt

        try:
            # Use explicit timeout with connect and read timeouts
            timeout = httpx.Timeout(timeout=self.timeout, connect=60.0)
            with httpx.Client(timeout=timeout) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()

            return {
                "content": data.get("response", ""),
                "tokens_used": data.get("eval_count", 0) + data.get("prompt_eval_count", 0),
            }

        except httpx.TimeoutException as e:
            logger.error(f"Ollama API timeout after {self.timeout}s: {e}")
            raise RuntimeError(f"Ollama timeout - model may be too slow on this hardware: {e}")
        except httpx.HTTPError as e:
            logger.error(f"Ollama API error: {e}")
            raise RuntimeError(f"Failed to generate with Ollama: {e}")

    def _generate_openai(
        self,
        prompt: str,
        system_prompt: str | None,
        max_tokens: int | None,
        temperature: float,
    ) -> dict[str, Any]:
        """Generate using OpenAI API."""
        if not settings.openai_api_key:
            raise ValueError("OpenAI API key not configured")

        # Using httpx directly (can be replaced with openai library)
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        }

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()

            return {
                "content": data["choices"][0]["message"]["content"],
                "tokens_used": data["usage"]["total_tokens"],
            }

        except httpx.HTTPError as e:
            logger.error(f"OpenAI API error: {e}")
            raise RuntimeError(f"Failed to generate with OpenAI: {e}")

    def _generate_anthropic(
        self,
        prompt: str,
        system_prompt: str | None,
        max_tokens: int | None,
        temperature: float,
    ) -> dict[str, Any]:
        """Generate using Anthropic API."""
        if not settings.anthropic_api_key:
            raise ValueError("Anthropic API key not configured")

        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens or 4096,
        }

        if system_prompt:
            payload["system"] = system_prompt

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()

            return {
                "content": data["content"][0]["text"],
                "tokens_used": data["usage"]["input_tokens"] + data["usage"]["output_tokens"],
            }

        except httpx.HTTPError as e:
            logger.error(f"Anthropic API error: {e}")
            raise RuntimeError(f"Failed to generate with Anthropic: {e}")

    def _generate_deepseek(
        self,
        prompt: str,
        system_prompt: str | None,
        max_tokens: int | None,
        temperature: float,
    ) -> dict[str, Any]:
        """Generate using DeepSeek API."""
        if not settings.deepseek_api_key:
            raise ValueError("DeepSeek API key not configured")

        # DeepSeek uses OpenAI-compatible API
        url = "https://api.deepseek.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.deepseek_api_key}",
            "Content-Type": "application/json",
        }

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()

            return {
                "content": data["choices"][0]["message"]["content"],
                "tokens_used": data["usage"]["total_tokens"],
            }

        except httpx.HTTPError as e:
            logger.error(f"DeepSeek API error: {e}")
            raise RuntimeError(f"Failed to generate with DeepSeek: {e}")

    def _generate_togetherai(
        self,
        prompt: str,
        system_prompt: str | None,
        max_tokens: int | None,
        temperature: float,
    ) -> dict[str, Any]:
        """Generate using Together AI API (open-source models)."""
        if not settings.togetherai_api_key:
            raise ValueError("Together AI API key not configured")

        # Together AI uses OpenAI-compatible API
        url = "https://api.together.ai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.togetherai_api_key}",
            "Content-Type": "application/json",
        }

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()

            return {
                "content": data["choices"][0]["message"]["content"],
                "tokens_used": data["usage"]["total_tokens"],
            }

        except httpx.HTTPError as e:
            logger.error(f"Together AI API error: {e}")
            raise RuntimeError(f"Failed to generate with Together AI: {e}")

    def _generate_openrouter(
        self,
        prompt: str,
        system_prompt: str | None,
        max_tokens: int | None,
        temperature: float,
    ) -> dict[str, Any]:
        """Generate using OpenRouter API (access to many models including free tiers)."""
        if not settings.openrouter_api_key:
            raise ValueError("OpenRouter API key not configured")

        # Build list of models to try (primary + fallbacks)
        models_to_try = [self.model]
        if self.model.endswith(":free"):
            # Fetch available free models dynamically and add as fallbacks
            free_models = _fetch_openrouter_free_models()
            models_to_try.extend([m for m in free_models if m != self.model])

        # OpenRouter uses OpenAI-compatible API
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/carlhuxley/ace_enterprise",  # Required by OpenRouter
            "X-Title": "ACE Enterprise",
        }

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        last_error = None

        for model in models_to_try:
            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens or 4096,  # OpenRouter requires explicit max_tokens
            }

            # Retry logic with exponential backoff for rate limits
            max_retries = 3
            base_delay = 1.0  # seconds

            for attempt in range(max_retries):
                try:
                    with httpx.Client(timeout=self.timeout) as client:
                        response = client.post(url, headers=headers, json=payload)
                        response.raise_for_status()
                        data = response.json()

                    # OpenRouter returns actual model used (important for auto-routing)
                    actual_model = data.get("model", model)

                    if model != self.model:
                        logger.info(f"OpenRouter: using fallback model {model} (requested: {self.model})")

                    return {
                        "content": data["choices"][0]["message"]["content"],
                        "tokens_used": data.get("usage", {}).get("total_tokens", 0),
                        "actual_model": actual_model,  # The model that actually served the request
                        "requested_model": self.model,  # The originally requested model
                        "provider": data.get("provider", "unknown"),
                    }

                except httpx.HTTPStatusError as e:
                    last_error = e
                    status_code = e.response.status_code

                    # Handle rate limiting with retry
                    if status_code == 429:
                        if attempt < max_retries - 1:
                            # Check for Retry-After header
                            retry_after = e.response.headers.get("Retry-After")
                            if retry_after:
                                delay = float(retry_after)
                            else:
                                # Exponential backoff: 1s, 2s, 4s
                                delay = base_delay * (2 ** attempt)

                            logger.warning(
                                f"OpenRouter rate limited for {model} (429), retrying in {delay}s "
                                f"(attempt {attempt + 1}/{max_retries})"
                            )
                            time.sleep(delay)
                            continue
                        else:
                            # Max retries exhausted for this model, try next fallback
                            logger.warning(f"OpenRouter: {model} rate limited after {max_retries} retries, trying fallback")
                            break

                    # Handle model not found - try next fallback
                    elif status_code == 404:
                        logger.warning(f"OpenRouter: model {model} not found (404), trying fallback")
                        break

                    # Handle server errors with retry
                    elif status_code >= 500:
                        if attempt < max_retries - 1:
                            delay = base_delay * (2 ** attempt)
                            logger.warning(
                                f"OpenRouter server error for {model} ({status_code}), retrying in {delay}s "
                                f"(attempt {attempt + 1}/{max_retries})"
                            )
                            time.sleep(delay)
                            continue
                        else:
                            logger.warning(f"OpenRouter: {model} server errors after {max_retries} retries, trying fallback")
                            break

                    else:
                        # Non-retryable HTTP error (4xx except 429 and 404)
                        logger.error(f"OpenRouter API error for {model}: {e}")
                        logger.error(f"Response: {e.response.text}")
                        raise RuntimeError(f"Failed to generate with OpenRouter: {e}")

                except httpx.TimeoutException as e:
                    logger.error(f"OpenRouter timeout for {model}: {e}")
                    last_error = e
                    break  # Try next model

                except httpx.HTTPError as e:
                    logger.error(f"OpenRouter API error for {model}: {e}")
                    last_error = e
                    raise RuntimeError(f"Failed to generate with OpenRouter: {e}")

        # All models exhausted
        raise RuntimeError(
            f"OpenRouter: all models rate limited or unavailable. "
            f"Last error: {last_error}"
        )

    def _get_default_model(self, model: str | None) -> str:
        """Get default model for provider."""
        if model:
            return model

        if self.provider == "ollama":
            return settings.ollama_default_model
        elif self.provider == "openai":
            return settings.openai_default_model
        elif self.provider == "anthropic":
            return settings.anthropic_default_model
        elif self.provider == "deepseek":
            return settings.deepseek_default_model
        elif self.provider == "togetherai":
            return settings.togetherai_default_model
        elif self.provider == "openrouter":
            return settings.openrouter_default_model
        else:
            return "unknown"

    def check_availability(self) -> bool:
        """
        Check if the LLM provider is available.

        Returns:
            True if provider is reachable and working
        """
        try:
            if self.provider == "ollama":
                url = f"{settings.ollama_base_url}/api/tags"
                with httpx.Client(timeout=5.0) as client:
                    response = client.get(url)
                    response.raise_for_status()
                return True
            else:
                # For API providers, just check if API key is configured
                if self.provider == "openai":
                    return bool(settings.openai_api_key)
                elif self.provider == "anthropic":
                    return bool(settings.anthropic_api_key)
                elif self.provider == "deepseek":
                    return bool(settings.deepseek_api_key)
                elif self.provider == "togetherai":
                    return bool(settings.togetherai_api_key)
                elif self.provider == "openrouter":
                    return bool(settings.openrouter_api_key)

        except Exception as e:
            logger.warning(f"LLM provider {self.provider} not available: {e}")
            return False

        return False
