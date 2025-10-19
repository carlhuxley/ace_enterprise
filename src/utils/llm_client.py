"""
LLM Client - Unified interface for multiple LLM providers.
Supports Ollama, OpenAI, Anthropic, and DeepSeek.
"""
import json
import logging
import time
from typing import Any, Optional

import httpx

from src.config.settings import settings

logger = logging.getLogger(__name__)


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
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        """
        Initialize LLM client.

        Args:
            provider: LLM provider (default from settings)
            model: Model name (default from settings)
        """
        self.provider = provider or settings.default_llm_provider
        self.model = self._get_default_model(model)
        self.timeout = 600.0  # seconds (10 minutes for large local models)

        logger.info(f"Initialized LLM client: {self.provider}/{self.model}")

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
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
        elif self.provider == "openai":
            result = self._generate_openai(prompt, system_prompt, max_tokens, temperature)
        elif self.provider == "anthropic":
            result = self._generate_anthropic(prompt, system_prompt, max_tokens, temperature)
        elif self.provider == "deepseek":
            result = self._generate_deepseek(prompt, system_prompt, max_tokens, temperature)
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

    def _generate_ollama(
        self,
        prompt: str,
        system_prompt: Optional[str],
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
        system_prompt: Optional[str],
        max_tokens: Optional[int],
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
        system_prompt: Optional[str],
        max_tokens: Optional[int],
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
        system_prompt: Optional[str],
        max_tokens: Optional[int],
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

    def _get_default_model(self, model: Optional[str]) -> str:
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

        except Exception as e:
            logger.warning(f"LLM provider {self.provider} not available: {e}")
            return False

        return False
