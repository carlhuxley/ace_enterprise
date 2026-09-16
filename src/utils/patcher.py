"""Deterministic, host-side search/replace patching for LLM-authored diffs.

LLMs are unreliable at unified-diff format specifically: getting the
content AND the positional bookkeeping (line numbers, hunk header counts)
exactly right at once has a much lower success rate than getting content
right alone. Aider-style SEARCH/REPLACE blocks drop the positional
bookkeeping entirely -- the model states what to find (exact context) and
what to put there instead, and this module does the finding, matching
first by exact substring (must be unambiguous) and falling back to a
fuzzy line-window match for minor whitespace drift only.

No LLM involvement here -- this runs before the sandboxed GREEN phase to
decide whether a patch is even worth trying to compile (via ast.parse),
never inside it.
"""

from __future__ import annotations

import ast
import difflib
import re
from dataclasses import dataclass

_BLOCK_RE = re.compile(
    r"<<<<<<<\s*SEARCH\s*\r?\n(.*?)\r?\n=======\s*\r?\n(.*?)\r?\n>>>>>>>\s*REPLACE",
    re.DOTALL,
)


class PatchError(Exception):
    """A SEARCH/REPLACE block failed to parse or apply. Carries enough
    context (which block, what was searched for) that feeding str(exc)
    back to the worker as retry feedback is meaningful on its own."""


@dataclass(frozen=True)
class SearchReplaceBlock:
    search: str
    replace: str


@dataclass
class PatchResult:
    success: bool
    code: str | None = None
    error: str | None = None
    blocks_applied: int = 0


def parse_search_replace_blocks(text: str) -> list[SearchReplaceBlock]:
    """Every `<<<<<<< SEARCH / ======= / >>>>>>> REPLACE` block in `text`,
    in order. Empty when the response contains none -- callers should
    treat that as a patch failure, not silently no-op."""
    return [
        SearchReplaceBlock(search=m.group(1), replace=m.group(2))
        for m in _BLOCK_RE.finditer(text)
    ]


def apply_search_replace_blocks(
    original: str,
    blocks: list[SearchReplaceBlock],
    *,
    fuzzy_threshold: float = 0.85,
) -> str:
    """Apply `blocks` to `original` in order, each block's replacement
    visible to the next block's search. Raises `PatchError` (never
    silently guesses) when a block's search text is absent, ambiguous
    (matches more than once exactly), or below `fuzzy_threshold` on the
    best fuzzy line-window match.
    """
    if not blocks:
        raise PatchError("no SEARCH/REPLACE blocks found in the response")

    text = original
    for i, block in enumerate(blocks, start=1):
        count = text.count(block.search)
        if count == 1:
            text = text.replace(block.search, block.replace, 1)
            continue
        if count > 1:
            raise PatchError(
                f"block {i}/{len(blocks)}: SEARCH text matches {count} locations "
                f"in the file (ambiguous) -- narrow it with more surrounding "
                f"context so it matches exactly once:\n{block.search}"
            )
        start, end, ratio = _best_fuzzy_match(text, block.search)
        if start is None or ratio < fuzzy_threshold:
            raise PatchError(
                f"block {i}/{len(blocks)}: SEARCH text not found in the current "
                f"file, even fuzzily (best match ratio "
                f"{ratio:.2f} < {fuzzy_threshold}). Copy the SEARCH text "
                f"verbatim from the current file. SEARCH was:\n{block.search}"
            )
        text = text[:start] + block.replace + text[end:]
    return text


def apply_patch(
    original: str,
    patch_text: str,
    *,
    validate_python: bool = True,
    fuzzy_threshold: float = 0.85,
) -> PatchResult:
    """Parse `patch_text` for SEARCH/REPLACE blocks, apply them to
    `original`, and (by default) reject the result immediately with
    `ast.parse` if it isn't valid Python -- before any sandbox involvement.
    Never raises; failures come back as `PatchResult(success=False, error=...)`.
    """
    try:
        blocks = parse_search_replace_blocks(patch_text)
        patched = apply_search_replace_blocks(original, blocks, fuzzy_threshold=fuzzy_threshold)
    except PatchError as exc:
        return PatchResult(success=False, error=str(exc))

    if validate_python:
        try:
            ast.parse(patched)
        except SyntaxError as exc:
            return PatchResult(success=False, error=f"patched module has a syntax error: {exc}")

    return PatchResult(success=True, code=patched, blocks_applied=len(blocks))


def _best_fuzzy_match(text: str, search: str) -> tuple[int | None, int | None, float]:
    """Best-matching contiguous line-window of `text` (same line count as
    `search`) by `difflib.SequenceMatcher` ratio, as (char_start, char_end,
    ratio). (None, None, 0.0) when `text`/`search` is empty or too short."""
    search_lines = search.splitlines()
    text_lines = text.splitlines(keepends=True)
    window = len(search_lines)
    if not window or len(text_lines) < window:
        return None, None, 0.0

    offsets = [0]
    for line in text_lines:
        offsets.append(offsets[-1] + len(line))

    best_ratio = 0.0
    best_span: tuple[int, int] | None = None
    for start in range(0, len(text_lines) - window + 1):
        candidate = "".join(text_lines[start:start + window]).rstrip("\n")
        ratio = difflib.SequenceMatcher(None, candidate, search).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_span = (offsets[start], offsets[start + window])

    if best_span is None:
        return None, None, 0.0
    return best_span[0], best_span[1], best_ratio
