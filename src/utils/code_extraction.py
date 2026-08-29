"""Extract Python code from LLM responses."""
import re

_PYTHON_CODE_START = re.compile(
    r"^(import\s|from\s\S+\simport\s|def\s|class\s|async def\s|@\w)", re.MULTILINE
)


def _fence_body(response: str, start: int) -> str:
    """Given the index right after an opening ``` (and before its language
    tag, if any), skip past a bare tag line -- e.g. "python", "code", or
    nothing at all -- and return everything up to the next ```, or to the
    end of the response if the fence is never closed.
    """
    newline = response.find("\n", start)
    if newline != -1:
        tag = response[start:newline].strip()
        if not tag or tag.isidentifier():
            start = newline + 1
    end = response.find("```", start)
    body = response[start:end] if end != -1 else response[start:]
    return body.strip()


def extract_code(response: str) -> str:
    """Strip markdown fences from an LLM response and return bare Python code.

    Prefers a fence explicitly tagged ```python if one exists anywhere,
    even when an untagged or differently-tagged fence appears earlier
    (e.g. a pseudocode sketch before the real answer). A tag other than
    "python" must never leak into the extracted source as a stray first
    line -- reproduced live as ```code producing
    "NameError: name 'code' is not defined" -- and a CRLF-terminated tag
    line must not be missed and leave the original closing ``` embedded
    as a line of "code" further down -- reproduced live as a SyntaxError
    partway through the file. Falls back to scanning for the first line
    that looks like real Python when no fence is present at all, so a
    conversational preamble isn't written into the source file verbatim.
    """
    python_idx = response.find("```python")
    if python_idx != -1:
        return _fence_body(response, python_idx + len("```python"))

    fence_idx = response.find("```")
    if fence_idx != -1:
        return _fence_body(response, fence_idx + 3)

    code_match = _PYTHON_CODE_START.search(response)
    if code_match:
        return response[code_match.start():].strip()

    return response.strip()
