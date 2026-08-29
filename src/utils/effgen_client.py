"""
effGen LLM Client - Adapter to use effGen local models with LLMClient interface.

This allows WorkerAgent and other components to use local effGen
models (like Qwen 2.5 1.5B) instead of external APIs.

Bead: ace_enterprise-41e
"""
import base64
import logging
import subprocess
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class EffGenClient:
    """
    LLM client adapter for effGen local models.

    Implements the same interface as LLMClient but runs inference
    locally via effGen framework.

    Usage:
        client = EffGenClient(model="Qwen/Qwen2.5-1.5B-Instruct")
        result = client.generate("Write a function that adds two numbers")
        print(result["content"])
    """

    def __init__(
        self,
        model: str = "Qwen/Qwen2.5-1.5B-Instruct",
        quantization: str = "4bit",
        effgen_path: Path | None = None,
        timeout: float = 120.0,
    ) -> None:
        """
        Initialize effGen client.

        Args:
            model: HuggingFace model ID
            quantization: Quantization level (4bit, 8bit, none)
            effgen_path: Path to effGen installation (default: ~/effgen_test)
            timeout: Generation timeout in seconds
        """
        self.model = model
        self.quantization = quantization
        self.effgen_path = effgen_path or Path.home() / "effgen_test"
        self.timeout = timeout
        self.provider = "effgen"

        # Validate effGen installation
        self._python_path = self.effgen_path / ".venv" / "bin" / "python"
        if not self._python_path.exists():
            raise ValueError(f"effGen Python not found at {self._python_path}")

        logger.info(f"Initialized effGen client: {self.model} ({self.quantization})")

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> dict[str, Any]:
        """
        Generate completion using effGen local model.

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

        # Build the full prompt
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        # Encode prompt to avoid quote issues in subprocess
        prompt_b64 = base64.b64encode(full_prompt.encode()).decode()

        # Build effGen script
        script = f'''
import sys
import base64
sys.path.insert(0, "{self.effgen_path}")
import logging
logging.basicConfig(level=logging.WARNING)

from effgen import load_model

model = load_model("{self.model}", quantization="{self.quantization}")

prompt = base64.b64decode("{prompt_b64}").decode()
response = model.generate(prompt, max_tokens={max_tokens or 512}, temperature={temperature})

# Handle GenerationResult object
if hasattr(response, 'text'):
    text = response.text
    tokens_count = getattr(response, 'tokens_used', 0)
else:
    text = str(response)
    tokens_count = len(text.split()) * 2  # Rough estimate

print("CONTENT_START")
print(text)
print("CONTENT_END")
print("TOKENS:" + str(tokens_count))
'''

        try:
            result = subprocess.run(
                [str(self._python_path), "-c", script],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(self.effgen_path),
            )

            output = result.stdout
            stderr = result.stderr

            # Extract content
            if "CONTENT_START" in output and "CONTENT_END" in output:
                content = output.split("CONTENT_START")[1].split("CONTENT_END")[0].strip()
            else:
                content = output.strip()
                if not content and stderr:
                    logger.error(f"effGen error: {stderr[:500]}")
                    raise RuntimeError(f"effGen generation failed: {stderr[:200]}")

            # Clean up escaped characters
            content = content.replace("\\n", "\n").replace("\\t", "\t")

            # Extract tokens
            tokens_used = 0
            if "TOKENS:" in output:
                try:
                    tokens_used = int(output.split("TOKENS:")[1].split()[0])
                except (ValueError, IndexError):
                    tokens_used = len(content.split()) * 2

            latency_ms = int((time.time() - start_time) * 1000)

            logger.debug(
                f"Generated {tokens_used} tokens in {latency_ms}ms "
                f"using effgen/{self.model}"
            )

            return {
                "content": content,
                "tokens_used": tokens_used,
                "latency_ms": latency_ms,
                "model": self.model,
            }

        except subprocess.TimeoutExpired:
            logger.error(f"effGen timeout after {self.timeout}s")
            raise RuntimeError(f"effGen timeout after {self.timeout}s")
        except Exception as e:
            logger.error(f"effGen error: {e}")
            raise RuntimeError(f"Failed to generate with effGen: {e}")

    def generate_with_agent(
        self,
        prompt: str,
        system_prompt: str | None = None,
        tools: list[str] | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """
        Generate using effGen Agent with tools.

        This uses the full agent framework for tasks that benefit
        from tool use (like PythonREPL for testing code).

        Args:
            prompt: User prompt
            system_prompt: System prompt for agent
            tools: List of tool names (e.g., ["PythonREPL", "CodeExecutor"])
            max_tokens: Maximum tokens

        Returns:
            Same format as generate()
        """
        start_time = time.time()

        tools = tools or ["PythonREPL", "CodeExecutor"]
        tools_import = ", ".join(tools)

        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        prompt_b64 = base64.b64encode(full_prompt.encode()).decode()
        system_b64 = base64.b64encode((system_prompt or "You are a helpful assistant.").encode()).decode()

        script = f'''
import sys
import base64
sys.path.insert(0, "{self.effgen_path}")
import logging
logging.basicConfig(level=logging.WARNING)

from effgen import Agent, load_model
from effgen.core.agent import AgentConfig
from effgen.tools.builtin import {tools_import}

model = load_model("{self.model}", quantization="{self.quantization}")

system_prompt = base64.b64decode("{system_b64}").decode()
config = AgentConfig(
    name="tdd_agent",
    model=model,
    tools=[{", ".join(f"{t}()" for t in tools)}],
    system_prompt=system_prompt,
)

agent = Agent(config=config)

prompt = base64.b64decode("{prompt_b64}").decode()
result = agent.run(prompt)

output = result.output if hasattr(result, 'output') else str(result)
success = result.success if hasattr(result, 'success') else True

print("CONTENT_START")
print(output)
print("CONTENT_END")
print(f"SUCCESS:{{success}}")
'''

        try:
            result = subprocess.run(
                [str(self._python_path), "-c", script],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(self.effgen_path),
            )

            output = result.stdout

            if "CONTENT_START" in output and "CONTENT_END" in output:
                content = output.split("CONTENT_START")[1].split("CONTENT_END")[0].strip()
            else:
                content = output.strip()

            content = content.replace("\\n", "\n").replace("\\t", "\t")

            latency_ms = int((time.time() - start_time) * 1000)

            return {
                "content": content,
                "tokens_used": len(content.split()) * 2,
                "latency_ms": latency_ms,
                "model": self.model,
                "agent_mode": True,
            }

        except subprocess.TimeoutExpired:
            raise RuntimeError(f"effGen agent timeout after {self.timeout}s")
        except Exception as e:
            raise RuntimeError(f"Failed to generate with effGen agent: {e}")

    def check_availability(self) -> bool:
        """Check if effGen is available and model can be loaded."""
        try:
            script = f'''
import sys
sys.path.insert(0, "{self.effgen_path}")
from effgen import load_model
model = load_model("{self.model}", quantization="{self.quantization}")
print("OK")
'''
            result = subprocess.run(
                [str(self._python_path), "-c", script],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(self.effgen_path),
            )
            return "OK" in result.stdout

        except Exception as e:
            logger.warning(f"effGen not available: {e}")
            return False


def get_effgen_client(
    model: str = "Qwen/Qwen2.5-1.5B-Instruct",
    quantization: str = "4bit",
) -> EffGenClient:
    """
    Factory function to get an effGen client.

    Args:
        model: Model ID
        quantization: Quantization level

    Returns:
        EffGenClient instance
    """
    return EffGenClient(model=model, quantization=quantization)
