"""Extract Python code from LLM responses."""


def extract_code(response: str) -> str:
    """Strip markdown fences from an LLM response and return bare Python code.

    Handles ```python ... ``` and bare ``` ... ``` blocks; falls back to the
    full response when neither is present.
    """
    if "```python" in response:
        start = response.find("```python") + len("```python")
        end = response.find("```", start)
        if end != -1:
            return response[start:end].strip()

    if "```" in response:
        start = response.find("```") + 3
        end = response.find("```", start)
        if end != -1:
            return response[start:end].strip()

    return response.strip()
