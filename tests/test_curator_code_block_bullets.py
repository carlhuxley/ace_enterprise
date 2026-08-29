"""Regression tests for Curator._parse_synthesis dropping fenced code blocks
that follow a bullet's intro line.

Found via forensic analysis of a real benchmark run
(benchmarks/reports/20260827T055616Z_qwen2.5-coder_7b_x5runs.json,
num_neg_zero task): the curated bullet read "Use the `math` module to
correctly detect `-0.0`. Here's a corrected implementation:" and then
nothing -- the actual implementation that followed in a ```python fence was
silently discarded because the old parser only kept lines starting with
"-"/"*", so any non-bulleted continuation line (including an entire code
block) was dropped on the floor.
"""
from unittest.mock import MagicMock

from src.core.curator.module import Curator


def _curator():
    return Curator(playbook_manager=MagicMock(), llm_client=MagicMock())


def test_code_block_after_bullet_intro_is_preserved():
    response = """### Reasoning
Some reasoning here.

### Delta Bullets

#### Section: strategies_and_hard_rules
- Use the `math` module to correctly detect `-0.0`. Here's a corrected implementation:
```python
def is_negative_zero(x):
    return x == 0.0 and math.copysign(1.0, x) < 0
```
"""
    bullets, _ = _curator()._parse_synthesis(response)

    assert len(bullets) == 1
    assert "Here's a corrected implementation" in bullets[0].content
    assert "def is_negative_zero(x):" in bullets[0].content
    assert "return x == 0.0 and math.copysign(1.0, x) < 0" in bullets[0].content


def test_code_fence_does_not_leak_into_next_bullet():
    response = """### Delta Bullets

#### Section: code_snippets
- First bullet with an example:
```python
x = 1
```
- Second, unrelated bullet
"""
    bullets, _ = _curator()._parse_synthesis(response)

    assert len(bullets) == 2
    assert "x = 1" in bullets[0].content
    assert "x = 1" not in bullets[1].content
    assert bullets[1].content == "Second, unrelated bullet"


def test_code_fence_closes_before_next_section():
    response = """### Delta Bullets

#### Section: code_snippets
- Example here:
```python
y = 2
```

#### Section: troubleshooting
- A different bullet in a different section
"""
    bullets, _ = _curator()._parse_synthesis(response)

    assert len(bullets) == 2
    assert bullets[0].section == "code_snippets"
    assert "y = 2" in bullets[0].content
    assert bullets[1].section == "troubleshooting"
    assert "y = 2" not in bullets[1].content


def test_line_starting_with_dash_inside_fence_is_not_a_new_bullet():
    # A code line that happens to start with "-" (unary minus) must not be
    # mistaken for a new top-level bullet while inside a fence.
    response = """### Delta Bullets

#### Section: code_snippets
- Clamp to a negative bound:
```python
def clamp(x):
    return max(x, -1)
```
"""
    bullets, _ = _curator()._parse_synthesis(response)

    assert len(bullets) == 1
    assert "return max(x, -1)" in bullets[0].content


def test_stray_prose_outside_a_fence_is_still_dropped():
    # Scope of the fix is fenced code blocks specifically -- free-standing
    # prose between bullets (not code, not a new "-"/"*" item) keeps the
    # pre-existing behavior of being ignored, so it doesn't silently glue
    # unrelated trailing commentary onto whatever bullet preceded it.
    response = """### Delta Bullets

#### Section: strategies_and_hard_rules
- A real bullet.

This is a stray explanatory sentence with no bullet marker.
- Another real bullet.
"""
    bullets, _ = _curator()._parse_synthesis(response)

    assert len(bullets) == 2
    assert bullets[0].content == "A real bullet."
    assert bullets[1].content == "Another real bullet."
    assert "stray explanatory sentence" not in bullets[0].content
    assert "stray explanatory sentence" not in bullets[1].content
